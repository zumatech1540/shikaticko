import logging

from django.shortcuts import render
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.views.decorators.http import require_POST



from .models import Event, EventCategory, EventTicketType
from .forms import EventForm, EventTicketTypeFormSet


def is_event_organizer(user):
    """
    Allow organizers, staff members and superusers
    to access organizer event management pages.
    """
    return (
        user.is_authenticated
        and (
            user.is_superuser
            or user.is_staff
            or getattr(user, 'role', '') == 'organizer'
        )
    )


def public_events(request):
    """
    Display published events to visitors.
    Supports searching and filtering by category and event type.
    """

    events = Event.objects.filter(
        status='published',
        end_datetime__gte=timezone.now()
    ).select_related(
        'category',
        'organizer'
    )

    search_query = request.GET.get('q', '').strip()
    category_slug = request.GET.get('category', '').strip()
    event_type = request.GET.get('type', '').strip()
    location = request.GET.get('location', '').strip()

    if search_query:
        events = events.filter(
            Q(title__icontains=search_query)
            | Q(short_description__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(venue_name__icontains=search_query)
            | Q(town__icontains=search_query)
            | Q(county__icontains=search_query)
        )

    if category_slug:
        events = events.filter(
            category__slug=category_slug
        )

    if event_type in ['physical', 'online', 'hybrid']:
        events = events.filter(
            event_type=event_type
        )

    if location:
        events = events.filter(
            Q(town__icontains=location)
            | Q(county__icontains=location)
            | Q(venue_name__icontains=location)
        )

    categories = EventCategory.objects.filter(
        is_active=True
    )

    paginator = Paginator(events.distinct(), 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'events': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'search_query': search_query,
        'selected_category': category_slug,
        'selected_type': event_type,
        'location': location,
    }

    return render(
        request,
        'events/event_list.html',
        context
    )


def event_detail(request, slug):
    """
    Display details of a published event.
    """

    event = get_object_or_404(
        Event.objects.select_related(
            'category',
            'organizer'
        ).prefetch_related(
            'gallery_images'
        ),
        slug=slug,
        status='published'
    )

    context = {
        'event': event,
    }

    return render(
        request,
        'events/event_detail.html',
        context
    )


@login_required
def organizer_events(request):
    """
    Display events belonging to the logged-in organizer.
    Staff and superusers can view all events.
    """

    if not is_event_organizer(request.user):
        messages.error(
            request,
            'You do not have permission to access event management.'
        )
        return redirect('core:home')

    if request.user.is_staff or request.user.is_superuser:
        events = Event.objects.select_related(
            'category',
            'organizer'
        )
    else:
        events = Event.objects.filter(
            organizer=request.user
        ).select_related(
            'category'
        )

    events = events.order_by('-created_at')

    status_filter = request.GET.get('status', '').strip()

    valid_statuses = [
        'draft',
        'pending_review',
        'published',
        'rejected',
        'cancelled',
        'completed',
    ]

    if status_filter in valid_statuses:
        events = events.filter(status=status_filter)

    paginator = Paginator(events, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'events': page_obj,
        'page_obj': page_obj,
        'selected_status': status_filter,
        'total_events': events.count(),
    }

    return render(
        request,
        'events/organizer_events.html',
        context
    )



@login_required
def create_event(request):
    """
    Allow organizers and administrators to create events
    with multiple ticket categories.

    Events can be saved as drafts or submitted for approval.
    """

    if not is_event_organizer(request.user):
        messages.error(
            request,
            'Only approved organizers can create events.'
        )
        return redirect('core:home')

    if request.method == 'POST':

        form = EventForm(
            request.POST,
            request.FILES
        )

        # Create an unsaved event instance for the ticket formset.
        event = Event()

        if form.is_valid():
            event = form.save(commit=False)
            event.entry_type = form.cleaned_data.get('entry_type')

        else:
            event.entry_type = request.POST.get(
                'entry_type',
                'paid'
            )

        ticket_formset = EventTicketTypeFormSet(
            request.POST,
            instance=event,
            prefix='tickets'
        )

        if form.is_valid() and ticket_formset.is_valid():

            action = request.POST.get('action', 'draft')

            try:
                with transaction.atomic():

                    event.organizer = request.user

                    if action == 'submit':
                        event.status = 'pending_review'
                        event.submitted_at = timezone.now()
                    else:
                        event.status = 'draft'

                    # Validate the event before saving.
                    event.full_clean()
                    event.save()

                    # Save all ticket categories against this event.
                    ticket_formset.instance = event
                    ticket_formset.save()

                if action == 'submit':
                    messages.success(
                        request,
                        'Your event and ticket categories have been '
                        'submitted successfully. The event is now '
                        'awaiting administrator approval.'
                    )
                else:
                    messages.success(
                        request,
                        'Your event and ticket categories have been '
                        'saved successfully as a draft.'
                    )

                return redirect('events:organizer_events')

            except ValidationError as error:

                if hasattr(error, 'message_dict'):
                    for field_errors in error.message_dict.values():
                        for error_message in field_errors:
                            messages.error(
                                request,
                                error_message
                            )
                else:
                    for error_message in error.messages:
                        messages.error(
                            request,
                            error_message
                        )

        else:
            messages.error(
                request,
                'Please correct the event details and ticket '
                'category errors before continuing.'
            )

    else:
        form = EventForm()

        event = Event()

        ticket_formset = EventTicketTypeFormSet(
            instance=event,
            prefix='tickets'
        )

    context = {
        'form': form,
        'ticket_formset': ticket_formset,
        'event': event,
        'is_edit': False,
        'page_title': 'Create New Event',
        'button_text': 'Save Event',
    }

    return render(
        request,
        'events/event_form.html',
        context
    )

@login_required
def edit_event(request, pk):
    """
    Allow organizers to edit their own draft or rejected events.

    Administrators can edit events regardless of their status.
    Ticket categories are managed together with event details.
    """

    if not is_event_organizer(request.user):
        messages.error(
            request,
            'You do not have permission to edit events.'
        )
        return redirect('core:home')

    event = get_object_or_404(
        Event,
        pk=pk
    )

    is_admin = (
        request.user.is_staff
        or request.user.is_superuser
    )

    # Organizers can only edit their own events.
    if not (
        is_admin
        or event.organizer_id == request.user.id
    ):
        messages.error(
            request,
            'You cannot edit another organizer’s event.'
        )
        return redirect('events:organizer_events')

    # Organizers can edit drafts and rejected events.
    # Administrators can edit events in any status.
    if not is_admin and event.status not in [
        'draft',
        'rejected'
    ]:
        messages.error(
            request,
            'You can only edit your own draft or rejected events.'
        )
        return redirect('events:organizer_events')

    if request.method == 'POST':

        form = EventForm(
            request.POST,
            request.FILES,
            instance=event
        )

        if form.is_valid():
            updated_event = form.save(commit=False)
            updated_event.entry_type = form.cleaned_data.get(
                'entry_type'
            )
        else:
            updated_event = event
            updated_event.entry_type = request.POST.get(
                'entry_type',
                event.entry_type
            )

        ticket_formset = EventTicketTypeFormSet(
            request.POST,
            instance=updated_event,
            prefix='tickets'
        )

        if form.is_valid() and ticket_formset.is_valid():

            try:
                with transaction.atomic():

                    # Preserve the original event owner.
                    updated_event.organizer = event.organizer

                    # Preserve the existing approval status.
                    updated_event.status = event.status

                    updated_event.full_clean()
                    updated_event.save()

                    # Save ticket categories without changing
                    # the system-managed quantity_sold field.
                    ticket_formset.instance = updated_event
                    ticket_formset.save()

                messages.success(
                    request,
                    'Event details and ticket categories '
                    'updated successfully.'
                )

                return redirect('events:organizer_events')

            except ValidationError as error:

                if hasattr(error, 'message_dict'):
                    for field_errors in error.message_dict.values():
                        for error_message in field_errors:
                            messages.error(
                                request,
                                error_message
                            )
                else:
                    for error_message in error.messages:
                        messages.error(
                            request,
                            error_message
                        )

        else:
            messages.error(
                request,
                'Please correct the event details and ticket '
                'category errors before continuing.'
            )

    else:
        form = EventForm(
            instance=event
        )

        ticket_formset = EventTicketTypeFormSet(
            instance=event,
            prefix='tickets'
        )

    context = {
        'form': form,
        'ticket_formset': ticket_formset,
        'event': event,
        'is_edit': True,
        'page_title': 'Edit Event',
        'button_text': 'Update Event',
    }

    return render(
        request,
        'events/event_form.html',
        context
    )

@login_required
@require_POST
def delete_event(request, pk):

    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(
            request,
            "You are not authorized to delete events."
        )
        return redirect('core:home')

    event = get_object_or_404(Event, pk=pk)

    event_title = event.title
    event.delete()

    messages.success(
        request,
        f'"{event_title}" has been deleted successfully.'
    )

    return redirect('accounts:admin_dashboard')

@login_required
@require_POST
def submit_event_for_approval(request, pk):
    """
    Submit an organizer's draft or rejected event for admin review.
    """

    if not is_event_organizer(request.user):
        messages.error(
            request,
            'You do not have permission to submit events.'
        )
        return redirect('core:home')

    event = get_object_or_404(
        Event,
        pk=pk
    )

    if not (
        request.user.is_staff
        or request.user.is_superuser
        or event.organizer_id == request.user.id
    ):
        messages.error(
            request,
            'You cannot submit another organizer’s event.'
        )
        return redirect('events:organizer_events')

    if event.status not in ['draft', 'rejected']:
        messages.error(
            request,
            'This event cannot be submitted in its current status.'
        )
        return redirect('events:organizer_events')

    try:
        event.full_clean()
    except ValidationError as error:
        if hasattr(error, 'message_dict'):
            error_messages = []

            for field_errors in error.message_dict.values():
                error_messages.extend(field_errors)

            for error_message in error_messages:
                messages.error(request, error_message)
        else:
            for error_message in error.messages:
                messages.error(request, error_message)

        return redirect('events:edit_event', pk=event.pk)

    event.status = 'pending_review'
    event.submitted_at = timezone.now()
    event.rejection_reason = ''
    event.save()

    messages.success(
        request,
        'Your event has been submitted successfully '
        'and is awaiting administrator approval.'
    )

    return redirect('events:organizer_events')


@login_required
@require_POST
def cancel_event(request, pk):
    """
    Allow the event owner or an administrator to cancel an event.
    """

    if not is_event_organizer(request.user):
        messages.error(
            request,
            'You do not have permission to cancel events.'
        )
        return redirect('core:home')

    event = get_object_or_404(
        Event,
        pk=pk
    )

    if not (
        request.user.is_staff
        or request.user.is_superuser
        or event.organizer_id == request.user.id
    ):
        messages.error(
            request,
            'You cannot cancel another organizer’s event.'
        )
        return redirect('events:organizer_events')

    if event.status in ['cancelled', 'completed']:
        messages.error(
            request,
            'This event is already cancelled or completed.'
        )
        return redirect('events:organizer_events')

    event.status = 'cancelled'
    event.save()

    messages.success(
        request,
        'The event has been cancelled.'
    )

    return redirect('events:organizer_events')


@login_required
def event_review_list(request):
    """
    Administrator's event approval queue.
    """

    if not (
        request.user.is_staff
        or request.user.is_superuser
    ):
        messages.error(
            request,
            'Only administrators can review events.'
        )
        return redirect('core:home')

    events = Event.objects.filter(
        status='pending_review'
    ).select_related(
        'organizer',
        'category'
    ).order_by(
        'submitted_at'
    )

    context = {
        'events': events,
    }

    return render(
        request,
        'events/event_review_list.html',
        context
    )


@login_required
@require_POST
def review_event(request, pk):
    """
    Administrator approves or rejects a submitted event.
    """

    if not (
        request.user.is_staff
        or request.user.is_superuser
    ):
        messages.error(
            request,
            'Only administrators can approve or reject events.'
        )
        return redirect('core:home')

    event = get_object_or_404(
        Event,
        pk=pk,
        status='pending_review'
    )

    decision = request.POST.get('decision', '').strip()
    rejection_reason = request.POST.get(
        'rejection_reason',
        ''
    ).strip()

    if decision == 'approve':
        event.status = 'published'
        event.reviewed_by = request.user
        event.reviewed_at = timezone.now()
        event.published_at = timezone.now()
        event.rejection_reason = ''

        event.save()

        messages.success(
            request,
            f'"{event.title}" has been approved and published.'
        )

    elif decision == 'reject':
        if not rejection_reason:
            messages.error(
                request,
                'Please provide a reason for rejecting this event.'
            )
            return redirect('events:event_review_list')

        event.status = 'rejected'
        event.reviewed_by = request.user
        event.reviewed_at = timezone.now()
        event.rejection_reason = rejection_reason
        event.save()

        messages.warning(
            request,
            f'"{event.title}" has been rejected.'
        )

    else:
        messages.error(
            request,
            'Invalid review decision.'
        )

    return redirect('events:event_review_list')


from decimal import Decimal, InvalidOperation

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import F
from django.utils import timezone

from .models import Event, EventTicketType


def event_booking(request, slug):
    """
    Display available ticket categories and process
    the visitor's initial ticket selection.

    This step saves a temporary selection in the session.
    It does not create an order or confirm a purchase.
    """

    event = get_object_or_404(
        Event,
        slug=slug,
        status='published'
    )

    now = timezone.now()

    if event.end_datetime < now:
        messages.warning(
            request,
            "Ticket booking for this event has closed."
        )
        return redirect(
            'events:event_detail',
            slug=event.slug
        )

    ticket_types = EventTicketType.objects.filter(
        event=event,
        is_active=True,
        quantity_sold__lt=F('quantity_available')
    ).order_by('price')

    if request.method == 'POST':

        selected_tickets = []
        total_quantity = 0
        total_amount = Decimal('0.00')
        selected_currency = None

        for ticket in ticket_types:

            field_name = f'ticket_{ticket.id}'

            raw_quantity = request.POST.get(
                field_name,
                '0'
            )

            try:
                quantity = int(raw_quantity)
            except (TypeError, ValueError):
                messages.error(
                    request,
                    f'Invalid quantity selected for {ticket.name}.'
                )
                return redirect(
                    'events:event_booking',
                    slug=event.slug
                )

            if quantity < 0:
                messages.error(
                    request,
                    'Ticket quantities cannot be negative.'
                )
                return redirect(
                    'events:event_booking',
                    slug=event.slug
                )

            if quantity == 0:
                continue

            if quantity < ticket.minimum_per_order:
                messages.error(
                    request,
                    f'The minimum order for {ticket.name} is '
                    f'{ticket.minimum_per_order}.'
                )
                return redirect(
                    'events:event_booking',
                    slug=event.slug
                )

            if quantity > ticket.maximum_per_order:
                messages.error(
                    request,
                    f'The maximum order for {ticket.name} is '
                    f'{ticket.maximum_per_order}.'
                )
                return redirect(
                    'events:event_booking',
                    slug=event.slug
                )

            if quantity > ticket.remaining_quantity:
                messages.error(
                    request,
                    f'Only {ticket.remaining_quantity} '
                    f'{ticket.name} tickets are remaining.'
                )
                return redirect(
                    'events:event_booking',
                    slug=event.slug
                )

            if (
                ticket.sales_start_at
                and now < ticket.sales_start_at
            ):
                messages.error(
                    request,
                    f'Sales for {ticket.name} have not started yet.'
                )
                return redirect(
                    'events:event_booking',
                    slug=event.slug
                )

            if (
                ticket.sales_end_at
                and now > ticket.sales_end_at
            ):
                messages.error(
                    request,
                    f'Sales for {ticket.name} have closed.'
                )
                return redirect(
                    'events:event_booking',
                    slug=event.slug
                )

            # All selected categories must use the same currency.
            if selected_currency is None:
                selected_currency = ticket.currency

            elif selected_currency != ticket.currency:
                messages.error(
                    request,
                    'Please select ticket categories using the same currency.'
                )
                return redirect(
                    'events:event_booking',
                    slug=event.slug
                )

            subtotal = ticket.price * quantity

            selected_tickets.append({
                'ticket_id': ticket.id,
                'ticket_name': ticket.name,
                'quantity': quantity,
                'unit_price': str(ticket.price),
                'currency': ticket.currency,
                'subtotal': str(subtotal),
            })

            total_quantity += quantity
            total_amount += subtotal

        if not selected_tickets:
            messages.error(
                request,
                'Please select at least one ticket.'
            )
            return redirect(
                'events:event_booking',
                slug=event.slug
            )

        # Save the selection in the visitor's session.
        # This is NOT yet a confirmed purchase.
        session_key = f'booking_selection_{event.id}'

        request.session[session_key] = {
            'event_id': event.id,
            'event_slug': event.slug,
            'tickets': selected_tickets,
            'total_quantity': total_quantity,
            'total_amount': str(total_amount),
            'currency': selected_currency,
        }

        request.session.modified = True

        return redirect(
            'events:checkout',
            slug=event.slug
        )

    context = {
        'event': event,
        'ticket_types': ticket_types,
    }

    return render(
        request,
        'events/event_booking.html',
        context
    )


import re
import logging

from decimal import Decimal, InvalidOperation

import re
import logging

from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Event, EventTicketType
from orders.models import Order, OrderItem


logger = logging.getLogger(__name__)


def normalize_checkout_phone(phone):
    """Normalize Kenyan phone numbers to 254 format."""

    phone = re.sub(r'[\s()+-]', '', phone or '')

    if not re.fullmatch(r'(?:254[17]\d{8}|0[17]\d{8}|[17]\d{8})', phone):
        raise ValueError('Invalid Kenyan phone number.')

    if phone.startswith('0'):
        phone = '254' + phone[1:]

    elif len(phone) == 9:
        phone = '254' + phone

    return phone


def checkout(request, slug):

    event = get_object_or_404(
        Event,
        slug=slug,
        status='published'
    )

    session_key = f'booking_selection_{event.id}'
    customer_key = f'checkout_customer_{event.id}'

    booking = request.session.get(session_key)

    if not booking or not booking.get('tickets'):

        messages.warning(
            request,
            'Please select your tickets before proceeding to checkout.'
        )

        return redirect(
            'events:event_booking',
            slug=event.slug
        )

    # --------------------------------------------------
    # LOAD AND VALIDATE SELECTED TICKETS
    # --------------------------------------------------

    checkout_tickets = []
    total_amount = Decimal('0.00')
    total_quantity = 0

    currency = booking.get('currency', 'KES')

    try:

        for item in booking['tickets']:

            ticket = EventTicketType.objects.get(
                pk=item['ticket_id'],
                event=event,
                is_active=True
            )

            quantity = int(item['quantity'])

            if quantity <= 0:
                raise ValueError('Invalid ticket quantity.')

            if quantity > ticket.remaining_quantity:

                raise ValueError(
                    f'Only {ticket.remaining_quantity} '
                    f'{ticket.name} tickets remain.'
                )

            now = timezone.now()

            if (
                ticket.sales_start_at and
                now < ticket.sales_start_at
            ) or (
                ticket.sales_end_at and
                now > ticket.sales_end_at
            ):

                raise ValueError(
                    f'Ticket sales for {ticket.name} are closed.'
                )

            if ticket.currency != currency:

                raise ValueError(
                    'Ticket currency has changed. '
                    'Please select your tickets again.'
                )

            subtotal = ticket.price * quantity

            checkout_tickets.append({
                'ticket': ticket,
                'quantity': quantity,
                'subtotal': subtotal,
            })

            total_amount += subtotal
            total_quantity += quantity

    except (
        EventTicketType.DoesNotExist,
        ValueError,
        TypeError,
        KeyError
    ) as error:

        messages.error(request, str(error))

        request.session.pop(session_key, None)

        return redirect(
            'events:event_booking',
            slug=event.slug
        )

    # --------------------------------------------------
    # CUSTOMER DETAILS
    # --------------------------------------------------

    saved_customer = request.session.get(customer_key, {})

    form_data = (
        request.POST
        if request.method == 'POST'
        else saved_customer
    )

    details_saved = False

    # --------------------------------------------------
    # PROCESS CHECKOUT
    # --------------------------------------------------

    if request.method == 'POST':

        email = request.POST.get(
            'email', ''
        ).strip().lower()

        full_name = request.POST.get(
            'full_name', ''
        ).strip()

        phone = request.POST.get(
            'phone', ''
        ).strip()

        purchase_for = request.POST.get(
            'purchase_for', 'myself'
        ).strip()

        recipient_name = request.POST.get(
            'recipient_name', ''
        ).strip()

        recipient_email = request.POST.get(
            'recipient_email', ''
        ).strip().lower()

        recipient_phone = request.POST.get(
            'recipient_phone', ''
        ).strip()

        payment_method = request.POST.get(
            'payment_method', ''
        ).strip().lower()

        mpesa_phone = request.POST.get(
            'mpesa_phone', ''
        ).strip()

        terms_accepted = (
            request.POST.get('terms') == 'on'
        )

        errors = []

        # ----------------------------------------------
        # VALIDATE PURCHASER
        # ----------------------------------------------

        if not full_name:
            errors.append('Please enter your full name.')

        elif len(full_name) < 3:
            errors.append('Please enter your full name correctly.')

        try:
            validate_email(email)

        except ValidationError:
            errors.append('Please enter a valid email address.')

        try:
            normalized_phone = normalize_checkout_phone(phone)

        except ValueError:
            normalized_phone = ''
            errors.append('Please enter a valid Kenyan phone number.')

        # ----------------------------------------------
        # VALIDATE RECIPIENT
        # ----------------------------------------------

        if purchase_for not in ['myself', 'someone_else']:

            errors.append('Please select who the tickets are for.')

        if purchase_for == 'someone_else':

            if not recipient_name:
                errors.append('Please enter the recipient name.')

            try:
                validate_email(recipient_email)

            except ValidationError:
                errors.append('Please enter a valid recipient email.')

            try:
                normalized_recipient_phone = normalize_checkout_phone(
                    recipient_phone
                )

            except ValueError:
                normalized_recipient_phone = ''
                errors.append('Please enter a valid recipient phone number.')

        else:

            normalized_recipient_phone = normalized_phone
            recipient_name = full_name
            recipient_email = email

        # ----------------------------------------------
        # VALIDATE PAYMENT METHOD
        # ----------------------------------------------

        if payment_method not in ['mpesa', 'pesapal']:

            errors.append('Please select a valid payment method.')

        normalized_mpesa_phone = ''

        if payment_method == 'mpesa':

            try:
                normalized_mpesa_phone = normalize_checkout_phone(
                    mpesa_phone
                )

            except ValueError:
                errors.append(
                    'Enter a valid M-Pesa number, '
                    'for example 0712345678.'
                )

            if currency != 'KES':

                errors.append(
                    'M-Pesa payments are only supported in KES.'
                )

            if total_amount != total_amount.to_integral_value():

                errors.append(
                    'M-Pesa payments require a whole-number KES amount.'
                )

        elif payment_method == 'pesapal':

            # We will connect this to your actual PesaPal
            # initiation view after reviewing its implementation.
            errors.append(
                'PesaPal checkout integration is not yet connected. '
                'Please select M-Pesa for now.'
            )

        # ----------------------------------------------
        # TERMS AND CONDITIONS
        # ----------------------------------------------

        if not terms_accepted:

            errors.append(
                'You must accept the Terms & Conditions.'
            )

        if total_amount <= Decimal('0.00'):

            errors.append('Invalid booking amount.')

        # ----------------------------------------------
        # DISPLAY VALIDATION ERRORS
        # ----------------------------------------------

        if errors:

            for error in errors:
                messages.error(request, error)

        else:

            # ------------------------------------------
            # CREATE ORDER AND ORDER ITEMS
            # ------------------------------------------

            try:

                with transaction.atomic():

                    locked_tickets = []

                    # Lock ticket categories while checking
                    # availability and creating the order.
                    for item in checkout_tickets:

                        ticket = EventTicketType.objects.select_for_update().get(
                            pk=item['ticket'].pk,
                            event=event,
                            is_active=True
                        )

                        if item['quantity'] > ticket.remaining_quantity:

                            raise ValidationError(
                                f'Not enough tickets remain for {ticket.name}. '
                                'Please update your selection.'
                            )

                        locked_tickets.append({
                            'ticket': ticket,
                            'quantity': item['quantity'],
                        })

                    # Recalculate using current database prices.
                    final_amount = Decimal('0.00')
                    final_quantity = 0

                    for item in locked_tickets:

                        ticket = item['ticket']
                        quantity = item['quantity']

                        final_amount += ticket.price * quantity
                        final_quantity += quantity

                    if final_amount != total_amount:

                        raise ValidationError(
                            'Ticket prices have changed. '
                            'Please review your booking again.'
                        )

                    # Create the actual order.
                    order = Order.objects.create(

                        event=event,

                        user=(
                            request.user
                            if request.user.is_authenticated
                            else None
                        ),

                        customer_name=full_name,

                        customer_email=email,

                        customer_phone=normalized_phone,

                        purchase_for=purchase_for,

                        recipient_name=recipient_name,

                        recipient_email=recipient_email,

                        recipient_phone=normalized_recipient_phone,

                        payment_method=payment_method,

                        mpesa_phone=(
                            normalized_mpesa_phone
                            if payment_method == 'mpesa'
                            else ''
                        ),

                        currency=currency,

                        total_quantity=final_quantity,

                        total_amount=final_amount,

                        status=Order.STATUS_PENDING,

                        terms_accepted=True,

                        terms_accepted_at=timezone.now(),

                    )

                    # Create individual order items.
                    for item in locked_tickets:

                        ticket = item['ticket']
                        quantity = item['quantity']

                        subtotal = ticket.price * quantity

                        OrderItem.objects.create(

                            order=order,

                            ticket_type=ticket,

                            ticket_name=ticket.name,

                            quantity=quantity,

                            unit_price=ticket.price,

                            subtotal=subtotal,

                        )

                # --------------------------------------
                # SAVE ORDER REFERENCE IN SESSION
                # --------------------------------------

                request.session['last_order_reference'] = (
                    order.reference
                )

                request.session.modified = True

                logger.info(
                    'ShikaTicko order created: %s',
                    order.reference
                )

                # --------------------------------------
                # INITIATE M-PESA
                # --------------------------------------

                if payment_method == 'mpesa':

                    return render(
                        request,
                        'payments/mpesa_redirect.html',
                        {
                            'order': order,
                        }
                    )

            except ValidationError as error:

                messages.error(
                    request,
                    str(error)
                )

            except Exception:

                logger.exception(
                    'Checkout order creation failed for event %s',
                    event.id
                )

                messages.error(
                    request,
                    'We could not create your order. '
                    'Please try again.'
                )

    # --------------------------------------------------
    # PAGE CONTEXT
    # --------------------------------------------------

    context = {

        'event': event,

        'checkout_tickets': checkout_tickets,

        'total_quantity': total_quantity,

        'total_amount': total_amount,

        'currency': currency,

        'form_data': form_data,

        'details_saved': details_saved,

    }

    return render(
        request,
        'events/checkout.html',
        context
    )