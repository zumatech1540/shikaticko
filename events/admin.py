from django.contrib import admin


from django.contrib import admin
from django.utils import timezone

from .models import EventCategory, Event, EventImage


@admin.register(EventCategory)
class EventCategoryAdmin(admin.ModelAdmin):

    list_display = (
        'name',
        'slug',
        'is_active',
        'display_order',
        'created_at',
    )

    list_filter = (
        'is_active',
        'created_at',
    )

    search_fields = (
        'name',
        'description',
    )

    list_editable = (
        'is_active',
        'display_order',
    )

    prepopulated_fields = {
        'slug': ('name',),
    }

    ordering = (
        'display_order',
        'name',
    )

    list_per_page = 25


class EventImageInline(admin.TabularInline):

    model = EventImage

    extra = 1

    fields = (
        'image',
        'caption',
        'display_order',
    )

    ordering = (
        'display_order',
    )


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):

    list_display = (
        'title',
        'organizer',
        'category',
        'event_type',
        'entry_type',
        'start_datetime',
        'status',
        'is_featured',
        'created_at',
    )

    list_filter = (
        'status',
        'event_type',
        'entry_type',
        'category',
        'is_featured',
        'start_datetime',
        'created_at',
    )

    search_fields = (
        'title',
        'short_description',
        'description',
        'organizer__username',
        'organizer__email',
        'venue_name',
        'town',
        'county',
    )

    list_editable = (
        'status',
        'is_featured',
    )

    readonly_fields = (
        'slug',
        'submitted_at',
        'reviewed_at',
        'published_at',
        'created_at',
        'updated_at',
    )

    prepopulated_fields = {
        'slug': ('title',),
    }

    autocomplete_fields = (
        'organizer',
        'category',
        'reviewed_by',
    )

    date_hierarchy = 'start_datetime'

    inlines = (
        EventImageInline,
    )

    list_per_page = 25

    fieldsets = (
        ('Event Information', {
            'fields': (
                'organizer',
                'category',
                'title',
                'slug',
                'short_description',
                'description',
                'cover_image',
            )
        }),

        ('Event Classification', {
            'fields': (
                'event_type',
                'entry_type',
                'capacity',
            )
        }),

        ('Schedule', {
            'fields': (
                'start_datetime',
                'end_datetime',
                'registration_deadline',
                'timezone',
            )
        }),

        ('Physical Venue', {
            'fields': (
                'venue_name',
                'venue_address',
                'town',
                'county',
                'google_maps_url',
            ),
            'classes': ('collapse',),
        }),

        ('Online Event', {
            'fields': (
                'online_event_url',
            ),
            'classes': ('collapse',),
        }),

        ('Approval and Publication', {
            'fields': (
                'status',
                'is_featured',
                'rejection_reason',
                'admin_notes',
                'reviewed_by',
                'submitted_at',
                'reviewed_at',
                'published_at',
            )
        }),

        ('System Information', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )

    actions = (
        'approve_selected_events',
        'reject_selected_events',
        'mark_as_featured',
        'remove_from_featured',
    )

    @admin.action(description='Approve selected events')
    def approve_selected_events(self, request, queryset):

        queryset.update(
            status='published',
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
            published_at=timezone.now(),
            rejection_reason='',
        )

    @admin.action(description='Reject selected events')
    def reject_selected_events(self, request, queryset):

        queryset.update(
            status='rejected',
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )

    @admin.action(description='Mark selected events as featured')
    def mark_as_featured(self, request, queryset):

        queryset.update(
            is_featured=True
        )

    @admin.action(description='Remove selected events from featured')
    def remove_from_featured(self, request, queryset):

        queryset.update(
            is_featured=False
        )


@admin.register(EventImage)
class EventImageAdmin(admin.ModelAdmin):

    list_display = (
        'event',
        'caption',
        'display_order',
        'uploaded_at',
    )

    list_filter = (
        'uploaded_at',
    )

    search_fields = (
        'event__title',
        'caption',
    )

    autocomplete_fields = (
        'event',
    )

    ordering = (
        'display_order',
        '-uploaded_at',
    )

    readonly_fields = (
        'uploaded_at',
    )

    list_per_page = 25

from django.contrib import admin
from .models import EventTicketType


@admin.register(EventTicketType)
class EventTicketTypeAdmin(admin.ModelAdmin):
    list_display = (
        'event',
        'name',
        'price',
        'quantity_available',
        'quantity_sold',
        'is_active',
    )

    list_filter = (
        'is_active',
        'event',
    )

    search_fields = (
        'event__title',
        'name',
    )
