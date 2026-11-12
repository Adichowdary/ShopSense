"""
Custom User Model for ShopSense.

This replaces Django's default User model with a custom implementation
that uses email as the unique identifier instead of username.
"""

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Custom manager for User model."""

    def create_user(self, email, password=None, **extra_fields):
        """Create and return a regular user with an email and password."""
        if not email:
            raise ValueError(_('The Email field must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and return a superuser with an email and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', User.Role.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model using email as the unique identifier."""

    class Role(models.TextChoices):
        ADMIN = 'ADMIN', _('Administrator')
        VENDOR = 'VENDOR', _('Vendor')
        CUSTOMER = 'CUSTOMER', _('Customer')

    email = models.EmailField(_('email address'), unique=True)
    first_name = models.CharField(_('first name'), max_length=150)
    last_name = models.CharField(_('last name'), max_length=150)
    role = models.CharField(
        _('role'),
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
    )
    phone = models.CharField(_('phone number'), max_length=20, blank=True)
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    is_active = models.BooleanField(_('active'), default=True)
    is_staff = models.BooleanField(_('staff status'), default=False)
    last_login_ip = models.GenericIPAddressField(_('last login IP'), null=True, blank=True)
    failed_login_attempts = models.PositiveIntegerField(_('failed login attempts'), default=0)
    locked_until = models.DateTimeField(_('locked until'), null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-date_joined']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        """Ensure email is always normalized to lowercase."""
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)

    def get_full_name(self):
        """Return the first_name plus the last_name, with a space in between."""
        full_name = f'{self.first_name} {self.last_name}'
        return full_name.strip()

    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name

    def is_admin(self):
        """Check if user is an administrator."""
        return self.role == self.Role.ADMIN or self.is_superuser

    def is_vendor(self):
        """Check if user is a vendor."""
        return self.role == self.Role.VENDOR

    def is_customer(self):
        """Check if user is a customer."""
        return self.role == self.Role.CUSTOMER

    def can_access_admin_dashboard(self):
        """Check if user can access admin dashboard."""
        return self.is_admin() and self.is_active and self.is_staff

    def can_access_vendor_dashboard(self):
        """Check if user can access vendor dashboard."""
        return self.is_vendor() and self.is_active

    def increment_failed_login(self):
        """Increment failed login attempts."""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            from datetime import timedelta
            self.locked_until = timezone.now() + timedelta(minutes=15)
        self.save(update_fields=['failed_login_attempts', 'locked_until'])

    def reset_failed_login(self):
        """Reset failed login attempts."""
        self.failed_login_attempts = 0
        self.locked_until = None
        self.save(update_fields=['failed_login_attempts', 'locked_until'])

    def is_locked(self):
        """Check if account is locked."""
        return bool(self.locked_until and self.locked_until > timezone.now())