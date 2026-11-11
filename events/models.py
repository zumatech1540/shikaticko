from django.db import models


from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class EventCategory(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    slug = models.SlugField(
        max_length=120,
        unique=True,
        blank=True
    )

    description = models.TextField(
        blank=True
    )

    icon = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional Bootstrap icon class, e.g. bi bi-music-note"
    )

    is_active = models.BooleanField(
        default=True
    )

    display_order = models.PositiveIntegerField(
        default=0
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = 'Event Category'
        verbose_name_plural = 'Event Categories'

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or 'category'
            candidate = base_slug
            counter = 1

            while EventCategory.objects.filter(
                slug=candidate
            ).exclude(pk=self.pk).exists():

                counter += 1
                candidate = f'{base_slug}-{counter}'

            self.slug = candidate

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Event(models.Model):

    # EVENT TYPE
    EVENT_TYPE_CHOICES = [
        ('physical', 'Physical Event'),
        ('online', 'Online Event'),
        ('hybrid', 'Hybrid Event'),
    ]

    # ENTRY TYPE
    ENTRY_TYPE_CHOICES = [
        ('free', 'Free Event'),
        ('paid', 'Paid Event'),
    ]

    # EVENT STATUS
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_review', 'Pending Approval'),
        ('published', 'Published'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]

    # BASIC INFORMATION
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organized_events'
    )

    category = models.ForeignKey(
        EventCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='events'
    )

    title = models.CharField(
        max_length=255
    )

    slug = models.SlugField(
        max_length=280,
        unique=True,
        blank=True
    )

    short_description = models.CharField(
        max_length=500
    )

    description = models.TextField()

    cover_image = models.ImageField(
        upload_to='events/covers/',
        blank=True,
        null=True
    )

    # EVENT CLASSIFICATION
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPE_CHOICES,
        default='physical'
    )

    entry_type = models.CharField(
        max_length=10,
        choices=ENTRY_TYPE_CHOICES,
        default='paid'
    )

    # EVENT SCHEDULING
    start_datetime = models.DateTimeField()

    end_datetime = models.DateTimeField()

    registration_deadline = models.DateTimeField(
        blank=True,
        null=True
    )

    timezone = models.CharField(
        max_length=50,
        default='Africa/Nairobi'
    )

    # PHYSICAL VENUE INFORMATION
    venue_name = models.CharField(
        max_length=255,
        blank=True
    )

    venue_address = models.CharField(
        max_length=255,
        blank=True
    )

    town = models.CharField(
        max_length=100,
        blank=True
    )

    county = models.CharField(
        max_length=100,
        blank=True
    )

    google_maps_url = models.URLField(
        blank=True
    )

    # ONLINE EVENT INFORMATION
    online_event_url = models.URLField(
        blank=True
    )

    # CAPACITY
    capacity = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Maximum number of attendees. Leave blank for unlimited capacity."
    )

    # PUBLICATION AND APPROVAL
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )

    rejection_reason = models.TextField(
        blank=True
    )

    admin_notes = models.TextField(
        blank=True
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_events'
    )

    submitted_at = models.DateTimeField(
        blank=True,
        null=True
    )

    reviewed_at = models.DateTimeField(
        blank=True,
        null=True
    )

    published_at = models.DateTimeField(
        blank=True,
        null=True
    )

    # PROMOTION
    is_featured = models.BooleanField(
        default=False
    )

    # RECORD INFORMATION
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ['start_datetime', '-created_at']
        verbose_name = 'Event'
        verbose_name_plural = 'Events'

        indexes = [
            models.Index(
                fields=['status', 'start_datetime']
            ),
            models.Index(
                fields=['category', 'status']
            ),
            models.Index(
                fields=['organizer', 'status']
            ),
            models.Index(
                fields=['is_featured', 'status']
            ),
        ]

    def clean(self):
        super().clean()

        if self.start_datetime and self.end_datetime:
            if self.end_datetime <= self.start_datetime:
                raise ValidationError({
                    'end_datetime': 'The event end date and time must be after the start date and time.'
                })

        if self.registration_deadline and self.start_datetime:
            if self.registration_deadline > self.start_datetime:
                raise ValidationError({
                    'registration_deadline': 'The registration deadline cannot be after the event start time.'
                })

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or 'event'
            candidate = base_slug
            counter = 1

            while Event.objects.filter(
                slug=candidate
            ).exclude(pk=self.pk).exists():

                counter += 1
                candidate = f'{base_slug}-{counter}'

            self.slug = candidate

        if self.status == 'pending_review' and not self.submitted_at:
            self.submitted_at = timezone.now()

        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def is_upcoming(self):
        return (
            self.status == 'published'
            and self.start_datetime > timezone.now()
        )

    @property
    def is_ongoing(self):
        now = timezone.now()

        return (
            self.status == 'published'
            and self.start_datetime <= now <= self.end_datetime
        )

    @property
    def is_past(self):
        return self.end_datetime < timezone.now()

    def __str__(self):
        return self.title


class EventImage(models.Model):

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='gallery_images'
    )

    image = models.ImageField(
        upload_to='events/gallery/'
    )

    caption = models.CharField(
        max_length=255,
        blank=True
    )

    display_order = models.PositiveIntegerField(
        default=0
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ['display_order', '-uploaded_at']
        verbose_name = 'Event Gallery Image'
        verbose_name_plural = 'Event Gallery Images'

    def __str__(self):
        return f'{self.event.title} - Image {self.pk}'


from django.core.validators import MinValueValidator


class EventTicketType(models.Model):

    CURRENCY_CHOICES = [
        ('KES', 'Kenyan Shilling (KES)'),
        ('USD', 'US Dollar (USD)'),
    ]

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='ticket_types'
    )

    # TICKET INFORMATION
    name = models.CharField(
        max_length=100,
        help_text="Example: Regular, VIP, VVIP, Early Bird"
    )

    description = models.TextField(
        blank=True
    )

    # PRICING
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Ticket price. Enter 0 for free tickets."
    )

    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='KES'
    )

    # TICKET QUANTITY
    quantity_available = models.PositiveIntegerField(
        default=100,
        help_text="Total number of tickets available for sale."
    )

    quantity_sold = models.PositiveIntegerField(
        default=0,
        help_text="Number of tickets already sold. Managed by the system."
    )

    # ORDER LIMITS
    minimum_per_order = models.PositiveIntegerField(
        default=1
    )

    maximum_per_order = models.PositiveIntegerField(
        default=10
    )

    # SALES PERIOD
    sales_start_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Leave blank to allow sales immediately."
    )

    sales_end_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Leave blank to use the event registration deadline."
    )

    # STATUS
    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ['price', 'name']

        constraints = [
            models.UniqueConstraint(
                fields=['event', 'name'],
                name='unique_ticket_name_per_event'
            ),
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name='ticket_price_non_negative'
            ),
        ]

        verbose_name = 'Event Ticket Type'
        verbose_name_plural = 'Event Ticket Types'

    def clean(self):
        super().clean()

        errors = {}

        if self.price is not None and self.price < 0:
            errors['price'] = 'Ticket price cannot be negative.'

        if self.event_id and self.event.entry_type == 'free':
            if self.price and self.price > 0:
                errors['price'] = (
                    'Tickets for a free event must have a price of zero.'
                )

        if self.quantity_sold > self.quantity_available:
            errors['quantity_available'] = (
                'Available quantity cannot be less than tickets already sold.'
            )

        if self.minimum_per_order < 1:
            errors['minimum_per_order'] = (
                'Minimum tickets per order must be at least 1.'
            )

        if self.maximum_per_order < self.minimum_per_order:
            errors['maximum_per_order'] = (
                'Maximum tickets per order cannot be less than the minimum.'
            )

        if (
            self.sales_start_at
            and self.sales_end_at
            and self.sales_end_at <= self.sales_start_at
        ):
            errors['sales_end_at'] = (
                'Ticket sales closing time must be after the opening time.'
            )

        if errors:
            raise ValidationError(errors)

    @property
    def remaining_quantity(self):
        return max(
            self.quantity_available - self.quantity_sold,
            0
        )

    @property
    def is_available(self):
        now = timezone.now()

        if not self.is_active:
            return False

        if self.remaining_quantity <= 0:
            return False

        if self.sales_start_at and now < self.sales_start_at:
            return False

        if self.sales_end_at and now > self.sales_end_at:
            return False

        if (
            self.event.registration_deadline
            and now > self.event.registration_deadline
        ):
            return False

        return True

    def __str__(self):
        return f"{self.event.title} - {self.name}"
