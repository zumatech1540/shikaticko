from django.shortcuts import render

import json
import logging
from decimal import Decimal, InvalidOperation
from io import BytesIO

import qrcode

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from email.mime.image import MIMEImage

from orders.models import Order, OrderItem, Ticket
from .models import Payment
from .providers.mpesa import (
    MpesaError,
    initiate_stk_push,
    normalize_mpesa_phone,
)


logger = logging.getLogger(__name__)


def _callback_metadata(callback):
    """
    Convert Safaricom CallbackMetadata.Item into a dictionary.
    """
    metadata = callback.get("CallbackMetadata", {})
    items = metadata.get("Item", [])

    return {
        item.get("Name"): item.get("Value")
        for item in items
        if item.get("Name")
    }



@require_POST
def initiate_mpesa_payment(request, order_reference):
    """
    Initiate an M-Pesa STK Push for a pending order.
    """

    order = get_object_or_404(
        Order,
        reference=order_reference,
        status=Order.STATUS_PENDING,
        payment_method=Order.PAYMENT_MPESA,
    )

    # Orders created by guests can still be paid by the same
    # browser session. The order reference is also unguessable.
    if request.session.get("last_order_reference") != order.reference:
        messages.error(
            request,
            "This payment session is not available."
        )
        return redirect("core:home")

    if order.currency != "KES":
        messages.error(
            request,
            "M-Pesa payments are currently supported in KES only."
        )
        return redirect(
            "payments:payment_status",
            order_reference=order.reference
        )

    if order.total_amount != order.total_amount.to_integral_value():
        messages.error(
            request,
            "M-Pesa requires a whole-number KES amount."
        )
        return redirect(
            "payments:payment_status",
            order_reference=order.reference
        )

    # Prevent a second prompt while an earlier attempt is still pending.
    existing_payment = Payment.objects.filter(
        order=order,
        provider=Payment.PROVIDER_MPESA,
        status=Payment.STATUS_PENDING,
    ).order_by("-created_at").first()

    if existing_payment and existing_payment.checkout_request_id:
        messages.info(
            request,
            "Your M-Pesa payment request is already being processed. "
            "Please check your phone."
        )
        return redirect(
            "payments:payment_status",
            order_reference=order.reference
        )

    try:
        normalized_phone = normalize_mpesa_phone(
            order.mpesa_phone
        )

        payment = Payment.objects.create(
            order=order,
            provider=Payment.PROVIDER_MPESA,
            status=Payment.STATUS_PENDING,
            amount=order.total_amount,
            currency=order.currency,
            phone_number=normalized_phone,
        )

        response = initiate_stk_push(
            phone=normalized_phone,
            amount=order.total_amount,
            account_reference=order.reference,
            transaction_description="ShikaTicko Ticket",
        )

        payment.merchant_request_id = response.get(
            "MerchantRequestID",
            ""
        )

        payment.checkout_request_id = response.get(
            "CheckoutRequestID"
        )

        payment.request_payload = response

        payment.save(
            update_fields=[
                "merchant_request_id",
                "checkout_request_id",
                "request_payload",
                "updated_at",
            ]
        )

        messages.success(
            request,
            response.get(
                "CustomerMessage",
                "M-Pesa payment prompt sent. Please check your phone."
            )
        )

    except MpesaError as error:
        if "payment" in locals():
            payment.status = Payment.STATUS_FAILED
            payment.result_description = str(error)
            payment.completed_at = timezone.now()
            payment.save(
                update_fields=[
                    "status",
                    "result_description",
                    "completed_at",
                    "updated_at",
                ]
            )

        logger.exception(
            "M-Pesa STK Push failed for order %s",
            order.reference
        )

        messages.error(
            request,
            f"Could not initiate M-Pesa payment: {error}"
        )

    except Exception:
        logger.exception(
            "Unexpected error initiating payment for order %s",
            order.reference
        )

        messages.error(
            request,
            "An unexpected payment error occurred. Please try again."
        )

    return redirect(
        "payments:payment_status",
        order_reference=order.reference
    )


@csrf_exempt
@require_POST
def mpesa_callback(request):
    """
    Receive the asynchronous STK Push result from Safaricom.

    Tickets are generated only after a successful callback whose
    amount and phone number match the payment record.
    """

    try:
        payload = json.loads(request.body.decode("utf-8"))

    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("Invalid JSON received at M-Pesa callback.")
        return JsonResponse(
            {"ResultCode": 1, "ResultDesc": "Invalid JSON"},
            status=400
        )

    callback = (
        payload.get("Body", {})
        .get("stkCallback", {})
    )

    checkout_request_id = callback.get("CheckoutRequestID")

    if not checkout_request_id:
        logger.warning("M-Pesa callback missing CheckoutRequestID.")
        return JsonResponse(
            {"ResultCode": 1, "ResultDesc": "Missing request ID"},
            status=400
        )

    payment = Payment.objects.filter(
        checkout_request_id=checkout_request_id,
        provider=Payment.PROVIDER_MPESA,
    ).select_related("order").first()

    if not payment:
        logger.warning(
            "Unknown M-Pesa CheckoutRequestID: %s",
            checkout_request_id
        )
        return JsonResponse(
            {"ResultCode": 0, "ResultDesc": "Callback received"}
        )

    result_code = callback.get("ResultCode")
    result_description = callback.get(
        "ResultDesc",
        "No result description provided."
    )

    # Save the callback for audit and troubleshooting.
    payment.callback_payload = payload
    payment.merchant_request_id = callback.get(
        "MerchantRequestID",
        payment.merchant_request_id
    )

    if str(result_code) != "0":
        payment.mark_failed(
            result_code=result_code,
            result_description=result_description,
        )
        payment.callback_payload = payload
        payment.save(update_fields=["callback_payload", "updated_at"])

        return JsonResponse(
            {"ResultCode": 0, "ResultDesc": "Callback received"}
        )

    metadata = _callback_metadata(callback)

    receipt_number = metadata.get("MpesaReceiptNumber")
    callback_amount = metadata.get("Amount")
    callback_phone = metadata.get("PhoneNumber")

    try:
        callback_amount = Decimal(str(callback_amount))
        callback_phone = normalize_mpesa_phone(callback_phone)

    except (InvalidOperation, TypeError, ValueError, MpesaError):
        logger.error(
            "Invalid successful callback metadata for payment %s",
            payment.pk
        )
        payment.result_description = (
            "Callback reported success, but payment details were invalid. "
            "Manual verification is required."
        )
        payment.callback_payload = payload
        payment.save(
            update_fields=[
                "result_description",
                "callback_payload",
                "updated_at",
            ]
        )

        return JsonResponse(
            {"ResultCode": 0, "ResultDesc": "Callback received"}
        )

    # Do not accept a callback that does not match the amount
    # and phone number used for this payment.
    if (
        callback_amount != payment.amount
        or callback_phone != payment.phone_number
        or not receipt_number
    ):
        logger.error(
            "M-Pesa callback mismatch for payment %s",
            payment.pk
        )

        payment.result_description = (
            "Payment callback details did not match the order. "
            "Manual verification is required."
        )
        payment.callback_payload = payload
        payment.save(
            update_fields=[
                "result_description",
                "callback_payload",
                "updated_at",
            ]
        )

        return JsonResponse(
            {"ResultCode": 0, "ResultDesc": "Callback received"}
        )

    try:
        with transaction.atomic():

            locked_payment = Payment.objects.select_for_update().get(
                pk=payment.pk
            )

            locked_order = Order.objects.select_for_update().get(
                pk=locked_payment.order_id
            )

            # Safeguard against duplicate callbacks.
            if locked_payment.status == Payment.STATUS_SUCCESS:
                return JsonResponse(
                    {"ResultCode": 0, "ResultDesc": "Already processed"}
                )

            # Do not let a second payment attempt issue tickets again.
            if locked_order.status == Order.STATUS_PAID:
                locked_payment.status = Payment.STATUS_SUCCESS
                locked_payment.mpesa_receipt_number = receipt_number
                locked_payment.result_code = str(result_code)
                locked_payment.result_description = result_description
                locked_payment.callback_payload = payload
                locked_payment.completed_at = timezone.now()
                locked_payment.save()

                return JsonResponse(
                    {"ResultCode": 0, "ResultDesc": "Order already paid"}
                )

            # Check whether another payment already used this receipt.
            duplicate_receipt = Payment.objects.filter(
                mpesa_receipt_number=receipt_number,
                status=Payment.STATUS_SUCCESS,
            ).exclude(pk=locked_payment.pk).exists()

            if duplicate_receipt:
                logger.error(
                    "Duplicate M-Pesa receipt received: %s",
                    receipt_number
                )
                return JsonResponse(
                    {"ResultCode": 0, "ResultDesc": "Callback received"}
                )

            locked_payment.status = Payment.STATUS_SUCCESS
            locked_payment.mpesa_receipt_number = receipt_number
            locked_payment.result_code = str(result_code)
            locked_payment.result_description = result_description
            locked_payment.callback_payload = payload
            locked_payment.completed_at = timezone.now()
            locked_payment.save()

            # Recheck ticket stock before issuing tickets.
            order_items = OrderItem.objects.filter(
                order=locked_order
            ).select_related("ticket_type")

            for item in order_items:
                ticket_type = (
                    item.ticket_type.__class__.objects
                    .select_for_update()
                    .get(pk=item.ticket_type_id)
                )

                if item.quantity > ticket_type.remaining_quantity:
                    raise ValueError(
                        f"Insufficient remaining stock for "
                        f"{ticket_type.name}. Payment received; "
                        f"manual ticket allocation is required."
                    )

                ticket_type.quantity_sold += item.quantity
                ticket_type.save(
                    update_fields=["quantity_sold"]
                )

                attendee_name = (
                    locked_order.recipient_name
                    or locked_order.customer_name
                )

                attendee_email = (
                    locked_order.recipient_email
                    or locked_order.customer_email
                )

                attendee_phone = (
                    locked_order.recipient_phone
                    or locked_order.customer_phone
                )

                for _ in range(item.quantity):
                    Ticket.objects.create(
                        order_item=item,
                        attendee_name=attendee_name,
                        attendee_email=attendee_email,
                        attendee_phone=attendee_phone,
                    )

            locked_order.mark_as_paid()

            # Send the email only after the database transaction commits.
            transaction.on_commit(
                lambda order_id=locked_order.pk: send_ticket_email(order_id)
            )

    except Exception:
        logger.exception(
            "Could not complete order after M-Pesa callback: %s",
            payment.order.reference
        )

        # The payment callback has been received, but ticket allocation
        # needs investigation. Do not silently claim tickets were issued.
        return JsonResponse(
            {"ResultCode": 0, "ResultDesc": "Callback received"}
        )

    return JsonResponse(
        {"ResultCode": 0, "ResultDesc": "Payment processed"}
    )


def send_ticket_email(order_id):
    """
    Email the purchaser their individual ticket cards and QR codes.
    """

    try:
        order = Order.objects.prefetch_related(
            "items__tickets"
        ).select_related("event").get(pk=order_id)

        tickets = Ticket.objects.filter(
            order_item__order=order
        ).select_related(
            "order_item",
            "order_item__ticket_type",
        )

        if not tickets.exists():
            logger.warning(
                "No tickets found for order %s",
                order.reference
            )
            return

        subject = (
            f"Your ShikaTicko Tickets - {order.event.title}"
        )

        html_parts = [
            "<html><body>",
            "<h2>Payment Successful!</h2>",
            f"<p>Dear {escape(order.customer_name)},</p>",
            "<p>Your payment has been received. "
            "Your event tickets are below.</p>",
            f"<p><strong>Order Reference:</strong> "
            f"{escape(order.reference)}</p>",
            f"<h3>{escape(order.event.title)}</h3>",
        ]

        email = EmailMultiAlternatives(
            subject=subject,
            body=(
                f"Your payment for {order.event.title} was successful. "
                f"Order reference: {order.reference}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.customer_email],
        )

        for index, ticket in enumerate(tickets, start=1):
            cid = f"ticket_qr_{index}"

            qr = qrcode.make(str(ticket.qr_token))
            image_buffer = BytesIO()
            qr.save(image_buffer, format="PNG")
            image_buffer.seek(0)

            image = MIMEImage(image_buffer.read(), _subtype="png")
            image.add_header(
                "Content-ID",
                f"<{cid}>"
            )
            image.add_header(
                "Content-Disposition",
                "inline",
                filename=f"{ticket.ticket_number}.png"
            )
            email.attach(image)

            html_parts.extend([
                '<div style="border:1px solid #ddd;'
                'padding:18px;margin:18px 0;'
                'border-radius:12px;">',
                "<h3>ShikaTicko Event Ticket</h3>",
                f"<p><strong>Event:</strong> "
                f"{escape(order.event.title)}</p>",
                f"<p><strong>Ticket:</strong> "
                f"{escape(ticket.ticket_number)}</p>",
                f"<p><strong>Attendee:</strong> "
                f"{escape(ticket.attendee_name)}</p>",
                f"<p><strong>Category:</strong> "
                f"{escape(ticket.order_item.ticket_name)}</p>",
                f"<p><strong>Order:</strong> "
                f"{escape(order.reference)}</p>",
                f'<img src="cid:{cid}" '
                'alt="Ticket QR Code" '
                'style="width:160px;height:160px;">',
                "</div>",
            ])

        html_parts.extend([
            "<p>Please present your QR code at the event entrance.</p>",
            "<p>Thank you for booking with ShikaTicko.</p>",
            "</body></html>",
        ])

        email.attach_alternative(
            "".join(html_parts),
            "text/html"
        )

        email.send(fail_silently=False)

    except Exception:
        logger.exception(
            "Could not send ticket email for order ID %s",
            order_id
        )


def payment_status(request, order_reference):
    """
    Display the current order and payment status.
    """

    order = get_object_or_404(
        Order.objects.prefetch_related(
            "items",
            "payments",
        ).select_related("event"),
        reference=order_reference,
    )

    if request.session.get("last_order_reference") != order.reference:
        messages.error(
            request,
            "You cannot access this order from this session."
        )
        return redirect("core:home")

    latest_payment = order.payments.order_by(
        "-created_at"
    ).first()

    return render(
        request,
        "payments/payment_status.html",
        {
            "order": order,
            "latest_payment": latest_payment,
        }
    )
