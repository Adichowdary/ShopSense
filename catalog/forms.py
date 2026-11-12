"""
Forms for ShopSense Catalog app.
"""

from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from PIL import Image

from vendors.models import VendorProfile
from .models import Category, Inventory, Product, ProductImage

MAX_IMAGE_SIZE_MB = 5
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}


def validate_image_file(image_file):
    """Validate uploaded image file type and size."""
    if not image_file:
        return
    
    # Check file size
    if image_file.size > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError(
            _('Image file size exceeds the %(max_mb)sMB limit. Current size: %(curr_mb).1fMB') % {
                'max_mb': MAX_IMAGE_SIZE_MB,
                'curr_mb': image_file.size / (1024 * 1024),
            }
        )
    
    # Check file extension
    ext = image_file.name.split('.')[-1].lower() if '.' in image_file.name else ''
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(
            _('Unsupported file format (.%(ext)s). Allowed formats: %(allowed)s') % {
                'ext': ext,
                'allowed': ', '.join(ALLOWED_IMAGE_EXTENSIONS),
            }
        )
    
    # Verify image integrity with PIL
    try:
        image = Image.open(image_file)
        image.verify()
        # Reset file pointer after verify()
        image_file.seek(0)
    except Exception:
        raise ValidationError(_('Uploaded file is not a valid image.'))


class ProductForm(forms.ModelForm):
    """Form for creating and updating products."""

    # Optional vendor selector for administrators
    vendor = forms.ModelChoiceField(
        queryset=VendorProfile.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label=_('Vendor'),
        empty_label=_('Select vendor...'),
    )

    class Meta:
        model = Product
        fields = [
            'vendor',
            'category',
            'name',
            'slug',
            'sku',
            'description',
            'short_description',
            'price',
            'compare_at_price',
            'cost_price',
            'status',
            'is_featured',
            'weight',
            'dimensions',
            'meta_title',
            'meta_description',
        ]
        widgets = {
            'category': forms.Select(attrs={
                'class': 'form-select',
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': _('e.g. Wireless Noise-Cancelling Headphones'),
                'required': True,
            }),
            'slug': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': _('auto-generated-from-name-if-blank'),
            }),
            'sku': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': _('e.g. SKU-WH-1000XM4'),
                'required': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 4,
                'placeholder': _('Provide a detailed description of the product...'),
                'required': True,
            }),
            'short_description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 2,
                'placeholder': _('Brief overview (shown in listings and previews)...'),
            }),
            'price': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.01',
                'min': '0.01',
                'placeholder': '0.00',
                'required': True,
            }),
            'compare_at_price': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.01',
                'min': '0.01',
                'placeholder': '0.00',
            }),
            'cost_price': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.01',
                'min': '0.00',
                'placeholder': '0.00',
            }),
            'status': forms.Select(attrs={
                'class': 'form-select',
            }),
            'is_featured': forms.CheckboxInput(attrs={
                'class': 'form-checkbox',
            }),
            'weight': forms.NumberInput(attrs={
                'class': 'form-input',
                'step': '0.001',
                'min': '0',
                'placeholder': _('Weight in kg'),
            }),
            'dimensions': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': _('e.g. 20x15x5 cm'),
            }),
            'meta_title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': _('SEO Meta Title'),
            }),
            'meta_description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 2,
                'placeholder': _('SEO Meta Description'),
            }),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Active categories only
        self.fields['category'].queryset = Category.objects.filter(is_active=True)
        self.fields['category'].empty_label = _('Select a category...')
        self.fields['slug'].required = False

        # If user is a vendor, hide the vendor field as they can only create for themselves
        if user and hasattr(user, 'is_vendor') and user.is_vendor():
            if 'vendor' in self.fields:
                self.fields['vendor'].widget = forms.HiddenInput()
                self.fields['vendor'].required = False
        elif user and hasattr(user, 'can_access_admin_dashboard') and user.can_access_admin_dashboard():
            self.fields['vendor'].required = True

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price <= Decimal('0'):
            raise forms.ValidationError(_('Price must be greater than zero.'))
        return price

    def clean_cost_price(self):
        cost_price = self.cleaned_data.get('cost_price')
        if cost_price is not None and cost_price < Decimal('0'):
            raise forms.ValidationError(_('Cost price cannot be negative.'))
        return cost_price

    def clean(self):
        cleaned_data = super().clean()
        price = cleaned_data.get('price')
        compare_at_price = cleaned_data.get('compare_at_price')
        name = cleaned_data.get('name')
        slug = cleaned_data.get('slug')

        # Compare at price validation
        if compare_at_price is not None:
            if compare_at_price <= Decimal('0'):
                self.add_error('compare_at_price', _('Compare at price must be greater than zero.'))
            elif price is not None and compare_at_price <= price:
                self.add_error(
                    'compare_at_price',
                    _('Compare at price (original price) must be greater than current price to indicate a discount.')
                )

        # Generate slug if not provided
        if not slug and name:
            base_slug = slugify(name)
            candidate_slug = base_slug
            counter = 1
            pk = self.instance.pk if self.instance else None
            while Product.objects.filter(slug=candidate_slug).exclude(pk=pk).exists():
                candidate_slug = f'{base_slug}-{counter}'
                counter += 1
            cleaned_data['slug'] = candidate_slug

        return cleaned_data


class InventoryForm(forms.ModelForm):
    """Form for product inventory."""

    class Meta:
        model = Inventory
        fields = [
            'quantity',
            'low_stock_threshold',
            'track_quantity',
            'allow_backorder',
        ]
        widgets = {
            'quantity': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0',
                'placeholder': '0',
            }),
            'low_stock_threshold': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0',
                'placeholder': '10',
            }),
            'track_quantity': forms.CheckboxInput(attrs={
                'class': 'form-checkbox',
            }),
            'allow_backorder': forms.CheckboxInput(attrs={
                'class': 'form-checkbox',
            }),
        }

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty < 0:
            raise forms.ValidationError(_('Stock quantity cannot be negative.'))
        return qty

    def clean_low_stock_threshold(self):
        threshold = self.cleaned_data.get('low_stock_threshold')
        if threshold is not None and threshold < 0:
            raise forms.ValidationError(_('Low stock threshold cannot be negative.'))
        return threshold


class ProductImageForm(forms.ModelForm):
    """Form for single product image."""

    class Meta:
        model = ProductImage
        fields = [
            'image',
            'alt_text',
            'is_primary',
            'sort_order',
        ]
        widgets = {
            'image': forms.FileInput(attrs={
                'class': 'form-file-input',
                'accept': 'image/jpeg,image/png,image/webp,image/gif',
            }),
            'alt_text': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': _('Descriptive alt text for accessibility'),
            }),
            'is_primary': forms.CheckboxInput(attrs={
                'class': 'form-checkbox',
            }),
            'sort_order': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0',
            }),
        }

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            validate_image_file(image)
        return image


class CategoryForm(forms.ModelForm):
    """Form for managing category hierarchy with circular reference validation."""

    class Meta:
        model = Category
        fields = [
            'name',
            'slug',
            'parent',
            'description',
            'image',
            'is_active',
            'sort_order',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': _('Category Name')}),
            'slug': forms.TextInput(attrs={'class': 'form-input', 'placeholder': _('category-slug')}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-input', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Prevent picking self or descendants in dropdown
            descendant_ids = [d.pk for d in self.instance.get_descendants(include_self=True)]
            self.fields['parent'].queryset = Category.objects.exclude(pk__in=descendant_ids)

    def clean(self):
        cleaned_data = super().clean()
        parent = cleaned_data.get('parent')
        if parent and self.instance and self.instance.pk:
            if parent.pk == self.instance.pk:
                self.add_error('parent', _('A category cannot be its own parent.'))
            elif parent in self.instance.get_descendants():
                self.add_error('parent', _('Circular category hierarchy detected.'))
        return cleaned_data
