"""
Customer-facing Storefront Views for ShopSense.
"""

from decimal import Decimal
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, TemplateView

from .models import Category, Product


class StorefrontHomeView(TemplateView):
    """Customer marketplace home view with promotional hero, categories, and active products."""

    template_name = 'storefront/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_products = (
            Product.objects.filter(status=Product.Status.ACTIVE)
            .select_related('vendor', 'category', 'inventory')
            .prefetch_related('images')
        )

        context.update({
            'page_title': _('ShopSense - Discover, Shop & Save Online'),
            'categories': (
                Category.objects.filter(is_active=True)
                .annotate(
                    active_products_count=Count(
                        'products', filter=Q(products__status=Product.Status.ACTIVE)
                    )
                )
                .order_by('sort_order', 'name')[:8]
            ),
            'featured_products': active_products.filter(is_featured=True).order_by('-created_at')[:8],
            'new_arrivals': active_products.order_by('-created_at')[:8],
            'deal_products': (
                active_products.filter(compare_at_price__gt=0)
                .filter(compare_at_price__gt=Product.objects.filter(pk=models.OuterRef('pk')).values('price') if hasattr(models, 'OuterRef') else active_products)
                if False else active_products.filter(compare_at_price__isnull=False).order_by('-created_at')[:8]
            ),
        })
        return context


class StorefrontProductListView(ListView):
    """Catalog browsing and search with multi-faceted filtering and sorting."""

    model = Product
    template_name = 'storefront/product_list.html'
    context_object_name = 'products'
    paginate_by = 12

    def get_queryset(self):
        queryset = (
            Product.objects.filter(status=Product.Status.ACTIVE)
            .select_related('vendor', 'category', 'inventory')
            .prefetch_related('images')
        )

        params = self.request.GET

        # Search keyword
        search_query = params.get('q', '').strip() or params.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query)
                | Q(description__icontains=search_query)
                | Q(sku__icontains=search_query)
                | Q(category__name__icontains=search_query)
                | Q(vendor__business_name__icontains=search_query)
            )

        # Category filter (by slug or ID)
        category_slug = params.get('category', '').strip()
        if category_slug:
            if category_slug.isdigit():
                queryset = queryset.filter(category_id=int(category_slug))
            else:
                queryset = queryset.filter(category__slug=category_slug)

        # Price range filter
        min_price = params.get('min_price', '').strip()
        if min_price:
            try:
                queryset = queryset.filter(price__gte=Decimal(min_price))
            except Exception:
                pass

        max_price = params.get('max_price', '').strip()
        if max_price:
            try:
                queryset = queryset.filter(price__lte=Decimal(max_price))
            except Exception:
                pass

        # In-stock filter
        in_stock = params.get('in_stock', '').strip()
        if in_stock in ['1', 'true', 'yes', 'on']:
            queryset = queryset.filter(inventory__quantity__gt=0)

        # Sorting
        sort_by = params.get('sort', 'featured').strip()
        sort_options = {
            'featured': ['-is_featured', '-created_at'],
            'price_asc': ['price'],
            'price_desc': ['-price'],
            'newest': ['-created_at'],
            'name_asc': ['name'],
        }
        order_fields = sort_options.get(sort_by, ['-is_featured', '-created_at'])
        queryset = queryset.order_by(*order_fields)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET

        category_slug = params.get('category', '').strip()
        active_category = None
        if category_slug:
            if category_slug.isdigit():
                active_category = Category.objects.filter(pk=int(category_slug)).first()
            else:
                active_category = Category.objects.filter(slug=category_slug).first()

        context.update({
            'page_title': active_category.name if active_category else _('All Products'),
            'categories': Category.objects.filter(is_active=True).order_by('name'),
            'active_category': active_category,
            'search_query': params.get('q', '').strip() or params.get('search', '').strip(),
            'current_sort': params.get('sort', 'featured'),
            'current_min_price': params.get('min_price', ''),
            'current_max_price': params.get('max_price', ''),
            'current_in_stock': params.get('in_stock', ''),
        })
        return context


class StorefrontProductDetailView(DetailView):
    """Customer-facing product detail page."""

    model = Product
    template_name = 'storefront/product_detail.html'
    context_object_name = 'product'

    def get_queryset(self):
        # Customers can only view active products
        return (
            Product.objects.filter(status=Product.Status.ACTIVE)
            .select_related('vendor', 'category', 'inventory')
            .prefetch_related('images')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object

        # Images
        all_images = list(product.images.all())
        primary_image = next((img for img in all_images if img.is_primary), None)
        if not primary_image and all_images:
            primary_image = all_images[0]

        # Discount / Savings calculation
        discount_percent = 0
        discount_amount = Decimal('0.00')
        if product.compare_at_price and product.compare_at_price > product.price:
            discount_amount = product.compare_at_price - product.price
            discount_percent = int((discount_amount / product.compare_at_price) * 100)

        # Related products
        related_products = []
        if product.category:
            related_products = (
                Product.objects.filter(category=product.category, status=Product.Status.ACTIVE)
                .exclude(pk=product.pk)
                .select_related('inventory')
                .prefetch_related('images')[:4]
            )

        context.update({
            'page_title': f'{product.name} | ShopSense',
            'primary_image': primary_image,
            'gallery_images': all_images,
            'discount_amount': discount_amount,
            'discount_percent': discount_percent,
            'related_products': related_products,
            'available_quantity': product.inventory.quantity if hasattr(product, 'inventory') else 0,
            'is_in_stock': hasattr(product, 'inventory') and product.inventory.quantity > 0,
        })
        return context
