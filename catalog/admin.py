"""
Admin configuration for ShopSense Catalog app.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .forms import CategoryForm
from .models import Category, Inventory, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image', 'alt_text', 'is_primary', 'sort_order')


class InventoryInline(admin.StackedInline):
    model = Inventory
    extra = 0
    fields = ('quantity', 'reserved_quantity', 'low_stock_threshold', 'track_quantity', 'allow_backorder')
    readonly_fields = ('reserved_quantity',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    form = CategoryForm
    list_display = ('name', 'slug', 'parent', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'parent', 'created_at')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('sort_order', 'name')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'vendor', 'category', 'sku', 'price', 'status', 'is_featured', 'created_at')
    list_filter = ('status', 'is_featured', 'category', 'vendor', 'created_at')
    search_fields = ('name', 'sku', 'description', 'vendor__business_name')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at', 'published_at')
    ordering = ('-created_at',)
    inlines = [ProductImageInline, InventoryInline]

    fieldsets = (
        (None, {'fields': ('vendor', 'category', 'name', 'slug', 'sku')}),
        (_('Descriptions'), {'fields': ('description', 'short_description')}),
        (_('Pricing'), {'fields': ('price', 'compare_at_price', 'cost_price')}),
        (_('Status & Visibility'), {'fields': ('status', 'is_featured', 'published_at')}),
        (_('Physical Attributes'), {'fields': ('weight', 'dimensions')}),
        (_('SEO'), {'fields': ('meta_title', 'meta_description'), 'classes': ('collapse',)}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'image', 'is_primary', 'sort_order', 'created_at')
    list_filter = ('is_primary', 'created_at')
    search_fields = ('product__name', 'alt_text')


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'reserved_quantity', 'available_quantity', 'is_low_stock', 'is_out_of_stock')
    list_filter = ('track_quantity', 'allow_backorder', 'created_at')
    search_fields = ('product__name', 'product__sku')
    readonly_fields = ('created_at', 'updated_at')

    def available_quantity(self, obj):
        return obj.available_quantity
    available_quantity.short_description = _('Available')

    def is_low_stock(self, obj):
        return obj.is_low_stock
    is_low_stock.boolean = True
    is_low_stock.short_description = _('Low Stock')

    def is_out_of_stock(self, obj):
        return obj.is_out_of_stock
    is_out_of_stock.boolean = True
    is_out_of_stock.short_description = _('Out of Stock')