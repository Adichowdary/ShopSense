"""
Tests for ShopSense Customer Storefront, Shopping Cart, and Checkout (Phase 3).
"""

from decimal import Decimal
import pytest
from django.urls import reverse

from accounts.models import User
from catalog.models import Category, Inventory, Product
from orders.models import Address, Cart, CartItem, Order, OrderItem, Payment
from vendors.models import VendorProfile


@pytest.fixture
def vendor_profile(vendor_user):
    """Active vendor profile for product vendor FK."""
    profile, _ = VendorProfile.objects.get_or_create(
        user=vendor_user,
        defaults={
            'vendor_id': 'VND55555555',
            'business_name': 'Tech Hub Store',
            'contact_email': vendor_user.email,
            'is_active': True,
            'is_verified': True,
        }
    )
    return profile


@pytest.fixture
def category():
    """Product category fixture."""
    cat, _ = Category.objects.get_or_create(
        slug='laptops',
        defaults={'name': 'Laptops & Computers', 'is_active': True}
    )
    return cat


@pytest.fixture
def active_product(vendor_profile, category):
    """Active product fixture with inventory."""
    prod = Product.objects.create(
        vendor=vendor_profile,
        category=category,
        name='Ultrabook Pro 15',
        slug='ultrabook-pro-15',
        sku='UB-PRO-15',
        description='High performance laptop with 32GB RAM and 1TB SSD.',
        price=Decimal('1200.00'),
        compare_at_price=Decimal('1350.00'),
        status=Product.Status.ACTIVE,
        is_featured=True,
    )
    Inventory.objects.create(
        product=prod,
        quantity=10,
        low_stock_threshold=2,
    )
    return prod


@pytest.fixture
def second_customer_user():
    """Create a second customer user for privacy testing."""
    return User.objects.create_user(
        email='customer2@example.com',
        password='TestPass123!',
        role=User.Role.CUSTOMER,
        is_active=True,
    )


@pytest.mark.django_db
class TestStorefrontViews:
    """Storefront marketplace views, search, and filtering."""

    def test_storefront_home_shows_active_products(self, client, active_product):
        response = client.get(reverse('store:home'))
        assert response.status_code == 200
        assert active_product.name in response.content.decode()

    def test_storefront_home_hides_draft_products(self, client, vendor_profile, category):
        draft_prod = Product.objects.create(
            vendor=vendor_profile,
            category=category,
            name='Secret Prototype X',
            sku='PROTO-X',
            description='Unreleased item.',
            price=Decimal('999.00'),
            status=Product.Status.DRAFT,
        )
        response = client.get(reverse('store:home'))
        assert response.status_code == 200
        assert draft_prod.name not in response.content.decode()

    def test_product_list_search_by_name(self, client, active_product):
        url = reverse('store:product_list')
        response = client.get(f'{url}?q=Ultrabook')
        assert response.status_code == 200
        assert len(response.context['products']) == 1
        assert response.context['products'][0] == active_product

    def test_product_list_category_filter(self, client, active_product, category):
        url = reverse('store:product_list')
        response = client.get(f'{url}?category={category.slug}')
        assert response.status_code == 200
        assert active_product in response.context['products']

    def test_product_detail_view_active(self, client, active_product):
        url = reverse('store:product_detail', kwargs={'pk': active_product.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert response.context['product'] == active_product

    def test_product_detail_view_draft_returns_404(self, client, vendor_profile, category):
        draft_prod = Product.objects.create(
            vendor=vendor_profile,
            category=category,
            name='Internal Draft Product',
            sku='DRAFT-INTERNAL',
            description='Internal only.',
            price=Decimal('500.00'),
            status=Product.Status.DRAFT,
        )
        url = reverse('store:product_detail', kwargs={'pk': draft_prod.pk})
        response = client.get(url)
        assert response.status_code == 404


@pytest.mark.django_db
class TestShoppingCartOperations:
    """Shopping cart add, update, remove, stock validation, and totals."""

    def test_unauthenticated_cart_access_redirects(self, client):
        response = client.get(reverse('orders:cart'))
        assert response.status_code == 302
        assert reverse('accounts:login') in response.url

    def test_add_to_cart(self, customer_client, customer_user, active_product):
        url = reverse('orders:cart_add')
        response = customer_client.post(url, {'product_id': active_product.pk, 'quantity': 2})
        assert response.status_code == 302
        cart = Cart.objects.get(user=customer_user)
        assert cart.items.count() == 1
        item = cart.items.first()
        assert item.product == active_product
        assert item.quantity == 2
        assert item.total_price == Decimal('2400.00')

    def test_add_to_cart_increments_existing_item(self, customer_client, customer_user, active_product):
        url = reverse('orders:cart_add')
        customer_client.post(url, {'product_id': active_product.pk, 'quantity': 2})
        customer_client.post(url, {'product_id': active_product.pk, 'quantity': 3})
        cart = Cart.objects.get(user=customer_user)
        assert cart.items.count() == 1
        assert cart.items.first().quantity == 5

    def test_add_to_cart_caps_at_available_stock(self, customer_client, customer_user, active_product):
        # active_product has inventory quantity = 10
        url = reverse('orders:cart_add')
        customer_client.post(url, {'product_id': active_product.pk, 'quantity': 25})
        cart = Cart.objects.get(user=customer_user)
        assert cart.items.first().quantity == 10  # Capped at stock

    def test_update_cart_item_quantity(self, customer_client, customer_user, active_product):
        cart = Cart.objects.create(user=customer_user)
        item = CartItem.objects.create(cart=cart, product=active_product, quantity=2)

        url = reverse('orders:cart_update', kwargs={'pk': item.pk})
        response = customer_client.post(url, {'quantity': 4})
        assert response.status_code == 302
        item.refresh_from_db()
        assert item.quantity == 4

    def test_update_cart_item_zero_removes_item(self, customer_client, customer_user, active_product):
        cart = Cart.objects.create(user=customer_user)
        item = CartItem.objects.create(cart=cart, product=active_product, quantity=2)

        url = reverse('orders:cart_update', kwargs={'pk': item.pk})
        customer_client.post(url, {'quantity': 0})
        assert not CartItem.objects.filter(pk=item.pk).exists()

    def test_remove_from_cart(self, customer_client, customer_user, active_product):
        cart = Cart.objects.create(user=customer_user)
        item = CartItem.objects.create(cart=cart, product=active_product, quantity=1)

        url = reverse('orders:cart_remove', kwargs={'pk': item.pk})
        response = customer_client.post(url)
        assert response.status_code == 302
        assert not CartItem.objects.filter(pk=item.pk).exists()

    def test_clear_cart(self, customer_client, customer_user, active_product):
        cart = Cart.objects.create(user=customer_user)
        CartItem.objects.create(cart=cart, product=active_product, quantity=2)

        url = reverse('orders:cart_clear')
        customer_client.post(url)
        assert cart.items.count() == 0


@pytest.mark.django_db
class TestCheckoutAndOrderProcessing:
    """Checkout, concurrency-safe inventory deduction, and order snapshots."""

    def test_checkout_empty_cart_redirects(self, customer_client):
        response = customer_client.get(reverse('orders:checkout'))
        assert response.status_code == 302
        assert reverse('orders:cart') in response.url

    def test_successful_place_order_deducts_inventory(self, customer_client, customer_user, active_product):
        cart = Cart.objects.create(user=customer_user)
        CartItem.objects.create(cart=cart, product=active_product, quantity=3)

        url = reverse('orders:place_order')
        post_data = {
            'shipping_first_name': 'Alice',
            'shipping_last_name': 'Smith',
            'shipping_phone': '+91 9876543210',
            'shipping_address': 'Flat 4B, Palm Grove',
            'shipping_city': 'Bangalore',
            'shipping_state': 'Karnataka',
            'shipping_postal_code': '560001',
            'shipping_country': 'India',
            'payment_method': 'COD',
            'save_address': '1',
        }
        response = customer_client.post(url, post_data)
        assert response.status_code == 302

        # Check Order
        order = Order.objects.get(user=customer_user)
        assert order.status == Order.Status.CONFIRMED
        assert order.shipping_first_name == 'Alice'
        assert order.subtotal == Decimal('3600.00')

        # Check Order Item
        order_item = order.items.first()
        assert order_item.product == active_product
        assert order_item.quantity == 3
        assert order_item.unit_price == Decimal('1200.00')
        assert order_item.total_price == Decimal('3600.00')

        # Check Inventory deduction: was 10, subtracted 3 -> 7
        active_product.inventory.refresh_from_db()
        assert active_product.inventory.quantity == 7

        # Check Cart cleared
        assert cart.items.count() == 0

        # Check Address saved
        assert Address.objects.filter(user=customer_user).count() == 1

        # Check Payment record
        payment = order.payments.first()
        assert payment.method == Payment.Method.COD
        assert payment.amount == order.total

    def test_place_order_prevents_overselling(self, customer_client, customer_user, active_product):
        cart = Cart.objects.create(user=customer_user)
        # Attempt to order 12 when inventory has 10
        CartItem.objects.create(cart=cart, product=active_product, quantity=12)

        url = reverse('orders:place_order')
        post_data = {
            'shipping_first_name': 'Bob',
            'shipping_last_name': 'Jones',
            'shipping_phone': '+91 9999999999',
            'shipping_address': '123 Street',
            'shipping_city': 'Mumbai',
            'shipping_state': 'Maharashtra',
            'shipping_postal_code': '400001',
            'payment_method': 'COD',
        }
        response = customer_client.post(url, post_data)
        assert response.status_code == 302
        assert reverse('orders:cart') in response.url
        # Order should NOT have been created
        assert Order.objects.filter(user=customer_user).count() == 0
        # Inventory untouched
        active_product.inventory.refresh_from_db()
        assert active_product.inventory.quantity == 10


@pytest.mark.django_db
class TestCustomerPrivacyAndAuthorization:
    """Verify isolation of carts and orders between customers and vendors."""

    def test_customer_cannot_view_other_customer_cart(
        self, client, customer_user, second_customer_user, active_product
    ):
        cart1 = Cart.objects.create(user=customer_user)
        CartItem.objects.create(cart=cart1, product=active_product, quantity=1)

        # Login as second customer
        client.force_login(second_customer_user)
        response = client.get(reverse('orders:cart'))
        assert response.status_code == 200
        # Second customer should see 0 items in their cart
        assert len(response.context['items']) == 0

    def test_customer_cannot_view_other_customer_order(
        self, client, customer_user, second_customer_user, active_product
    ):
        order = Order.objects.create(
            user=customer_user,
            email=customer_user.email,
            shipping_first_name='Alice',
            shipping_last_name='Customer',
            shipping_address='Street 1',
            shipping_city='City',
            shipping_state='State',
            shipping_postal_code='110001',
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
        )

        client.force_login(second_customer_user)
        url = reverse('orders:order_detail', kwargs={'order_number': order.order_number})
        response = client.get(url)
        # Should return 404 because queryset is filtered by request.user
        assert response.status_code == 404

    def test_vendor_cannot_view_customer_orders_list(
        self, client, vendor_user, customer_user, active_product
    ):
        # Vendor logs into customer order history
        client.force_login(vendor_user)
        response = client.get(reverse('orders:order_list'))
        assert response.status_code == 200
        # Vendor has no personal customer orders
        assert len(response.context['orders']) == 0
