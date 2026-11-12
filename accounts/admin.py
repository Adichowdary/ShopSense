"""
Admin configuration for ShopSense Accounts app.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for custom User model."""

    list_display = (
        'email',
        'get_full_name',
        'role',
        'is_active',
        'is_staff',
        'date_joined',
        'last_login',
    )
    list_filter = (
        'role',
        'is_active',
        'is_staff',
        'is_superuser',
        'date_joined',
    )
    search_fields = ('email', 'first_name', 'last_name', 'phone')
    ordering = ('-date_joined',)
    readonly_fields = ('date_joined', 'last_login', 'last_login_ip', 'failed_login_attempts', 'locked_until')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal Info'), {'fields': ('first_name', 'last_name', 'phone')}),
        (_('Role & Permissions'), {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Security'), {
            'fields': ('last_login_ip', 'failed_login_attempts', 'locked_until'),
            'classes': ('collapse',),
        }),
        (_('Important Dates'), {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'phone', 'role', 'password1', 'password2'),
        }),
    )

    def get_full_name(self, obj):
        return obj.get_full_name()
    get_full_name.short_description = _('Full Name')