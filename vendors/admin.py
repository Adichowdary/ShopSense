"""
Admin configuration for ShopSense Vendors app.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import AuditLog, VendorApplication, VendorProfile


@admin.register(VendorApplication)
class VendorApplicationAdmin(admin.ModelAdmin):
    list_display = (
        'vendor_id',
        'business_name',
        'contact_email',
        'status',
        'submitted_at',
        'reviewed_at',
    )
    list_filter = ('status', 'submitted_at', 'reviewed_at')
    search_fields = ('business_name', 'contact_email', 'vendor_id', 'tax_id')
    readonly_fields = ('vendor_id', 'submitted_at', 'reviewed_at', 'reviewed_by')
    ordering = ('-submitted_at',)
    date_hierarchy = 'submitted_at'

    fieldsets = (
        (None, {'fields': ('vendor_id', 'status', 'submitted_at', 'reviewed_at', 'reviewed_by')}),
        (_('Business Information'), {
            'fields': ('business_name', 'business_description', 'website', 'tax_id')
        }),
        (_('Contact Information'), {
            'fields': ('contact_email', 'contact_phone', 'business_address', 'city', 'state', 'postal_code', 'country')
        }),
        (_('Admin Review'), {
            'fields': ('admin_notes',),
            'classes': ('collapse',),
        }),
    )

    def has_add_permission(self, request):
        return False  # Applications are created via public form only


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display = (
        'vendor_id',
        'business_name',
        'contact_email',
        'user',
        'is_active',
        'is_verified',
        'commission_rate',
        'created_at',
    )
    list_filter = ('is_active', 'is_verified', 'created_at')
    search_fields = ('business_name', 'contact_email', 'vendor_id', 'user__email')
    readonly_fields = ('vendor_id', 'created_at', 'updated_at')
    ordering = ('-created_at',)

    fieldsets = (
        (None, {'fields': ('vendor_id', 'user', 'is_active', 'is_verified', 'commission_rate')}),
        (_('Business Information'), {
            'fields': ('business_name', 'business_description', 'website', 'tax_id', 'logo', 'banner')
        }),
        (_('Contact Information'), {
            'fields': ('contact_email', 'contact_phone', 'business_address', 'city', 'state', 'postal_code', 'country')
        }),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'action',
        'user',
        'target_user',
        'target_vendor',
        'created_at',
    )
    list_filter = ('action', 'created_at')
    search_fields = ('user__email', 'target_user__email', 'details')
    readonly_fields = ('user', 'action', 'target_user', 'target_vendor', 'details', 'ip_address', 'user_agent', 'created_at')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False