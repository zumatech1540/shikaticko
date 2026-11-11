from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet

from .models import (
    Event,
    EventImage,
    EventCategory,
    EventTicketType,
)


class EventForm(forms.ModelForm):

    class Meta:
        model = Event

        fields = [
            'category',
            'title',
            'short_description',
            'description',
            'cover_image',
            'event_type',
            'entry_type',
            'start_datetime',
            'end_datetime',
            'registration_deadline',
            'timezone',
            'venue_name',
            'venue_address',
            'town',
            'county',
            'google_maps_url',
            'online_event_url',
            'capacity',
        ]

        widgets = {
            'category': forms.Select(attrs={
                'class': 'form-select',
            }),

            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter event title',
            }),

            'short_description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Briefly describe your event',
                'maxlength': 500,
            }),

            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Provide full details about your event',
            }),

            'cover_image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),

            'event_type': forms.Select(attrs={
                'class': 'form-select',
            }),

            'entry_type': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_entry_type',
            }),

            'start_datetime': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),

            'end_datetime': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),

            'registration_deadline': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),

            'timezone': forms.TextInput(attrs={
                'class': 'form-control',
                'value': 'Africa/Nairobi',
            }),

            'venue_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Venue name',
            }),

            'venue_address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Physical venue address',
            }),

            'town': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Town or city',
            }),

            'county': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'County',
            }),

            'google_maps_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'Google Maps location link',
            }),

            'online_event_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'Online meeting or streaming link',
            }),

            'capacity': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Maximum attendees',
                'min': 1,
            }),
        }

        labels = {
            'category': 'Event Category',
            'title': 'Event Title',
            'short_description': 'Short Description',
            'description': 'Full Event Description',
            'cover_image': 'Event Poster / Cover Image',
            'event_type': 'Event Format',
            'entry_type': 'Entry Type',
            'start_datetime': 'Event Start Date and Time',
            'end_datetime': 'Event End Date and Time',
            'registration_deadline': 'Registration Deadline',
            'timezone': 'Event Timezone',
            'venue_name': 'Venue Name',
            'venue_address': 'Venue Address',
            'town': 'Town / City',
            'county': 'County',
            'google_maps_url': 'Google Maps Link',
            'online_event_url': 'Online Event Link',
            'capacity': 'Maximum Attendance',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['category'].queryset = EventCategory.objects.filter(
            is_active=True
        )

        optional_fields = [
            'cover_image',
            'registration_deadline',
            'venue_name',
            'venue_address',
            'town',
            'county',
            'google_maps_url',
            'online_event_url',
            'capacity',
        ]

        for field_name in optional_fields:
            self.fields[field_name].required = False

        self.fields['timezone'].initial = 'Africa/Nairobi'
        self.fields['category'].empty_label = 'Select an event category'

    def clean(self):
        cleaned_data = super().clean()

        start_datetime = cleaned_data.get('start_datetime')
        end_datetime = cleaned_data.get('end_datetime')
        registration_deadline = cleaned_data.get(
            'registration_deadline'
        )

        event_type = cleaned_data.get('event_type')
        venue_name = cleaned_data.get('venue_name')
        online_event_url = cleaned_data.get('online_event_url')

        if start_datetime and end_datetime:
            if end_datetime <= start_datetime:
                self.add_error(
                    'end_datetime',
                    'The event end time must be after the start time.'
                )

        if registration_deadline and start_datetime:
            if registration_deadline > start_datetime:
                self.add_error(
                    'registration_deadline',
                    'The registration deadline cannot be after the event starts.'
                )

        if event_type == 'physical' and not venue_name:
            self.add_error(
                'venue_name',
                'Please provide the physical event venue.'
            )

        if event_type == 'online' and not online_event_url:
            self.add_error(
                'online_event_url',
                'Please provide the online event link.'
            )

        if event_type == 'hybrid':
            if not venue_name:
                self.add_error(
                    'venue_name',
                    'Please provide the physical event venue.'
                )

            if not online_event_url:
                self.add_error(
                    'online_event_url',
                    'Please provide the online event link.'
                )

        return cleaned_data


# ==========================================================
# TICKET CATEGORY FORM
# ==========================================================

class EventTicketTypeForm(forms.ModelForm):

    class Meta:
        model = EventTicketType

        fields = [
            'name',
            'description',
            'price',
            'currency',
            'quantity_available',
            'minimum_per_order',
            'maximum_per_order',
            'sales_start_at',
            'sales_end_at',
            'is_active',
        ]

        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Regular, VIP, VVIP',
            }),

            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Describe what this ticket includes',
            }),

            'price': forms.NumberInput(attrs={
                'class': 'form-control ticket-price',
                'min': '0',
                'step': '0.01',
                'placeholder': 'Ticket price',
            }),

            'currency': forms.Select(attrs={
                'class': 'form-select',
            }),

            'quantity_available': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'Number of tickets',
            }),

            'minimum_per_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
            }),

            'maximum_per_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
            }),

            'sales_start_at': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),

            'sales_end_at': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),

            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['description'].required = False
        self.fields['sales_start_at'].required = False
        self.fields['sales_end_at'].required = False
        self.fields['currency'].initial = 'KES'
        self.fields['quantity_available'].initial = 100
        self.fields['minimum_per_order'].initial = 1
        self.fields['maximum_per_order'].initial = 10
        self.fields['is_active'].initial = True


# ==========================================================
# TICKET FORMSET VALIDATION
# ==========================================================

class BaseEventTicketTypeFormSet(BaseInlineFormSet):

    def clean(self):
        super().clean()

        if any(self.errors):
            return

        active_tickets = 0

        for form in self.forms:

            if not form.cleaned_data:
                continue

            if form.cleaned_data.get('DELETE'):
                continue

            name = form.cleaned_data.get('name')
            price = form.cleaned_data.get('price')

            if not name:
                continue

            active_tickets += 1

            if (
                self.instance.entry_type == 'free'
                and price is not None
                and price > 0
            ):
                form.add_error(
                    'price',
                    'Free events cannot have paid ticket categories.'
                )

        if active_tickets == 0:
            raise forms.ValidationError(
                'Please add at least one ticket category.'
            )


# ==========================================================
# INLINE TICKET FORMSET
# ==========================================================

EventTicketTypeFormSet = inlineformset_factory(
    Event,
    EventTicketType,
    form=EventTicketTypeForm,
    formset=BaseEventTicketTypeFormSet,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
    max_num=10,
    validate_max=True,
)


# ==========================================================
# EVENT GALLERY IMAGE FORM
# ==========================================================

class EventImageForm(forms.ModelForm):

    class Meta:
        model = EventImage

        fields = [
            'image',
            'caption',
            'display_order',
        ]

        widgets = {
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),

            'caption': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Image caption (optional)',
            }),

            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
            }),
        }