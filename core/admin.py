from django.contrib import admin


from django.contrib import admin
from .models import ContactMessage, FAQ


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):

    list_display = (
        'name',
        'email',
        'phone',
        'subject',
        'status',
        'created_at',
    )

    list_filter = (
        'status',
        'created_at',
    )

    search_fields = (
        'name',
        'email',
        'phone',
        'subject',
        'message',
    )

    readonly_fields = (
        'created_at',
        'updated_at',
    )

    list_per_page = 25


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):

    list_display = (
        'question',
        'is_active',
        'order',
        'created_at',
    )

    list_filter = (
        'is_active',
    )

    search_fields = (
        'question',
        'answer',
    )

    list_editable = (
        'is_active',
        'order',
    )

    list_per_page = 25

