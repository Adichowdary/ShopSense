"""
Forms for ShopSense Accounts app.
"""

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import User


class LoginForm(AuthenticationForm):
    """Custom login form with email instead of username."""

    username = forms.EmailField(
        label=_('Email Address'),
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your email address',
            'autocomplete': 'email',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        label=_('Password'),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs['aria-label'] = 'Email Address'
        self.fields['password'].widget.attrs['aria-label'] = 'Password'

    def clean(self):
        """Authenticate user with email and password."""
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password,
            )
            if self.user_cache is None:
                raise ValidationError(
                    _('Invalid email or password.'),
                    code='invalid_login',
                )
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data

    def confirm_login_allowed(self, user):
        """Check if user is allowed to log in."""
        if user.is_locked():
            raise ValidationError(
                _('This account is temporarily locked due to too many failed login attempts. '
                  'Please try again in 15 minutes.'),
                code='account_locked',
            )


class RegistrationForm(UserCreationForm):
    """Custom registration form."""

    email = forms.EmailField(
        label=_('Email Address'),
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your email address',
            'autocomplete': 'email',
        })
    )
    first_name = forms.CharField(
        label=_('First Name'),
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your first name',
            'autocomplete': 'given-name',
        })
    )
    last_name = forms.CharField(
        label=_('Last Name'),
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your last name',
            'autocomplete': 'family-name',
        })
    )
    phone = forms.CharField(
        label=_('Phone Number'),
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your phone number (optional)',
            'autocomplete': 'tel',
        })
    )
    role = forms.ChoiceField(
        label=_('Register As'),
        choices=User.Role.choices,
        initial=User.Role.CUSTOMER,
        widget=forms.Select(attrs={
            'class': 'form-select',
        })
    )
    password1 = forms.CharField(
        label=_('Password'),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Create a password',
            'autocomplete': 'new-password',
        }),
        help_text=_('Must be at least 10 characters with uppercase, lowercase, digit, and special character.')
    )
    password2 = forms.CharField(
        label=_('Confirm Password'),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Confirm your password',
            'autocomplete': 'new-password',
        }),
    )

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'phone', 'role', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Restrict role choices for public registration
        self.fields['role'].choices = [
            (User.Role.CUSTOMER, _('Customer')),
            (User.Role.VENDOR, _('Vendor')),
        ]

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError(_('An account with this email already exists.'))
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email'].lower()
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.phone = self.cleaned_data['phone']
        user.role = self.cleaned_data['role']
        if commit:
            user.save()
        return user


class CustomPasswordResetForm(PasswordResetForm):
    """Custom password reset form."""

    email = forms.EmailField(
        label=_('Email Address'),
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your registered email address',
            'autocomplete': 'email',
        })
    )

    def get_users(self, email):
        """Return users matching the email."""
        return User.objects.filter(email__iexact=email, is_active=True)


class CustomSetPasswordForm(SetPasswordForm):
    """Custom set password form."""

    new_password1 = forms.CharField(
        label=_('New Password'),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter new password',
            'autocomplete': 'new-password',
        }),
    )
    new_password2 = forms.CharField(
        label=_('Confirm New Password'),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password',
        }),
    )


class CustomPasswordChangeForm(PasswordChangeForm):
    """Custom password change form."""

    old_password = forms.CharField(
        label=_('Current Password'),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter current password',
            'autocomplete': 'current-password',
        }),
    )
    new_password1 = forms.CharField(
        label=_('New Password'),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter new password',
            'autocomplete': 'new-password',
        }),
    )
    new_password2 = forms.CharField(
        label=_('Confirm New Password'),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password',
        }),
    )


class ProfileUpdateForm(forms.ModelForm):
    """Form for updating user profile."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'First name',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Last name',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Phone number',
            }),
        }