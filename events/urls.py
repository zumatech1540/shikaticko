from django.urls import path
from . import views


app_name = 'events'


urlpatterns = [
    # ==========================================
    # PUBLIC EVENT DISCOVERY
    # ==========================================

    path(
        '',
        views.public_events,
        name='public_events'
    ),

    path(
        '<slug:slug>/',
        views.event_detail,
        name='event_detail'
    ),

    # ==========================================
    # ORGANIZER EVENT MANAGEMENT
    # ==========================================
    
    path(
        'organizer/my-events/',
        views.organizer_events,
        name='organizer_events'
    ),

    path(
        'organizer/create/',
        views.create_event,
        name='create_event'
    ),
    path(
    'organizer/create/',
    views.create_event,
    name='create_event'
),
    path(
    'organizer/my-events/<int:pk>/edit/',
    views.edit_event,
    name='event_edit'
),
    path(
    'edit/<int:pk>/',
    views.edit_event,
    name='edit_event'
),
    path(
    '<slug:slug>/book/',
    views.event_booking,
    name='event_booking'
),
    path(
    '<slug:slug>/',
    views.event_detail,
    name='event_detail'
),
    path(
    '<slug:slug>/checkout/',
    views.checkout,
    name='checkout'
),
    path(
    'admin/delete/<int:pk>/',
    views.delete_event,
    name='delete_event'
),
    path(
        'organizer/submit/<int:pk>/',
        views.submit_event_for_approval,
        name='submit_event_for_approval'
    ),

    path(
        'organizer/cancel/<int:pk>/',
        views.cancel_event,
        name='cancel_event'
    ),

    # ==========================================
    # ADMIN EVENT APPROVAL
    # ==========================================

    path(
        'admin/review/',
        views.event_review_list,
        name='event_review_list'
    ),

    path(
        'admin/review/<int:pk>/',
        views.review_event,
        name='review_event'
    ),
]