from django.db import models

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):

    ROLE_CHOICES = [
        ('customer', 'Customer'),
        ('organizer', 'Event Organizer'),
        ('staff', 'Platform Staff'),
    ]

    email = models.EmailField(
        unique=True,
        help_text='A valid email address is required.'
    )

    phone = models.CharField(
        max_length=20,
        blank=True
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='customer'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_joined']

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    @property
    def is_organizer(self):
        return self.role == 'organizer'

    @property
    def is_customer(self):
        return self.role == 'customer'