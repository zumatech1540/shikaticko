
from django.shortcuts import render, redirect
from django.contrib import messages

from .models import ContactMessage, FAQ
from .forms import ContactForm
from django.utils import timezone
from events.models import Event

def home(request):
    featured_events = Event.objects.filter(
        status='published',
        end_datetime__gte=timezone.now()
    ).select_related(
        'category',
        'organizer'
    ).order_by(
        '-is_featured',
        'start_datetime'
    )[:6]

    context = {
        'featured_events': featured_events,
    }

    return render(
        request,
        'core/home.html',
        context
    )


def about(request):
    return render(request, 'core/about.html')


def competitions(request):
    events = Event.objects.filter(
        status='published'
    ).select_related(
        'category',
        'organizer'
    ).order_by(
        'start_datetime'
    )

    context = {
        'events': events,
    }

    return render(
        request,
        'core/competitions.html',
        context
    )


def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)

        if form.is_valid():
            form.save()

            messages.success(
                request,
                'Your message has been sent successfully. '
                'Our team will get back to you soon.'
            )

            return redirect('core:contact')

        else:
            messages.error(
                request,
                'Please correct the errors below and try again.'
            )

    else:
        form = ContactForm()

    context = {
        'form': form,
    }

    return render(request, 'core/contact.html', context)


def faq(request):
    faqs = FAQ.objects.filter(
        is_active=True
    ).order_by('order', 'id')

    context = {
        'faqs': faqs,
    }

    return render(request, 'core/faq.html', context)

