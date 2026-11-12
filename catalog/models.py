"""
Models for ShopSense Catalog app (placeholder for future phases).
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from vendors.models import VendorProfile


class Category(models.Model):
    """Product category model."""

    name = models.CharField(_('name'), max_length=255, unique=True)
    slug = models.SlugField(_('slug'), max_length=255, unique=True)
    description = models.TextField(_('description'), blank=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name=_('parent category'),
    )
    image = models.ImageField(_('image'), upload_to='categories/', blank=True, null=True)
    is_active = models.BooleanField(_('active'), default=True)
    sort_order = models.PositiveIntegerField(_('sort order'), default=0)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('category')
        verbose_name_plural = _('categories')
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.parent_id:
            # Prevent self-parenting
            if self.pk and self.parent_id == self.pk:
                raise ValidationError({'parent': _('A category cannot be its own parent.')})

            # Prevent indirect circular references
            visited = {self.pk} if self.pk else set()
            curr = self.parent
            while curr is not None:
                if self.pk and curr.pk == self.pk:
                    raise ValidationError({'parent': _('Circular category hierarchy detected.')})
                if curr.pk in visited:
                    raise ValidationError({'parent': _('Circular category hierarchy detected.')})
                visited.add(curr.pk)
                curr = curr.parent

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def get_ancestors(self, include_self=False):
        """Return list of ancestor Category instances ordered from root down to parent."""
        ancestors = []
        if include_self:
            ancestors.append(self)
        curr = self.parent
        visited = {self.pk} if self.pk else set()
        while curr is not None:
            if curr.pk in visited:
                break
            visited.add(curr.pk)
            ancestors.append(curr)
            curr = curr.parent
        ancestors.reverse()
        return ancestors

    def get_descendants(self, include_self=False):
        """Return list of all descendant Category instances."""
        descendants = [self] if include_self else []
        visited = {self.pk} if self.pk else set()
        queue = list(self.children.all())
        while queue:
            curr = queue.pop(0)
            if curr.pk in visited:
                continue
            visited.add(curr.pk)
            descendants.append(curr)
            queue.extend(list(curr.children.all()))
        return descendants

    def get_product_count(self, include_descendants=True):
        """Return count of active products in this category (and descendants if specified)."""
        if include_descendants:
            descendant_cats = self.get_descendants(include_self=True)
            return Product.objects.filter(category__in=descendant_cats).count()
        return self.products.count()


class Product(models.Model):
    """Product model."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Draft')
        ACTIVE = 'ACTIVE', _('Active')
        INACTIVE = 'INACTIVE', _('Inactive')
        OUT_OF_STOCK = 'OUT_OF_STOCK', _('Out of Stock')

    vendor = models.ForeignKey(
        VendorProfile,
        on_delete=models.CASCADE,
        related_name='products',
        verbose_name=_('vendor'),
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name=_('category'),
    )
    name = models.CharField(_('name'), max_length=255)
    slug = models.SlugField(_('slug'), max_length=255)
    description = models.TextField(_('description'))
    short_description = models.TextField(_('short description'), max_length=500, blank=True)
    sku = models.CharField(_('SKU'), max_length=100, unique=True)
    price = models.DecimalField(_('price'), max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(
        _('compare at price'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    cost_price = models.DecimalField(
        _('cost price'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    is_featured = models.BooleanField(_('featured'), default=False)
    weight = models.DecimalField(
        _('weight (kg)'),
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
    )
    dimensions = models.CharField(_('dimensions (LxWxH cm)'), max_length=100, blank=True)
    meta_title = models.CharField(_('meta title'), max_length=255, blank=True)
    meta_description = models.TextField(_('meta description'), blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)
    published_at = models.DateTimeField(_('published at'), null=True, blank=True)

    class Meta:
        verbose_name = _('product')
        verbose_name_plural = _('products')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['slug']),
            models.Index(fields=['sku']),
        ]

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    """Product image model."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name=_('product'),
    )
    image = models.ImageField(_('image'), upload_to='products/')
    alt_text = models.CharField(_('alt text'), max_length=255, blank=True)
    is_primary = models.BooleanField(_('primary'), default=False)
    sort_order = models.PositiveIntegerField(_('sort order'), default=0)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)

    class Meta:
        verbose_name = _('product image')
        verbose_name_plural = _('product images')
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        return f'{self.product.name} - Image {self.sort_order}'


class Inventory(models.Model):
    """Inventory tracking model."""

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='inventory',
        verbose_name=_('product'),
    )
    quantity = models.PositiveIntegerField(_('quantity'), default=0)
    reserved_quantity = models.PositiveIntegerField(_('reserved quantity'), default=0)
    low_stock_threshold = models.PositiveIntegerField(_('low stock threshold'), default=10)
    track_quantity = models.BooleanField(_('track quantity'), default=True)
    allow_backorder = models.BooleanField(_('allow backorder'), default=False)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('inventory')
        verbose_name_plural = _('inventories')

    def __str__(self):
        return f'{self.product.name} - Qty: {self.quantity}'

    @property
    def available_quantity(self):
        return self.quantity - self.reserved_quantity

    @property
    def is_low_stock(self):
        return self.available_quantity <= self.low_stock_threshold

    @property
    def is_out_of_stock(self):
        return self.available_quantity <= 0