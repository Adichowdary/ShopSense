"""
Models for ShopSense Vendors app.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import User


class VendorApplication(models.Model):
    """Model for vendor onboarding applications."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending Review')
        APPROVED = 'APPROVED', _('Approved')
        REJECTED = 'REJECTED', _('Rejected')
        MORE_INFO = 'MORE_INFO', _('More Information Required')

    # Application details
    business_name = models.CharField(_('business name'), max_length=255)
    business_description = models.TextField(_('business description'), blank=True)
    contact_email = models.EmailField(_('contact email'))
    contact_phone = models.CharField(_('contact phone'), max_length=20, blank=True)
    business_address = models.TextField(_('business address'), blank=True)
    city = models.CharField(_('city'), max_length=100, blank=True)
    state = models.CharField(_('state'), max_length=100, blank=True)
    postal_code = models.CharField(_('postal code'), max_length=20, blank=True)
    country = models.CharField(_('country'), max_length=100, default='India')
    tax_id = models.CharField(_('tax ID (GST/PAN)'), max_length=50, blank=True)
    website = models.URLField(_('website'), blank=True)
    logo = models.ImageField(_('logo'), upload_to='vendor_logos/', blank=True, null=True)
    banner = models.ImageField(_('banner'), upload_to='vendor_banners/', blank=True, null=True)

    # Status tracking
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    vendor_id = models.CharField(_('vendor ID'), max_length=20, unique=True, blank=True)
    admin_notes = models.TextField(_('admin notes'), blank=True)

    # Timestamps
    submitted_at = models.DateTimeField(_('submitted at'), default=timezone.now)
    reviewed_at = models.DateTimeField(_('reviewed at'), null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_applications',
        verbose_name=_('reviewed by'),
    )

    class Meta:
        verbose_name = _('vendor application')
        verbose_name_plural = _('vendor applications')
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['contact_email']),
            models.Index(fields=['submitted_at']),
        ]

    def __str__(self):
        return f'{self.business_name} ({self.get_status_display()})'

    def save(self, *args, **kwargs):
        if not self.vendor_id:
            self.vendor_id = self.generate_vendor_id()
        super().save(*args, **kwargs)

    def generate_vendor_id(self):
        """Generate a unique vendor ID."""
        from django.conf import settings
        prefix = getattr(settings, 'VENDOR_ID_PREFIX', 'VND')
        length = getattr(settings, 'VENDOR_ID_LENGTH', 8)
        import random
        import string
        while True:
            suffix = ''.join(random.choices(string.digits, k=length))
            vendor_id = f'{prefix}{suffix}'
            if not VendorApplication.objects.filter(vendor_id=vendor_id).exists():
                return vendor_id

    def approve(self, reviewed_by, notes=''):
        """Approve the vendor application."""
        from django.db import transaction
        with transaction.atomic():
            self.status = self.Status.APPROVED
            self.reviewed_at = timezone.now()
            self.reviewed_by = reviewed_by
            self.admin_notes = notes
            self.save()

            # Create VendorProfile and update User role
            VendorProfile.objects.create(
                user=self.applicant_user,
                vendor_id=self.vendor_id,
                business_name=self.business_name,
                business_description=self.business_description,
                contact_email=self.contact_email,
                contact_phone=self.contact_phone,
                business_address=self.business_address,
                city=self.city,
                state=self.state,
                postal_code=self.postal_code,
                country=self.country,
                tax_id=self.tax_id,
                website=self.website,
                logo=self.logo,
                banner=self.banner,
                is_active=True,
            )
            self.applicant_user.role = User.Role.VENDOR
            self.applicant_user.save(update_fields=['role'])

    def reject(self, reviewed_by, notes=''):
        """Reject the vendor application."""
        self.status = self.Status.REJECTED
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewed_by
        self.admin_notes = notes
        self.save()

    def request_more_info(self, reviewed_by, notes=''):
        """Request more information from vendor."""
        self.status = self.Status.MORE_INFO
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewed_by
        self.admin_notes = notes
        self.save()

    @property
    def applicant_user(self):
        """Get or create the user associated with this application."""
        user, _created = User.objects.get_or_create(
            email=self.contact_email,
            defaults={
                'first_name': self.business_name.split()[0] if self.business_name else 'Vendor',
                'last_name': 'Applicant',
                'role': User.Role.VENDOR,
                'is_active': False,  # Will be activated on approval
            }
        )
        return user


class VendorProfile(models.Model):
    """Model for approved vendor profiles."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vendor_profile',
        verbose_name=_('user'),
    )
    vendor_id = models.CharField(_('vendor ID'), max_length=20, unique=True)
    business_name = models.CharField(_('business name'), max_length=255)
    business_description = models.TextField(_('business description'), blank=True)
    contact_email = models.EmailField(_('contact email'))
    contact_phone = models.CharField(_('contact phone'), max_length=20, blank=True)
    business_address = models.TextField(_('business address'), blank=True)
    city = models.CharField(_('city'), max_length=100, blank=True)
    state = models.CharField(_('state'), max_length=100, blank=True)
    postal_code = models.CharField(_('postal code'), max_length=20, blank=True)
    country = models.CharField(_('country'), max_length=100, default='India')
    tax_id = models.CharField(_('tax ID (GST/PAN)'), max_length=50, blank=True)
    website = models.URLField(_('website'), blank=True)
    logo = models.ImageField(_('logo'), upload_to='vendor_logos/', blank=True, null=True)
    banner = models.ImageField(_('banner'), upload_to='vendor_banners/', blank=True, null=True)
    is_active = models.BooleanField(_('active'), default=True)
    is_verified = models.BooleanField(_('verified'), default=False)
    commission_rate = models.DecimalField(
        _('commission rate (%)'),
        max_digits=5,
        decimal_places=2,
        default=10.00,
    )
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('vendor profile')
        verbose_name_plural = _('vendor profiles')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor_id']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_verified']),
        ]

    def __str__(self):
        return f'{self.business_name} ({self.vendor_id})'

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('vendors:detail', kwargs={'vendor_id': self.vendor_id})


class AuditLog(models.Model):
    """Audit log for sensitive administrative actions."""

    class ActionType(models.TextChoices):
        VENDOR_APPROVED = 'VENDOR_APPROVED', _('Vendor Approved')
        VENDOR_REJECTED = 'VENDOR_REJECTED', _('Vendor Rejected')
        VENDOR_SUSPENDED = 'VENDOR_SUSPENDED', _('Vendor Suspended')
        USER_ROLE_CHANGED = 'USER_ROLE_CHANGED', _('User Role Changed')
        USER_DEACTIVATED = 'USER_DEACTIVATED', _('User Deactivated')
        SETTINGS_CHANGED = 'SETTINGS_CHANGED', _('Settings Changed')
        ORDER_STATUS_CHANGED = 'ORDER_STATUS_CHANGED', _('Order Status Changed')
        ORDER_CANCELLED = 'ORDER_CANCELLED', _('Order Cancelled')
        ORDER_REFUNDED = 'ORDER_REFUNDED', _('Order Refunded')
        ORDER_ITEM_FULFILLED = 'ORDER_ITEM_FULFILLED', _('Order Item Fulfilled')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name=_('performed by'),
    )
    action = models.CharField(_('action'), max_length=50, choices=ActionType.choices)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs_target',
        verbose_name=_('target user'),
    )
    target_vendor = models.ForeignKey(
        'VendorProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name=_('target vendor'),
    )
    details = models.JSONField(_('details'), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_('IP address'), null=True, blank=True)
    user_agent = models.TextField(_('user agent'), blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)

    class Meta:
        verbose_name = _('audit log')
        verbose_name_plural = _('audit logs')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['action']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.get_action_display()} by {self.user} at {self.created_at}'