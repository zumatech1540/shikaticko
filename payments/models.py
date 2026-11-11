from django.db import models

from django.db import models
from django.utils import timezone


class Payment(models.Model):
    """
    Records an individual payment attempt for a ShikaTicko order.

    A single order can have multiple payment attempts if a customer
    retries after a failed or cancelled STK Push.
    """

    PROVIDER_MPESA = "mpesa"
    PROVIDER_PESAPAL = "pesapal"

    PROVIDER_CHOICES = [
        (PROVIDER_MPESA, "M-Pesa"),
        (PROVIDER_PESAPAL, "PesaPal"),
    ]

    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SUCCESS, "Successful"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="payments",
    )

    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_MPESA,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    currency = models.CharField(
        max_length=3,
        default="KES",
    )

    phone_number = models.CharField(
        max_length=20,
        blank=True,
    )

    # Safaricom STK Push identifiers
    merchant_request_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
    )

    checkout_request_id = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
    )

    mpesa_receipt_number = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
    )

    result_code = models.CharField(
        max_length=20,
        blank=True,
    )

    result_description = models.TextField(
        blank=True,
    )

    # Keep provider responses for troubleshooting and audit.
    request_payload = models.JSONField(
        default=dict,
        blank=True,
    )

    callback_payload = models.JSONField(
        default=dict,
        blank=True,
    )

    initiated_at = models.DateTimeField(
        default=timezone.now,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["order", "status"],
                name="payment_order_status_idx",
            ),
            models.Index(
                fields=["provider", "created_at"],
                name="payment_provider_date_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.order.reference} - "
            f"{self.get_provider_display()} - "
            f"{self.get_status_display()}"
        )

    def mark_successful(
        self,
        receipt_number="",
        result_code="0",
        result_description="Payment successful.",
    ):
        """
        Record a successful provider confirmation.

        Order payment completion and ticket issuance will be handled
        by the payment callback workflow, not by this method alone.
        """
        if self.status == self.STATUS_SUCCESS:
            return

        self.status = self.STATUS_SUCCESS
        self.mpesa_receipt_number = receipt_number
        self.result_code = str(result_code)
        self.result_description = result_description
        self.completed_at = timezone.now()

        self.save(
            update_fields=[
                "status",
                "mpesa_receipt_number",
                "result_code",
                "result_description",
                "completed_at",
                "updated_at",
            ]
        )

    def mark_failed(
        self,
        result_code="",
        result_description="Payment failed.",
    ):
        """
        Record a failed or cancelled payment attempt.
        """
        if self.status == self.STATUS_SUCCESS:
            return

        self.status = self.STATUS_FAILED
        self.result_code = str(result_code)
        self.result_description = result_description
        self.completed_at = timezone.now()

        self.save(
            update_fields=[
                "status",
                "result_code",
                "result_description",
                "completed_at",
                "updated_at",
            ]
        )
