"""
Product repository providing decoupled, optimized data access patterns for Catalog.
"""

from typing import Optional, List
from django.db.models import QuerySet, Q, F
from django.utils.text import slugify

from .models import Product, Category, Inventory


class ProductRepository:
    """Repository class encapsulating queries and data operations for products."""

    @staticmethod
    def get_queryset() -> QuerySet:
        return Product.objects.select_related('vendor', 'category', 'inventory').prefetch_related('images')

    @classmethod
    def get_active(cls) -> QuerySet:
        return cls.get_queryset().filter(status=Product.Status.ACTIVE)

    @classmethod
    def get_by_id(cls, product_id: int) -> Optional[Product]:
        try:
            return cls.get_queryset().get(pk=product_id)
        except Product.DoesNotExist:
            return None

    @classmethod
    def get_by_sku(cls, sku: str) -> Optional[Product]:
        try:
            return cls.get_queryset().get(sku=sku)
        except Product.DoesNotExist:
            return None

    @classmethod
    def get_by_slug(cls, slug: str) -> Optional[Product]:
        try:
            return cls.get_queryset().get(slug=slug)
        except Product.DoesNotExist:
            return None

    @classmethod
    def for_vendor(cls, vendor) -> QuerySet:
        return cls.get_queryset().filter(vendor=vendor)

    @classmethod
    def for_category(cls, category: Category, include_descendants: bool = True) -> QuerySet:
        if include_descendants:
            categories = category.get_descendants(include_self=True)
            return cls.get_active().filter(category__in=categories)
        return cls.get_active().filter(category=category)

    @classmethod
    def search(cls, query: str, vendor=None) -> QuerySet:
        qs = cls.get_active() if vendor is None else cls.for_vendor(vendor)
        if not query:
            return qs
        return qs.filter(
            Q(name__icontains=query) |
            Q(sku__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        )

    @classmethod
    def get_featured(cls, limit: int = 8) -> QuerySet:
        return cls.get_active().filter(is_featured=True)[:limit]

    @classmethod
    def get_low_stock(cls, threshold: Optional[int] = None) -> QuerySet:
        qs = cls.get_queryset().filter(status=Product.Status.ACTIVE)
        if threshold is not None:
            return qs.filter(inventory__quantity__lte=threshold)
        return qs.filter(inventory__quantity__lte=F('inventory__low_stock_threshold'))

    @classmethod
    def get_out_of_stock(cls) -> QuerySet:
        return cls.get_queryset().filter(
            Q(status=Product.Status.OUT_OF_STOCK) |
            Q(inventory__quantity__lte=0)
        )
