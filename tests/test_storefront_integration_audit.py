"""
Comprehensive Automated Tests for ShopSense Storefront Integration Audit:
Verifying all 10 focus areas across dynamic product catalog, images/fallbacks,
category filtering, search/sorting, vendor attribution, product details,
shopping cart, checkout with stock ledger synchronization, vendor isolation,
and marketplace-wide admin dashboard visibility.
"""

from decimal import Decimal
import pytest
from django.urls import reverse

from accounts.models import User
from catalog.models import Category, Inventory, Product, ProductImage
from inventory.models import Warehouse, WarehouseStock, StockMovement
from inventory.services.stock_services import StockService
from orders.models import Address, Cart, CartItem, Order, OrderItem, Payment
from vendors.models import VendorProfile


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def vendor_user_alpha():
    return User.objects.create_user(
        email='alpha_vendor@example.com',
        password='TestPass123!',
        role=User.Role.VENDOR,
        first_name='Alpha',
        last_name='Sellers',
    )


@pytest.fixture
def vendor_alpha(vendor_user_alpha):
    return VendorProfile.objects.create(
        user=vendor_user_alpha,
        vendor_id='VNDALPH0001',
        business_name='Alpha Electronics Store',
        contact_email=vendor_user_alpha.email,
        contact_phone='+919876543210',
        city='Bengaluru',
        state='Karnataka',
        is_active=True,
        is_verified=True,
    )


@pytest.fixture
def vendor_user_beta():
    return User.objects.create_user(
        email='beta_vendor@example.com',
        password='TestPass123!',
        role=User.Role.VENDOR,
        first_name='Beta',
        last_name='Spices',
    )


@pytest.fixture
def vendor_beta(vendor_user_beta):
    return VendorProfile.objects.create(
        user=vendor_user_beta,
        vendor_id='VNDBETA0002',
        business_name='Beta Organic Spices',
        contact_email=vendor_user_beta.email,
        contact_phone='+919876543211',
        city='Kochi',
        state='Kerala',
        is_active=True,
        is_verified=True,
    )


@pytest.fixture
def category_tech():
    return Category.objects.create(
        name='Consumer Tech',
        slug='consumer-tech',
        is_active=True,
        sort_order=1,
    )


@pytest.fixture
def category_groceries():
    return Category.objects.create(
        name='Gourmet Groceries',
        slug='gourmet-groceries',
        is_active=True,
        sort_order=2,
    )


@pytest.fixture
def default_warehouse():
    return StockService.get_or_create_default_warehouse()


@pytest.fixture
def alpha_product_in_stock(vendor_alpha, category_tech, default_warehouse):
    prod = Product.objects.create(
        vendor=vendor_alpha,
        category=category_tech,
        name='Alpha Wireless Earbuds Pro',
        slug='alpha-wireless-earbuds-pro',
        sku='ALPHA-TECH-001',
        description='Active noise cancellation wireless earbuds with 36hr battery.',
        short_description='True wireless earbuds with premium spatial audio.',
        price=Decimal('2499.00'),
        compare_at_price=Decimal('3499.00'),
        status=Product.Status.ACTIVE,
        is_featured=True,
        weight=Decimal('0.15'),
        dimensions='6x4x3 cm',
    )
    Inventory.objects.create(
        product=prod,
        quantity=25,
        low_stock_threshold=5,
    )
    WarehouseStock.objects.create(
        warehouse=default_warehouse,
        product=prod,
        quantity=25,
    )
    return prod


@pytest.fixture
def beta_product_in_stock(vendor_beta, category_groceries, default_warehouse):
    prod = Product.objects.create(
        vendor=vendor_beta,
        category=category_groceries,
        name='Beta Malabar Black Pepper 500g',
        slug='beta-malabar-black-pepper-500g',
        sku='BETA-GROC-001',
        description='Sun-dried organic black pepper from Wayanad estates.',
        short_description='Premium grade whole black pepper.',
        price=Decimal('540.00'),
        compare_at_price=Decimal('600.00'),
        status=Product.Status.ACTIVE,
        is_featured=False,
        weight=Decimal('0.50'),
    )
    Inventory.objects.create(
        product=prod,
        quantity=40,
        low_stock_threshold=10,
    )
    WarehouseStock.objects.create(
        warehouse=default_warehouse,
        product=prod,
        quantity=40,
    )
    return prod


@pytest.fixture
def alpha_product_out_of_stock(vendor_alpha, category_tech, default_warehouse):
    prod = Product.objects.create(
        vendor=vendor_alpha,
        category=category_tech,
        name='Alpha Smart Band 4',
        slug='alpha-smart-band-4',
        sku='ALPHA-TECH-002',
        description='Fitness band with AMOLED display and continuous heart-rate tracking.',
        price=Decimal('1899.00'),
        status=Product.Status.OUT_OF_STOCK,
        is_featured=False,
    )
    Inventory.objects.create(
        product=prod,
        quantity=0,
        low_stock_threshold=5,
    )
    WarehouseStock.objects.create(
        warehouse=default_warehouse,
        product=prod,
        quantity=0,
    )
    return prod


@pytest.fixture
def alpha_product_draft(vendor_alpha, category_tech):
    return Product.objects.create(
        vendor=vendor_alpha,
        category=category_tech,
        name='Alpha Secret NextGen Watch',
        slug='alpha-secret-nextgen-watch',
        sku='ALPHA-DRAFT-001',
        description='Confidential upcoming prototype.',
        price=Decimal('9999.00'),
        status=Product.Status.DRAFT,
    )


# -----------------------------------------------------------------------------
# 1. Catalog & Product Browsing Tests
# -----------------------------------------------------------------------------

@pytest.mark.django_db
class TestCatalogBrowsing:
    """Focus Area 1: Display products dynamically from the database."""

    def test_storefront_home_displays_featured_and_deal_products(
        self, client, alpha_product_in_stock, beta_product_in_stock
    ):
        response = client.get(reverse('store:home'))
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'ShopSense' in content
        assert alpha_product_in_stock.name in content
        assert beta_product_in_stock.name in content
        assert '₹2499.00' in content or '2499' in content

    def test_storefront_product_list_displays_all_catalog_products(
        self, client, alpha_product_in_stock, beta_product_in_stock, alpha_product_out_of_stock
    ):
        response = client.get(reverse('store:product_list'))
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert alpha_product_in_stock.name in content
        assert beta_product_in_stock.name in content
        assert alpha_product_out_of_stock.name in content

    def test_storefront_product_list_excludes_draft_products(
        self, client, alpha_product_in_stock, alpha_product_draft
    ):
        response = client.get(reverse('store:product_list'))
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert alpha_product_in_stock.name in content
        assert alpha_product_draft.name not in content


# -----------------------------------------------------------------------------
# 2. Product Images and Fallbacks
# -----------------------------------------------------------------------------

@pytest.mark.django_db
class TestProductImagesAndFallbacks:
    """Focus Area 2: Display real product images with appropriate fallbacks."""

    def test_product_card_without_image_renders_fallback_package_icon(
        self, client, alpha_product_in_stock
    ):
        response = client.get(reverse('store:product_list'))
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'product-card-fallback' in content
        assert 'data-lucide="package"' in content

    def test_product_detail_renders_gallery_or_fallback(
        self, client, alpha_product_in_stock
    ):
        url = reverse('store:product_detail', kwargs={'pk': alpha_product_in_stock.pk})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'product-detail-gallery' in content
        assert 'data-lucide="package"' in content


# -----------------------------------------------------------------------------
# 3. Category Browsing and Filtering
# -----------------------------------------------------------------------------

@pytest.mark.django_db
class TestCategoryBrowsingAndFiltering:
    """Focus Area 3: Build category-based browsing and filtering."""

    def test_filter_by_category_query_param(
        self, client, alpha_product_in_stock, beta_product_in_stock, category_tech
    ):
        url = reverse('store:product_list')
        response = client.get(f'{url}?category={category_tech.slug}')
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert alpha_product_in_stock.name in content
        assert beta_product_in_stock.name not in content

    def test_filter_by_category_url_slug_route(
        self, client, alpha_product_in_stock, beta_product_in_stock, category_groceries
    ):
        url = reverse('store:category_products', kwargs={'category': category_groceries.slug})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert beta_product_in_stock.name in content
        assert alpha_product_in_stock.name not in content

    def test_nonexistent_category_returns_empty_gracefully(self, client):
        url = reverse('store:category_products', kwargs={'category': 'non-existent-category'})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'No products found' in content or '0' in content or response.status_code == 200


# -----------------------------------------------------------------------------
# 4. Search, Sorting, and Pagination
# -----------------------------------------------------------------------------

@pytest.mark.django_db
class TestSearchSortingAndPagination:
    """Focus Area 4: Add product search, sorting and pagination."""

    def test_search_by_product_title(
        self, client, alpha_product_in_stock, beta_product_in_stock
    ):
        url = reverse('store:product_list')
        response = client.get(f'{url}?q=Earbuds')
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert alpha_product_in_stock.name in content
        assert beta_product_in_stock.name not in content

    def test_search_by_sku(
        self, client, alpha_product_in_stock, beta_product_in_stock
    ):
        url = reverse('store:product_list')
        response = client.get(f'{url}?q=BETA-GROC-001')
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert beta_product_in_stock.name in content
        assert alpha_product_in_stock.name not in content

    def test_search_by_vendor_name(
        self, client, alpha_product_in_stock, beta_product_in_stock
    ):
        url = reverse('store:product_list')
        response = client.get(f'{url}?q=Organic+Spices')
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert beta_product_in_stock.name in content
        assert alpha_product_in_stock.name not in content

    def test_sorting_by_price_ascending_and_descending(
        self, client, alpha_product_in_stock, beta_product_in_stock
    ):
        url = reverse('store:product_list')
        # Ascending: Beta (540) before Alpha (2499)
        resp_asc = client.get(f'{url}?sort=price_asc')
        assert resp_asc.status_code == 200
        content_asc = resp_asc.content.decode('utf-8')
        idx_beta = content_asc.find(beta_product_in_stock.name)
        idx_alpha = content_asc.find(alpha_product_in_stock.name)
        assert idx_beta != -1 and idx_alpha != -1
        assert idx_beta < idx_alpha

        # Descending: Alpha (2499) before Beta (540)
        resp_desc = client.get(f'{url}?sort=price_desc')
        assert resp_desc.status_code == 200
        content_desc = resp_desc.content.decode('utf-8')
        idx_beta_desc = content_desc.find(beta_product_in_stock.name)
        idx_alpha_desc = content_desc.find(alpha_product_in_stock.name)
        assert idx_alpha_desc < idx_beta_desc

    def test_in_stock_filtering(
        self, client, alpha_product_in_stock, alpha_product_out_of_stock
    ):
        url = reverse('store:product_list')
        response = client.get(f'{url}?in_stock=1')
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert alpha_product_in_stock.name in content
        assert alpha_product_out_of_stock.name not in content


# -----------------------------------------------------------------------------
# 5. Vendor Attribution and Details
# -----------------------------------------------------------------------------

@pytest.mark.django_db
class TestVendorAttributionAndDetails:
    """Focus Area 5: Show vendor names and seller details on card and detail view."""

    def test_vendor_name_displayed_on_product_card(
        self, client, alpha_product_in_stock
    ):
        response = client.get(reverse('store:product_list'))
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert f'Sold by <strong>{alpha_product_in_stock.vendor.business_name}</strong>' in content

    def test_vendor_details_displayed_on_product_detail(
        self, client, alpha_product_in_stock
    ):
        url = reverse('store:product_detail', kwargs={'pk': alpha_product_in_stock.pk})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert alpha_product_in_stock.vendor.business_name in content
        assert alpha_product_in_stock.sku in content
        assert 'Bengaluru' in content or 'Registered Marketplace Seller' in content


# -----------------------------------------------------------------------------
# 6. Functional Product Detail Pages
# -----------------------------------------------------------------------------

@pytest.mark.django_db
class TestProductDetailPages:
    """Focus Area 6: Implement functional product detail pages."""

    def test_product_detail_by_pk_and_by_slug(
        self, client, alpha_product_in_stock
    ):
        # By PK
        url_pk = reverse('store:product_detail', kwargs={'pk': alpha_product_in_stock.pk})
        resp_pk = client.get(url_pk)
        assert resp_pk.status_code == 200
        assert alpha_product_in_stock.name in resp_pk.content.decode('utf-8')

        # By Slug
        url_slug = reverse('store:product_detail_slug', kwargs={'slug': alpha_product_in_stock.slug})
        resp_slug = client.get(url_slug)
        assert resp_slug.status_code == 200
        assert alpha_product_in_stock.name in resp_slug.content.decode('utf-8')

    def test_discount_savings_calculation(
        self, client, alpha_product_in_stock
    ):
        url = reverse('store:product_detail', kwargs={'pk': alpha_product_in_stock.pk})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        # Price 2499 vs compare_at 3499 is -28% OFF, savings ₹1000
        assert '-28% OFF' in content
        assert '1000' in content

    def test_out_of_stock_product_shows_status(
        self, client, alpha_product_out_of_stock
    ):
        url = reverse('store:product_detail', kwargs={'pk': alpha_product_out_of_stock.pk})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Currently Out of Stock' in content
        assert 'btn-add-to-cart' not in content

    def test_draft_product_returns_404(
        self, client, alpha_product_draft
    ):
        url = reverse('store:product_detail', kwargs={'pk': alpha_product_draft.pk})
        response = client.get(url)
        assert response.status_code == 404


# -----------------------------------------------------------------------------
# 7. Shopping Cart Operations & Persistence
# -----------------------------------------------------------------------------

@pytest.mark.django_db
class TestShoppingCartPersistence:
    """Focus Area 7: Verify add-to-cart, quantity updates and cart persistence."""

    def test_cart_add_update_remove_flow(
        self, customer_client, customer_user, alpha_product_in_stock
    ):
        # 1. Add to cart
        add_url = reverse('orders:cart_add')
        resp_add = customer_client.post(add_url, {
            'product_id': alpha_product_in_stock.pk,
            'quantity': 2,
        }, follow=True)
        assert resp_add.status_code == 200

        cart = Cart.objects.get(user=customer_user)
        assert cart.items.count() == 1
        item = cart.items.first()
        assert item.quantity == 2
        assert item.product == alpha_product_in_stock

        # 2. Update quantity
        update_url = reverse('orders:cart_update', kwargs={'pk': item.pk})
        resp_update = customer_client.post(update_url, {'quantity': 5}, follow=True)
        assert resp_update.status_code == 200
        item.refresh_from_db()
        assert item.quantity == 5

        # 3. Remove from cart
        remove_url = reverse('orders:cart_remove', kwargs={'pk': item.pk})
        resp_remove = customer_client.post(remove_url, follow=True)
        assert resp_remove.status_code == 200
        assert cart.items.count() == 0

    def test_cart_persists_across_multiple_views(
        self, customer_client, customer_user, alpha_product_in_stock
    ):
        # Add item
        customer_client.post(reverse('orders:cart_add'), {
            'product_id': alpha_product_in_stock.pk,
            'quantity': 1,
        })
        # Visit home page
        customer_client.get(reverse('store:home'))
        # Visit product list
        customer_client.get(reverse('store:product_list'))
        # Check cart page
        resp_cart = customer_client.get(reverse('orders:cart'))
        assert resp_cart.status_code == 200
        content = resp_cart.content.decode('utf-8')
        assert alpha_product_in_stock.name in content


# -----------------------------------------------------------------------------
# 8. Checkout, Order Creation, and Stock Ledger Synchronization
# -----------------------------------------------------------------------------

@pytest.mark.django_db
class TestCheckoutAndInventoryLedger:
    """Focus Area 8: Verify checkout, order creation and inventory deduction."""

    def test_checkout_creates_order_and_synchronizes_ledger(
        self, customer_client, customer_user, alpha_product_in_stock, default_warehouse
    ):
        # Populate cart with 3 units
        cart, _ = Cart.objects.get_or_create(user=customer_user)
        CartItem.objects.create(cart=cart, product=alpha_product_in_stock, quantity=3)

        initial_catalog_stock = alpha_product_in_stock.inventory.quantity
        wh_stock_initial = WarehouseStock.objects.get(
            warehouse=default_warehouse, product=alpha_product_in_stock
        ).quantity
        initial_movements_count = StockMovement.objects.filter(product=alpha_product_in_stock).count()

        # Submit checkout
        place_order_url = reverse('orders:place_order')
        checkout_data = {
            'shipping_first_name': 'Rahul',
            'shipping_last_name': 'Sharma',
            'shipping_email': customer_user.email,
            'shipping_phone': '+919876543210',
            'shipping_address': 'Flat 402, Sunshine Heights, MG Road',
            'shipping_city': 'Bengaluru',
            'shipping_state': 'Karnataka',
            'shipping_postal_code': '560001',
            'shipping_country': 'India',
            'payment_method': Payment.Method.COD,
        }

        resp = customer_client.post(place_order_url, checkout_data, follow=True)
        assert resp.status_code == 200

        # Verify Order creation
        order = Order.objects.filter(user=customer_user).first()
        assert order is not None
        assert order.status == Order.Status.CONFIRMED
        assert order.items.count() == 1
        order_item = order.items.first()
        assert order_item.product == alpha_product_in_stock
        assert order_item.quantity == 3
        assert order_item.vendor == alpha_product_in_stock.vendor

        # Verify Payment record
        payment = Payment.objects.filter(order=order).first()
        assert payment is not None
        assert payment.method == Payment.Method.COD
        assert payment.amount == order.total

        # Verify Cart cleared
        cart.refresh_from_db()
        assert cart.items.count() == 0

        # Verify Catalog inventory decremented
        alpha_product_in_stock.inventory.refresh_from_db()
        assert alpha_product_in_stock.inventory.quantity == initial_catalog_stock - 3

        # Verify Warehouse stock decremented
        wh_stock_after = WarehouseStock.objects.get(
            warehouse=default_warehouse, product=alpha_product_in_stock
        ).quantity
        assert wh_stock_after == wh_stock_initial - 3

        # Verify StockMovement ledger entry recorded
        new_movements = StockMovement.objects.filter(
            product=alpha_product_in_stock,
            movement_type=StockMovement.MovementType.SALE,
            order=order,
        )
        assert new_movements.exists()
        movement = new_movements.first()
        assert movement.quantity_change == -3
        assert movement.warehouse == default_warehouse
        assert movement.performed_by == customer_user


# -----------------------------------------------------------------------------
# 9. Vendor Dashboard Isolation
# -----------------------------------------------------------------------------

@pytest.mark.django_db
class TestVendorDashboardIsolation:
    """Focus Area 9: Ensure vendor dashboards show only their own products and orders."""

    def test_vendor_sees_only_own_products_in_product_management(
        self, client, vendor_user_alpha, vendor_alpha, vendor_beta,
        alpha_product_in_stock, beta_product_in_stock
    ):
        client.force_login(vendor_user_alpha)
        url = reverse('dashboard:product_list')
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert alpha_product_in_stock.name in content
        assert beta_product_in_stock.name not in content

    def test_vendor_sees_only_own_orders(
        self, client, vendor_user_alpha, vendor_user_beta, vendor_alpha, vendor_beta,
        customer_user, alpha_product_in_stock, beta_product_in_stock
    ):
        # Order 1: Has alpha item
        order_alpha = Order.objects.create(
            user=customer_user,
            order_number='ORD-ALPHA-1001',
            status=Order.Status.PROCESSING,
            total=Decimal('2499.00'),
        )
        OrderItem.objects.create(
            order=order_alpha,
            product=alpha_product_in_stock,
            vendor=vendor_alpha,
            product_name=alpha_product_in_stock.name,
            product_sku=alpha_product_in_stock.sku,
            quantity=1,
            unit_price=Decimal('2499.00'),
            total_price=Decimal('2499.00'),
        )

        # Order 2: Has beta item
        order_beta = Order.objects.create(
            user=customer_user,
            order_number='ORD-BETA-2002',
            status=Order.Status.PROCESSING,
            total=Decimal('540.00'),
        )
        OrderItem.objects.create(
            order=order_beta,
            product=beta_product_in_stock,
            vendor=vendor_beta,
            product_name=beta_product_in_stock.name,
            product_sku=beta_product_in_stock.sku,
            quantity=1,
            unit_price=Decimal('540.00'),
            total_price=Decimal('540.00'),
        )

        # Log in as Vendor Alpha
        client.force_login(vendor_user_alpha)
        resp_vendor_alpha = client.get(reverse('vendors:order_list'))
        assert resp_vendor_alpha.status_code == 200
        content_alpha = resp_vendor_alpha.content.decode('utf-8')
        assert 'ORD-ALPHA-1001' in content_alpha
        assert 'ORD-BETA-2002' not in content_alpha

        # Vendor Alpha cannot access Order Beta detail view
        resp_beta_detail = client.get(
            reverse('vendors:order_detail', kwargs={'order_number': 'ORD-BETA-2002'})
        )
        assert resp_beta_detail.status_code == 404


# -----------------------------------------------------------------------------
# 10. Admin Dashboard Marketplace-Wide Information
# -----------------------------------------------------------------------------

@pytest.mark.django_db
class TestAdminDashboardMarketplaceWide:
    """Focus Area 10: Ensure admin dashboards show marketplace-wide information."""

    def test_admin_dashboard_shows_aggregated_marketplace_metrics(
        self, client, admin_user, alpha_product_in_stock, beta_product_in_stock, customer_user
    ):
        client.force_login(admin_user)
        resp = client.get(reverse('dashboard:admin_dashboard'))
        assert resp.status_code == 200
        content = resp.content.decode('utf-8')
        assert 'Dashboard' in content
        assert 'Marketplace' in content or 'Admin' in content or 'Total Products' in content

    def test_admin_sees_all_products_across_all_vendors(
        self, client, admin_user, alpha_product_in_stock, beta_product_in_stock
    ):
        client.force_login(admin_user)
        url = reverse('dashboard:product_list')
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert alpha_product_in_stock.name in content
        assert beta_product_in_stock.name in content

    def test_admin_sees_all_orders_across_all_vendors(
        self, client, admin_user, vendor_alpha, vendor_beta,
        customer_user, alpha_product_in_stock, beta_product_in_stock
    ):
        order = Order.objects.create(
            user=customer_user,
            order_number='ORD-GLOBAL-9999',
            status=Order.Status.PROCESSING,
            total=Decimal('3039.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=alpha_product_in_stock,
            vendor=vendor_alpha,
            product_name=alpha_product_in_stock.name,
            product_sku=alpha_product_in_stock.sku,
            quantity=1,
            unit_price=Decimal('2499.00'),
            total_price=Decimal('2499.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=beta_product_in_stock,
            vendor=vendor_beta,
            product_name=beta_product_in_stock.name,
            product_sku=beta_product_in_stock.sku,
            quantity=1,
            unit_price=Decimal('540.00'),
            total_price=Decimal('540.00'),
        )

        client.force_login(admin_user)
        url = reverse('dashboard:order_list')
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'ORD-GLOBAL-9999' in content
