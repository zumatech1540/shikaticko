
import json
import logging
from decimal import Decimal, InvalidOperation
from io import BytesIO

import qrcode

from email.mime.image import MIMEImage

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

from orders.models import Order, OrderItem, Ticket
from .models import Payment

from .providers.mpesa import (
    MpesaError,
    initiate_stk_push,
    normalize_mpesa_phone,
)


logger = logging.getLogger(__name__)


# ==========================================================
# 1. CALLBACK METADATA
# ==========================================================

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


# ==========================================================
# 2. INITIATE M-PESA PAYMENT
# ==========================================================

@require_POST
def initiate_mpesa_payment(request, order_reference):
    """
    Initiate an M-Pesa STK Push for a pending order.

    Supports:
        - Registered customers
        - Guest customers
        - Production Daraja
        - Sandbox Daraja
    """

    order = get_object_or_404(
        Order,
        reference=order_reference,
        status=Order.STATUS_PENDING,
        payment_method=Order.PAYMENT_MPESA,
    )

    # ------------------------------------------------------
    # VERIFY CUSTOMER SESSION
    # ------------------------------------------------------

    if request.session.get("last_order_reference") != order.reference:
        messages.error(
            request,
            "This payment session is not available."
        )
        return redirect("core:home")

    # ------------------------------------------------------
    # VALIDATE CURRENCY
    # ------------------------------------------------------

    if order.currency != "KES":
        messages.error(
            request,
            "M-Pesa payments are currently supported in KES only."
        )

        return redirect(
            "payments:payment_status",
            order_reference=order.reference
        )

    # ------------------------------------------------------
    # VALIDATE AMOUNT
    # ------------------------------------------------------

    if order.total_amount != order.total_amount.to_integral_value():
        messages.error(
            request,
            "M-Pesa requires a whole-number KES amount."
        )

        return redirect(
            "payments:payment_status",
            order_reference=order.reference
        )

    if order.total_amount < 1:
        messages.error(
            request,
            "Invalid payment amount."
        )

        return redirect(
            "payments:payment_status",
            order_reference=order.reference
        )

    # ------------------------------------------------------
    # PREVENT DUPLICATE PAYMENT PROMPTS
    # ------------------------------------------------------

    existing_payment = Payment.objects.filter(
        order=order,
        provider=Payment.PROVIDER_MPESA,
        status=Payment.STATUS_PENDING,
    ).order_by("-created_at").first()

    if existing_payment:
        messages.info(
            request,
            "Your previous M-Pesa payment request is still pending. "
            "Please check your phone or wait for payment confirmation "
            "before trying again."
        )

        return redirect(
            "payments:payment_status",
            order_reference=order.reference
        )

    payment = None

    # ------------------------------------------------------
    # INITIATE PAYMENT
    # ------------------------------------------------------

    try:

        normalized_phone = normalize_mpesa_phone(
            order.mpesa_phone
        )

        # Create a payment record before contacting Safaricom.
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

        # --------------------------------------------------
        # SAVE SAFARICOM REQUEST IDS
        # --------------------------------------------------

        payment.merchant_request_id = response.get(
            "MerchantRequestID",
            ""
        )

        payment.checkout_request_id = response.get(
            "CheckoutRequestID",
            ""
        )

        payment.request_payload = response

        payment.result_description = response.get(
            "ResponseDescription",
            "STK Push accepted. Waiting for customer payment."
        )

        payment.save(
            update_fields=[
                "merchant_request_id",
                "checkout_request_id",
                "request_payload",
                "result_description",
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

        logger.exception(
            "M-Pesa STK Push failed for order %s",
            order.reference
        )

        if payment:
            error_message = str(error)

            # A timeout or connection failure may happen after
            # Safaricom has received the request. Do not mark
            # such an attempt failed automatically.
            uncertain = any(
                phrase in error_message.lower()
                for phrase in (
                    "timed out",
                    "timeout",
                    "could not connect",
                    "connection",
                )
            )

            if uncertain:
                payment.result_description = (
                    "The STK Push response could not be confirmed. "
                    "The payment may still be processing. "
                    "Check the payment status before retrying. "
                    + error_message
                )

                payment.save(
                    update_fields=[
                        "result_description",
                        "updated_at",
                    ]
                )

            else:
                payment.status = Payment.STATUS_FAILED
                payment.result_description = error_message
                payment.completed_at = timezone.now()

                payment.save(
                    update_fields=[
                        "status",
                        "result_description",
                        "completed_at",
                        "updated_at",
                    ]
                )

        messages.error(
            request,
            f"Could not confirm the M-Pesa request: {error}"
        )

    except Exception:
        logger.exception(
            "Unexpected error initiating payment for order %s",
            order.reference
        )

        if payment and payment.status == Payment.STATUS_PENDING:
            payment.result_description = (
                "An unexpected error occurred while processing "
                "the STK Push. Payment status requires verification."
            )

            payment.save(
                update_fields=[
                    "result_description",
                    "updated_at",
                ]
            )

        messages.error(
            request,
            "An unexpected payment error occurred. "
            "Please check your payment status before retrying."
        )

    return redirect(
        "payments:payment_status",
        order_reference=order.reference
    )


# ==========================================================
# 3. ISSUE TICKETS AFTER CONFIRMED PAYMENT
# ==========================================================

def _fulfil_paid_order(locked_order):
    """
    Allocate tickets for a confirmed M-Pesa payment.

    Must be called inside an outer database transaction.

    Uses a nested transaction so ticket allocation can roll
    back without losing the successful payment record.
    """

    if locked_order.status == Order.STATUS_PAID:
        return False

    with transaction.atomic():

        order_items = OrderItem.objects.filter(
            order=locked_order
        ).select_related(
            "ticket_type"
        )

        if not order_items.exists():
            raise ValueError(
                "No order items were found for this payment."
            )

        for item in order_items:

            ticket_type = (
                item.ticket_type.__class__.objects
                .select_for_update()
                .get(pk=item.ticket_type_id)
            )

            if item.quantity > ticket_type.remaining_quantity:
                raise ValueError(
                    f"Insufficient remaining stock for "
                    f"{ticket_type.name}. Payment was received, "
                    f"but ticket allocation needs manual attention."
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

        # Only mark the order paid after all tickets are created.
        locked_order.mark_as_paid()

    return True


# ==========================================================
# 4. M-PESA CALLBACK
# ==========================================================

@csrf_exempt
@require_POST
def mpesa_callback(request):
    """
    Receive asynchronous Daraja STK Push callbacks.

    A payment is accepted only when:
        - CheckoutRequestID matches a payment record.
        - ResultCode is successful.
        - Amount matches the payment.
        - Phone number matches the payment.
        - A valid M-Pesa receipt is supplied.

    Duplicate callbacks will not create duplicate tickets.
    """

    # ------------------------------------------------------
    # READ CALLBACK
    # ------------------------------------------------------

    try:
        payload = json.loads(
            request.body.decode("utf-8")
        )

    except (json.JSONDecodeError, UnicodeDecodeError):

        logger.warning(
            "Invalid JSON received at M-Pesa callback."
        )

        return JsonResponse(
            {
                "ResultCode": 1,
                "ResultDesc": "Invalid JSON",
            },
            status=400
        )

    callback = (
        payload.get("Body", {})
        .get("stkCallback", {})
    )

    checkout_request_id = callback.get(
        "CheckoutRequestID"
    )

    if not checkout_request_id:

        logger.warning(
            "M-Pesa callback missing CheckoutRequestID."
        )

        return JsonResponse(
            {
                "ResultCode": 1,
                "ResultDesc": "Missing request ID",
            },
            status=400
        )

    # ------------------------------------------------------
    # FIND PAYMENT
    # ------------------------------------------------------

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
            {
                "ResultCode": 0,
                "ResultDesc": "Callback received",
            }
        )

    result_code = callback.get("ResultCode")

    result_description = callback.get(
        "ResultDesc",
        "No result description provided."
    )

    # ------------------------------------------------------
    # HANDLE FAILED OR CANCELLED PAYMENT
    # ------------------------------------------------------

    if str(result_code) != "0":

        with transaction.atomic():

            locked_payment = Payment.objects.select_for_update().get(
                pk=payment.pk
            )

            # Never downgrade an already successful payment.
            if locked_payment.status != Payment.STATUS_SUCCESS:

                locked_payment.mark_failed(
                    result_code=result_code,
                    result_description=result_description,
                )

            locked_payment.callback_payload = payload

            locked_payment.save(
                update_fields=[
                    "callback_payload",
                    "updated_at",
                ]
            )

        logger.info(
            "M-Pesa payment unsuccessful for order %s: %s",
            payment.order.reference,
            result_description
        )

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Callback received",
            }
        )

    # ------------------------------------------------------
    # EXTRACT SUCCESSFUL PAYMENT DETAILS
    # ------------------------------------------------------

    metadata = _callback_metadata(callback)

    receipt_number = metadata.get(
        "MpesaReceiptNumber"
    )

    callback_amount = metadata.get("Amount")
    callback_phone = metadata.get("PhoneNumber")

    try:

        callback_amount = Decimal(
            str(callback_amount)
        )

        callback_phone = normalize_mpesa_phone(
            callback_phone
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
        MpesaError,
    ):

        logger.error(
            "Invalid successful callback metadata for payment %s",
            payment.pk
        )

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Callback received for verification",
            }
        )

    # ------------------------------------------------------
    # VERIFY PAYMENT DETAILS
    # ------------------------------------------------------

    if (
        callback_amount != payment.amount
        or callback_phone != payment.phone_number
        or not receipt_number
    ):

        logger.error(
            "M-Pesa callback mismatch for payment %s",
            payment.pk
        )

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Payment details require verification",
            }
        )

    # ------------------------------------------------------
    # PROCESS SUCCESSFUL PAYMENT
    # ------------------------------------------------------

    try:

        with transaction.atomic():

            locked_payment = Payment.objects.select_for_update().get(
                pk=payment.pk
            )

            locked_order = Order.objects.select_for_update().get(
                pk=locked_payment.order_id
            )

            # ----------------------------------------------
            # CHECK FOR DUPLICATE RECEIPTS
            # ----------------------------------------------

            duplicate_receipt = Payment.objects.filter(
                mpesa_receipt_number=receipt_number,
                status=Payment.STATUS_SUCCESS,
            ).exclude(
                pk=locked_payment.pk
            ).exists()

            if duplicate_receipt:

                logger.error(
                    "Duplicate M-Pesa receipt detected: %s",
                    receipt_number
                )

                return JsonResponse(
                    {
                        "ResultCode": 0,
                        "ResultDesc": "Duplicate receipt detected",
                    }
                )

            # ----------------------------------------------
            # SAVE SUCCESSFUL PAYMENT
            # ----------------------------------------------

            if locked_payment.status != Payment.STATUS_SUCCESS:

                locked_payment.status = Payment.STATUS_SUCCESS

                locked_payment.mpesa_receipt_number = receipt_number

                locked_payment.result_code = str(result_code)

                locked_payment.result_description = result_description

                locked_payment.completed_at = timezone.now()

            locked_payment.callback_payload = payload

            locked_payment.save()

            # ----------------------------------------------
            # CHECK WHETHER ORDER IS ALREADY PAID
            # ----------------------------------------------

            if locked_order.status == Order.STATUS_PAID:

                logger.info(
                    "Order %s is already paid.",
                    locked_order.reference
                )

                return JsonResponse(
                    {
                        "ResultCode": 0,
                        "ResultDesc": "Order already paid",
                    }
                )

            # ----------------------------------------------
            # ISSUE TICKETS
            # ----------------------------------------------

            try:

                tickets_created = _fulfil_paid_order(
                    locked_order
                )

            except Exception as error:

                logger.exception(
                    "Payment received but ticket allocation failed "
                    "for order %s",
                    locked_order.reference
                )

                locked_payment.result_description = (
                    "Payment confirmed by Safaricom. "
                    "Ticket allocation requires manual attention: "
                    + str(error)
                )

                locked_payment.save(
                    update_fields=[
                        "result_description",
                        "updated_at",
                    ]
                )

                # The outer transaction commits the successful
                # payment even when ticket allocation fails.
                tickets_created = False

            # ----------------------------------------------
            # SEND TICKETS AFTER DATABASE COMMIT
            # ----------------------------------------------

            if tickets_created:

                transaction.on_commit(
                    lambda order_id=locked_order.pk:
                    send_ticket_email(order_id)
                )

                logger.info(
                    "Payment and ticket allocation successful. "
                    "Order: %s, Receipt: %s",
                    locked_order.reference,
                    receipt_number
                )

    except Exception:

        logger.exception(
            "Could not process M-Pesa callback for order %s",
            payment.order.reference
        )

        return JsonResponse(
            {
                "ResultCode": 0,
                "ResultDesc": "Callback received",
            }
        )

    return JsonResponse(
        {
            "ResultCode": 0,
            "ResultDesc": "Payment processed",
        }
    )


# ==========================================================
# 5. EMAIL TICKETS WITH QR CODES
# ==========================================================

def send_ticket_email(order_id):
    """
    Email the purchaser their individual ShikaTicko ticket cards.

    Every ticket receives its own QR code.
    """

    try:

        order = Order.objects.select_related(
            "event"
        ).get(
            pk=order_id
        )

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

        recipient_email = (
            order.customer_email
            or order.recipient_email
        )

        if not recipient_email:

            logger.error(
                "No customer email available for order %s",
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
            "<p>Your M-Pesa payment has been received. "
            "Your event tickets are below.</p>",
            f"<p><strong>Order Reference:</strong> "
            f"{escape(order.reference)}</p>",
            f"<h3>{escape(order.event.title)}</h3>",
        ]

        email = EmailMultiAlternatives(
            subject=subject,
            body=(
                f"Your payment for {order.event.title} was successful. "
                f"Order reference: {order.reference}. "
                "Your tickets are attached in the HTML email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email],
        )

        # --------------------------------------------------
        # GENERATE INDIVIDUAL TICKET QR CODES
        # --------------------------------------------------

        for index, ticket in enumerate(tickets, start=1):

            cid = f"ticket_qr_{index}"

            qr = qrcode.make(
                str(ticket.qr_token)
            )

            image_buffer = BytesIO()

            qr.save(
                image_buffer,
                format="PNG"
            )

            image_buffer.seek(0)

            image = MIMEImage(
                image_buffer.read(),
                _subtype="png"
            )

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

        email.send(
            fail_silently=False
        )

        logger.info(
            "Ticket email successfully sent for order %s",
            order.reference
        )

    except Exception:

        logger.exception(
            "Could not send ticket email for order ID %s",
            order_id
        )


# ==========================================================
# 6. PAYMENT STATUS PAGE
# ==========================================================

def payment_status(request, order_reference):
    """
    Display current order and M-Pesa payment status.
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
