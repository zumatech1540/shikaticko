from django.contrib import admin

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):

    list_display = (
        'username',
        'first_name',
        'last_name',
        'email',
        'phone',
        'role',
        'is_active',
        'is_staff',
    )

    list_filter = (
        'role',
        'is_active',
        'is_staff',
        'date_joined',
    )

    search_fields = (
        'username',
        'first_name',
        'last_name',
        'email',
        'phone',
    )

    fieldsets = UserAdmin.fieldsets + (
        (
            'Platform Information',
            {
                'fields': (
                    'phone',
                    'role',
                    'created_at',
                    'updated_at',
                )
            }
        ),
    )

    readonly_fields = (
        'created_at',
        'updated_at',
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            'Platform Information',
            {
                'fields': (
                    'email',
                    'first_name',
                    'last_name',
                    'phone',
                    'role',
                )
            }
        ),
    )
