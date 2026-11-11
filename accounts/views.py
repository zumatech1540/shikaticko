
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from events.models import Event, EventCategory

from .forms import (
    CustomerRegistrationForm,
    OrganizerRegistrationForm,
    UserLoginForm
)


User = get_user_model()


# ==========================================
# ROLE-BASED REDIRECTS
# ==========================================

def redirect_user_by_role(user):

    if (
        user.is_superuser
        or user.is_staff
        or user.role == 'staff'
    ):
        return redirect('accounts:admin_dashboard')

    if user.role == 'organizer':
        return redirect('accounts:organizer_dashboard')

    return redirect('core:home')


# ==========================================
# CUSTOMER REGISTRATION
# ==========================================

def register(request):

    if request.user.is_authenticated:
        return redirect_user_by_role(request.user)

    if request.method == 'POST':
        form = CustomerRegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()

            login(request, user)

            messages.success(
                request,
                'Your customer account has been created successfully.'
            )

            return redirect('core:home')

        messages.error(
            request,
            'Please correct the errors below.'
        )

    else:
        form = CustomerRegistrationForm()

    return render(
        request,
        'accounts/register.html',
        {
            'form': form,
            'page_title': 'Create Customer Account',
            'account_type': 'customer',
        }
    )


# ==========================================
# ORGANIZER REGISTRATION
# ==========================================

def organizer_register(request):

    if request.user.is_authenticated:
        return redirect_user_by_role(request.user)

    if request.method == 'POST':
        form = OrganizerRegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()

            login(request, user)

            messages.success(
                request,
                'Your organizer account has been created successfully.'
            )

            return redirect('accounts:organizer_dashboard')

        messages.error(
            request,
            'Please correct the errors below.'
        )

    else:
        form = OrganizerRegistrationForm()

    return render(
        request,
        'accounts/register.html',
        {
            'form': form,
            'page_title': 'Create Organizer Account',
            'account_type': 'organizer',
        }
    )


# ==========================================
# USER LOGIN
# ==========================================

def user_login(request):

    if request.user.is_authenticated:
        return redirect_user_by_role(request.user)

    if request.method == 'POST':

        form = UserLoginForm(
            request=request,
            data=request.POST
        )

        if form.is_valid():

            user = form.get_user()

            login(request, user)

            messages.success(
                request,
                f'Welcome back, {user.first_name or user.username}!'
            )

            next_url = request.POST.get('next')

            if next_url:
                return redirect(next_url)

            return redirect_user_by_role(user)

        messages.error(
            request,
            'Invalid username or password.'
        )

    else:
        form = UserLoginForm(request=request)

    return render(
        request,
        'accounts/login.html',
        {
            'form': form,
            'next': request.GET.get('next', ''),
        }
    )


# ==========================================
# USER LOGOUT
# ==========================================

@login_required
@require_POST
def user_logout(request):

    logout(request)

    messages.success(
        request,
        'You have been logged out successfully.'
    )

    return redirect('core:home')


# ==========================================
# ADMIN DASHBOARD
# ==========================================

@login_required
def admin_dashboard(request):

    # Protect the administrator dashboard.
    if not (
        request.user.is_superuser
        or request.user.is_staff
        or request.user.role == 'staff'
    ):

        messages.error(
            request,
            'You do not have permission to access the admin dashboard.'
        )

        return redirect_user_by_role(request.user)

    pending_events = Event.objects.filter(
        status='pending_review'
    )

    context = {

        'total_events': Event.objects.count(),

        'published_events': Event.objects.filter(
            status='published'
        ).count(),

        'pending_events_count': pending_events.count(),

        'rejected_events': Event.objects.filter(
            status='rejected'
        ).count(),

        'total_organizers': User.objects.filter(
            role='organizer'
        ).count(),

        'total_customers': User.objects.filter(
            role='customer'
        ).count(),

        'total_categories': EventCategory.objects.count(),

        'recent_events': Event.objects.select_related(
            'organizer',
            'category'
        ).order_by('-created_at')[:8],

        'events_awaiting_approval': pending_events.select_related(
            'organizer',
            'category'
        ).order_by('-submitted_at')[:8],

    }

    return render(
        request,
        'accounts/admin_dashboard.html',
        context
    )


# ==========================================
# ORGANIZER DASHBOARD
# ==========================================

@login_required
def organizer_dashboard(request):

    # Only organizers can access this dashboard.
    if request.user.role != 'organizer':

        messages.error(
            request,
            'This dashboard is only available to event organizers.'
        )

        return redirect_user_by_role(request.user)

    # Organizers can only see their own events.
    my_events = Event.objects.filter(
        organizer=request.user
    )

    context = {

        'total_events': my_events.count(),

        'published_events': my_events.filter(
            status='published'
        ).count(),

        'pending_events': my_events.filter(
            status='pending_review'
        ).count(),

        'draft_events': my_events.filter(
            status='draft'
        ).count(),

        'rejected_events': my_events.filter(
            status='rejected'
        ).count(),

        'recent_events': my_events.select_related(
            'category'
        ).order_by('-created_at')[:10],

    }

    return render(
        request,
        'accounts/organizer_dashboard.html',
        context
    )
