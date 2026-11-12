"""
Forms for ShopSense Vendors app.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import VendorApplication, VendorProfile


class VendorApplicationForm(forms.ModelForm):
    """Form for vendor onboarding application."""

    class Meta:
        model = VendorApplication
        fields = [
            'business_name',
            'business_description',
            'contact_email',
            'contact_phone',
            'business_address',
            'city',
            'state',
            'postal_code',
            'country',
            'tax_id',
            'website',
            'logo',
            'banner',
        ]
        widgets = {
            'business_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Enter your business name',
                'required': True,
            }),
            'business_description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'placeholder': 'Describe your business, products, and services',
                'rows': 4,
            }),
            'contact_email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'contact@yourbusiness.com',
                'required': True,
            }),
            'contact_phone': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+91 98765 43210',
            }),
            'business_address': forms.Textarea(attrs={
                'class': 'form-textarea',
                'placeholder': 'Full business address',
                'rows': 3,
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'City',
                'required': True,
            }),
            'state': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'State/Province',
                'required': True,
            }),
            'postal_code': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Postal/ZIP Code',
                'required': True,
            }),
            'country': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Country',
                'required': True,
            }),
            'tax_id': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'GST/PAN Number',
                'required': True,
            }),
            'website': forms.URLInput(attrs={
                'class': 'form-input',
                'placeholder': 'https://www.yourbusiness.com',
            }),
            'logo': forms.FileInput(attrs={
                'class': 'form-file-input',
                'accept': 'image/*',
            }),
            'banner': forms.FileInput(attrs={
                'class': 'form-file-input',
                'accept': 'image/*',
            }),
        }

    def clean_contact_email(self):
        email = self.cleaned_data['contact_email'].lower()
        # Check if there's already a pending application with this email
        if VendorApplication.objects.filter(
            contact_email__iexact=email,
            status__in=[VendorApplication.Status.PENDING, VendorApplication.Status.MORE_INFO]
        ).exists():
            raise forms.ValidationError(
                _('There is already a pending application with this email address.')
            )
        return email


class VendorProfileForm(forms.ModelForm):
    """Form for updating vendor profile."""

    class Meta:
        model = VendorProfile
        fields = [
            'business_name',
            'business_description',
            'contact_email',
            'contact_phone',
            'business_address',
            'city',
            'state',
            'postal_code',
            'country',
            'tax_id',
            'website',
            'logo',
            'banner',
        ]
        widgets = {
            'business_name': forms.TextInput(attrs={'class': 'form-input'}),
            'business_description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 4}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-input'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-input'}),
            'business_address': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'city': forms.TextInput(attrs={'class': 'form-input'}),
            'state': forms.TextInput(attrs={'class': 'form-input'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-input'}),
            'country': forms.TextInput(attrs={'class': 'form-input'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-input'}),
            'website': forms.URLInput(attrs={'class': 'form-input'}),
            'logo': forms.FileInput(attrs={'class': 'form-file-input', 'accept': 'image/*'}),
            'banner': forms.FileInput(attrs={'class': 'form-file-input', 'accept': 'image/*'}),
        }


class AdminVendorActionForm(forms.Form):
    """Form for admin actions on vendor applications."""

    ACTION_CHOICES = [
        ('approve', _('Approve')),
        ('reject', _('Reject')),
        ('more_info', _('Request More Information')),
    ]

    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-radio'}),
    )
    notes = forms.CharField(
        label=_('Admin Notes'),
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea',
            'placeholder': 'Optional notes for the vendor...',
            'rows': 3,
        }),
    )