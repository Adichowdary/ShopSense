"""
Admin configuration for ShopSense Orders app.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Cart, CartItem, Order, OrderItem, Payment


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'created_at', 'updated_at')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'updated_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name')
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'vendor', 'product_name', 'product_sku', 'quantity', 'unit_price', 'total_price')


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ('payment_id', 'method', 'status', 'amount', 'currency', 'created_at', 'completed_at')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number',
        'user',
        'email',
        'status',
        'total',
        'created_at',
    )
    list_filter = ('status', 'created_at', 'confirmed_at', 'shipped_at', 'delivered_at')
    search_fields = ('order_number', 'user__email', 'email', 'shipping_first_name', 'shipping_last_name')
    readonly_fields = (
        'order_number', 'user', 'email', 'phone',
        'shipping_first_name', 'shipping_last_name', 'shipping_address',
        'shipping_city', 'shipping_state', 'shipping_postal_code', 'shipping_country',
        'billing_first_name', 'billing_last_name', 'billing_address',
        'billing_city', 'billing_state', 'billing_postal_code', 'billing_country',
        'subtotal', 'shipping_cost', 'tax_amount', 'discount_amount', 'total',
        'customer_notes', 'created_at', 'updated_at', 'confirmed_at', 'shipped_at', 'delivered_at',
    )
    ordering = ('-created_at',)
    inlines = [OrderItemInline, PaymentInline]

    fieldsets = (
        (None, {'fields': ('order_number', 'user', 'email', 'phone', 'status')}),
        (_('Shipping Address'), {
            'fields': ('shipping_first_name', 'shipping_last_name', 'shipping_address',
                      'shipping_city', 'shipping_state', 'shipping_postal_code', 'shipping_country')
        }),
        (_('Billing Address'), {
            'fields': ('billing_first_name', 'billing_last_name', 'billing_address',
                      'billing_city', 'billing_state', 'billing_postal_code', 'billing_country'),
            'classes': ('collapse',),
        }),
        (_('Totals'), {
            'fields': ('subtotal', 'shipping_cost', 'tax_amount', 'discount_amount', 'total')
        }),
        (_('Notes'), {
            'fields': ('customer_notes', 'admin_notes')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at', 'confirmed_at', 'shipped_at', 'delivered_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product_name', 'product_sku', 'vendor', 'quantity', 'unit_price', 'total_price')
    list_filter = ('created_at',)
    search_fields = ('order__order_number', 'product_name', 'product_sku', 'vendor__business_name')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('payment_id', 'order', 'method', 'status', 'amount', 'currency', 'created_at')
    list_filter = ('method', 'status', 'created_at')
    search_fields = ('payment_id', 'order__order_number')
    readonly_fields = ('payment_id', 'order', 'method', 'status', 'amount', 'currency', 'gateway_response', 'failure_reason', 'created_at', 'completed_at')
    ordering = ('-created_at',)