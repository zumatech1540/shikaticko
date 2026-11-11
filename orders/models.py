from django.db import models

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from events.models import Event, EventTicketType


def generate_order_reference():
    return f"STK-{uuid.uuid4().hex[:12].upper()}"


def generate_ticket_number():
    return f"TKT-{uuid.uuid4().hex[:12].upper()}"


class Order(models.Model):
    """
    Stores one customer's event ticket purchase.

    An order is created as pending_payment. It becomes paid
    only after the payment provider confirms successful payment.
    """

    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_REFUNDED = "refunded"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending Payment"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Payment Failed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    PAYMENT_MPESA = "mpesa"
    PAYMENT_PESAPAL = "pesapal"

    PAYMENT_METHOD_CHOICES = [
        (PAYMENT_MPESA, "M-Pesa"),
        (PAYMENT_PESAPAL, "PesaPal"),
    ]

    PURCHASE_MYSELF = "myself"
    PURCHASE_SOMEONE_ELSE = "someone_else"

    PURCHASE_FOR_CHOICES = [
        (PURCHASE_MYSELF, "Myself"),
        (PURCHASE_SOMEONE_ELSE, "Someone Else"),
    ]

    reference = models.CharField(
        max_length=30,
        unique=True,
        default=generate_order_reference,
        editable=False,
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.PROTECT,
        related_name="orders",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_orders",
    )

    # Purchaser details
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=30)

    # Ticket recipient details
    purchase_for = models.CharField(
        max_length=20,
        choices=PURCHASE_FOR_CHOICES,
        default=PURCHASE_MYSELF,
    )

    recipient_name = models.CharField(
        max_length=200,
        blank=True,
    )

    recipient_email = models.EmailField(
        blank=True,
    )

    recipient_phone = models.CharField(
        max_length=30,
        blank=True,
    )

    # Payment details
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
    )

    mpesa_phone = models.CharField(
        max_length=20,
        blank=True,
    )

    currency = models.CharField(
        max_length=3,
        default="KES",
    )

    total_quantity = models.PositiveIntegerField(default=0)

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    terms_accepted = models.BooleanField(default=False)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)

    paid_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer_email", "created_at"]),
            models.Index(fields=["event", "status"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.customer_name}"

    def mark_as_paid(self):
        """
        Mark an order as paid after verified payment confirmation.
        """
        if self.status != self.STATUS_PAID:
            self.status = self.STATUS_PAID
            self.paid_at = timezone.now()
            self.save(update_fields=["status", "paid_at", "updated_at"])


class OrderItem(models.Model):
    """
    Stores the ticket categories and quantities in an order.

    Ticket name and price are saved as snapshots so that
    later ticket category edits do not change old orders.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )

    ticket_type = models.ForeignKey(
        EventTicketType,
        on_delete=models.PROTECT,
        related_name="order_items",
    )

    ticket_name = models.CharField(max_length=150)

    quantity = models.PositiveIntegerField()

    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="order_item_quantity_positive",
            ),
        ]

    def __str__(self):
        return (
            f"{self.ticket_name} x {self.quantity} "
            f"({self.order.reference})"
        )


class Ticket(models.Model):
    """
    One ticket record per attendee.

    Tickets should only be generated after successful payment.
    The QR token can be used later for event entry validation.
    """

    STATUS_VALID = "valid"
    STATUS_USED = "used"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_VALID, "Valid"),
        (STATUS_USED, "Used"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.PROTECT,
        related_name="tickets",
    )

    ticket_number = models.CharField(
        max_length=30,
        unique=True,
        default=generate_ticket_number,
        editable=False,
    )

    qr_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    attendee_name = models.CharField(max_length=200)
    attendee_email = models.EmailField()
    attendee_phone = models.CharField(max_length=30, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_VALID,
        db_index=True,
    )

    issued_at = models.DateTimeField(auto_now_add=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return self.ticket_number

    @property
    def event(self):
        return self.order_item.order.event

    @property
    def order(self):
        return self.order_item.order
