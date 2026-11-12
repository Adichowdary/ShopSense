"""
Models for ShopSense Orders app (placeholder for future phases).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from catalog.models import Product
from vendors.models import VendorProfile


class Cart(models.Model):
    """Shopping cart model."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart',
        verbose_name=_('user'),
    )
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('cart')
        verbose_name_plural = _('carts')

    def __str__(self):
        return f'Cart for {self.user.email}'

    @property
    def total_price(self):
        return sum(item.total_price for item in self.items.all())

    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())


class Address(models.Model):
    """Customer delivery address model."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='addresses',
        verbose_name=_('user'),
    )
    first_name = models.CharField(_('first name'), max_length=150)
    last_name = models.CharField(_('last name'), max_length=150)
    phone = models.CharField(_('phone number'), max_length=20)
    street_address = models.TextField(_('street address'))
    city = models.CharField(_('city'), max_length=100)
    state = models.CharField(_('state'), max_length=100)
    postal_code = models.CharField(_('postal code'), max_length=20)
    country = models.CharField(_('country'), max_length=100, default='India')
    is_default = models.BooleanField(_('default address'), default=False)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)

    class Meta:
        verbose_name = _('address')
        verbose_name_plural = _('addresses')
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f'{self.first_name} {self.last_name} - {self.city}, {self.postal_code}'

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class CartItem(models.Model):
    """Shopping cart item model."""

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('cart'),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='cart_items',
        verbose_name=_('product'),
    )
    quantity = models.PositiveIntegerField(_('quantity'), default=1)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('cart item')
        verbose_name_plural = _('cart items')
        unique_together = [['cart', 'product']]

    def __str__(self):
        return f'{self.quantity} x {self.product.name}'

    @property
    def total_price(self):
        return self.product.price * self.quantity


class Order(models.Model):
    """Order model."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        CONFIRMED = 'CONFIRMED', _('Confirmed')
        PROCESSING = 'PROCESSING', _('Processing')
        SHIPPED = 'SHIPPED', _('Shipped')
        DELIVERED = 'DELIVERED', _('Delivered')
        CANCELLED = 'CANCELLED', _('Cancelled')
        REFUNDED = 'REFUNDED', _('Refunded')

    order_number = models.CharField(_('order number'), max_length=20, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name=_('customer'),
    )
    email = models.EmailField(_('email'))
    phone = models.CharField(_('phone'), max_length=20, blank=True)
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # Shipping address
    shipping_first_name = models.CharField(_('shipping first name'), max_length=150)
    shipping_last_name = models.CharField(_('shipping last name'), max_length=150)
    shipping_address = models.TextField(_('shipping address'))
    shipping_city = models.CharField(_('shipping city'), max_length=100)
    shipping_state = models.CharField(_('shipping state'), max_length=100)
    shipping_postal_code = models.CharField(_('shipping postal code'), max_length=20)
    shipping_country = models.CharField(_('shipping country'), max_length=100, default='India')

    # Billing address
    billing_first_name = models.CharField(_('billing first name'), max_length=150, blank=True)
    billing_last_name = models.CharField(_('billing last name'), max_length=150, blank=True)
    billing_address = models.TextField(_('billing address'), blank=True)
    billing_city = models.CharField(_('billing city'), max_length=100, blank=True)
    billing_state = models.CharField(_('billing state'), max_length=100, blank=True)
    billing_postal_code = models.CharField(_('billing postal code'), max_length=20, blank=True)
    billing_country = models.CharField(_('billing country'), max_length=100, blank=True)

    # Totals
    subtotal = models.DecimalField(_('subtotal'), max_digits=10, decimal_places=2, default=0)
    shipping_cost = models.DecimalField(_('shipping cost'), max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(_('tax amount'), max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(_('discount amount'), max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(_('total'), max_digits=10, decimal_places=2, default=0)

    # Notes
    customer_notes = models.TextField(_('customer notes'), blank=True)
    admin_notes = models.TextField(_('admin notes'), blank=True)

    # Timestamps
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)
    confirmed_at = models.DateTimeField(_('confirmed at'), null=True, blank=True)
    shipped_at = models.DateTimeField(_('shipped at'), null=True, blank=True)
    delivered_at = models.DateTimeField(_('delivered at'), null=True, blank=True)

    class Meta:
        verbose_name = _('order')
        verbose_name_plural = _('orders')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['order_number']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f'Order {self.order_number}'

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)

    def generate_order_number(self):
        """Generate a unique order number."""
        import random
        import string
        from datetime import datetime
        date_part = datetime.now().strftime('%Y%m%d')
        while True:
            random_part = ''.join(random.choices(string.digits, k=6))
            order_number = f'ORD{date_part}{random_part}'
            if not Order.objects.filter(order_number=order_number).exists():
                return order_number


class OrderItem(models.Model):
    """Order item model."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        CONFIRMED = 'CONFIRMED', _('Confirmed')
        PROCESSING = 'PROCESSING', _('Processing')
        SHIPPED = 'SHIPPED', _('Shipped')
        DELIVERED = 'DELIVERED', _('Delivered')
        CANCELLED = 'CANCELLED', _('Cancelled')

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('order'),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_items',
        verbose_name=_('product'),
    )
    vendor = models.ForeignKey(
        VendorProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_items',
        verbose_name=_('vendor'),
    )
    product_name = models.CharField(_('product name'), max_length=255)
    product_sku = models.CharField(_('product SKU'), max_length=100)
    quantity = models.PositiveIntegerField(_('quantity'), default=1)
    unit_price = models.DecimalField(_('unit price'), max_digits=10, decimal_places=2)
    total_price = models.DecimalField(_('total price'), max_digits=10, decimal_places=2)
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.CONFIRMED,
    )
    shipped_at = models.DateTimeField(_('shipped at'), null=True, blank=True)
    delivered_at = models.DateTimeField(_('delivered at'), null=True, blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)

    class Meta:
        verbose_name = _('order item')
        verbose_name_plural = _('order items')

    def __str__(self):
        return f'{self.quantity} x {self.product_name} (Order {self.order.order_number})'


class Payment(models.Model):
    """Payment record model."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        PROCESSING = 'PROCESSING', _('Processing')
        COMPLETED = 'COMPLETED', _('Completed')
        FAILED = 'FAILED', _('Failed')
        REFUNDED = 'REFUNDED', _('Refunded')

    class Method(models.TextChoices):
        CARD = 'CARD', _('Credit/Debit Card')
        UPI = 'UPI', _('UPI')
        NET_BANKING = 'NET_BANKING', _('Net Banking')
        WALLET = 'WALLET', _('Wallet')
        COD = 'COD', _('Cash on Delivery')

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name=_('order'),
    )
    payment_id = models.CharField(_('payment ID'), max_length=100, unique=True)
    method = models.CharField(_('method'), max_length=20, choices=Method.choices)
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    amount = models.DecimalField(_('amount'), max_digits=10, decimal_places=2)
    currency = models.CharField(_('currency'), max_length=3, default='INR')
    gateway_response = models.JSONField(_('gateway response'), default=dict, blank=True)
    failure_reason = models.TextField(_('failure reason'), blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    completed_at = models.DateTimeField(_('completed at'), null=True, blank=True)

    class Meta:
        verbose_name = _('payment')
        verbose_name_plural = _('payments')
        ordering = ['-created_at']

    def __str__(self):
        return f'Payment {self.payment_id} for Order {self.order.order_number}'