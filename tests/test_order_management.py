"""
Comprehensive automated tests for ShopSense Phase 4:
Secure Admin & Vendor Order Management.
Tests cover authorization mixins, multi-vendor isolation,
status transition state machines, auto timestamps, and security audit logs.
"""

from decimal import Decimal
import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalog.models import Category, Inventory, Product
from orders.models import Address, Order, OrderItem, Payment
from orders.services import update_order_status, update_vendor_order_item_status
from vendors.models import AuditLog, VendorProfile


@pytest.fixture
def category():
    cat, _ = Category.objects.get_or_create(
        slug='electronics',
        defaults={'name': 'Electronics', 'is_active': True}
    )
    return cat


@pytest.fixture
def vendor_user_1():
    user = User.objects.create_user(
        email='vendor1@example.com',
        password='TestPass123!',
        role=User.Role.VENDOR,
        first_name='Alpha',
        last_name='Vendor',
    )
    return user


@pytest.fixture
def vendor_profile_1(vendor_user_1):
    return VendorProfile.objects.create(
        user=vendor_user_1,
        vendor_id='VND10000001',
        business_name='Alpha Tech',
        contact_email=vendor_user_1.email,
        is_active=True,
        is_verified=True,
    )


@pytest.fixture
def vendor_user_2():
    user = User.objects.create_user(
        email='vendor2@example.com',
        password='TestPass123!',
        role=User.Role.VENDOR,
        first_name='Beta',
        last_name='Vendor',
    )
    return user


@pytest.fixture
def vendor_profile_2(vendor_user_2):
    return VendorProfile.objects.create(
        user=vendor_user_2,
        vendor_id='VND20000002',
        business_name='Beta Electronics',
        contact_email=vendor_user_2.email,
        is_active=True,
        is_verified=True,
    )


@pytest.fixture
def vendor_user_3():
    """Third vendor who has no items in test orders."""
    user = User.objects.create_user(
        email='vendor3@example.com',
        password='TestPass123!',
        role=User.Role.VENDOR,
        first_name='Gamma',
        last_name='Vendor',
    )
    return user


@pytest.fixture
def vendor_profile_3(vendor_user_3):
    return VendorProfile.objects.create(
        user=vendor_user_3,
        vendor_id='VND30000003',
        business_name='Gamma Gadgets',
        contact_email=vendor_user_3.email,
        is_active=True,
        is_verified=True,
    )


@pytest.fixture
def product_alpha(vendor_profile_1, category):
    prod = Product.objects.create(
        vendor=vendor_profile_1,
        category=category,
        name='Alpha Mechanical Keyboard',
        slug='alpha-keyboard',
        sku='ALPHA-KB-01',
        description='Premium mechanical keyboard.',
        price=Decimal('100.00'),
        status=Product.Status.ACTIVE,
    )
    Inventory.objects.create(product=prod, quantity=50)
    return prod


@pytest.fixture
def product_beta(vendor_profile_2, category):
    prod = Product.objects.create(
        vendor=vendor_profile_2,
        category=category,
        name='Beta Wireless Mouse',
        slug='beta-mouse',
        sku='BETA-MS-02',
        description='Ergonomic wireless mouse.',
        price=Decimal('50.00'),
        status=Product.Status.ACTIVE,
    )
    Inventory.objects.create(product=prod, quantity=50)
    return prod


@pytest.fixture
def multi_vendor_order(customer_user, product_alpha, product_beta, vendor_profile_1, vendor_profile_2):
    """
    Creates an order containing items from both Vendor 1 (Alpha) and Vendor 2 (Beta).
    """
    order = Order.objects.create(
        order_number='ORD202610250001',
        user=customer_user,
        email=customer_user.email,
        phone='9876543210',
        status=Order.Status.CONFIRMED,
        shipping_first_name='John',
        shipping_last_name='Doe',
        shipping_address='123 Tech Park',
        shipping_city='Bengaluru',
        shipping_state='Karnataka',
        shipping_postal_code='560001',
        subtotal=Decimal('150.00'),
        shipping_cost=Decimal('0.00'),
        tax_amount=Decimal('7.50'),
        total=Decimal('157.50'),
        confirmed_at=timezone.now(),
    )

    # Item from Vendor 1
    OrderItem.objects.create(
        order=order,
        product=product_alpha,
        vendor=vendor_profile_1,
        product_name=product_alpha.name,
        product_sku=product_alpha.sku,
        quantity=1,
        unit_price=Decimal('100.00'),
        total_price=Decimal('100.00'),
        status=OrderItem.Status.CONFIRMED,
    )

    # Item from Vendor 2
    OrderItem.objects.create(
        order=order,
        product=product_beta,
        vendor=vendor_profile_2,
        product_name=product_beta.name,
        product_sku=product_beta.sku,
        quantity=1,
        unit_price=Decimal('50.00'),
        total_price=Decimal('50.00'),
        status=OrderItem.Status.CONFIRMED,
    )

    # Payment
    Payment.objects.create(
        order=order,
        payment_id='PAY-ORD202610250001',
        method=Payment.Method.CARD,
        status=Payment.Status.COMPLETED,
        amount=order.total,
    )

    return order


# =========================================================================
# 1. Centralized Authorization & Access Control Tests
# =========================================================================

@pytest.mark.django_db
class TestAdminOrderAuthorization:
    """Verify that only admins can access admin order endpoints."""

    def test_anonymous_cannot_access_admin_orders(self, client):
        url = reverse('dashboard:order_list')
        response = client.get(url)
        assert response.status_code == 302
        assert 'accounts/login' in response.url

    def test_customer_cannot_access_admin_orders(self, customer_client):
        url = reverse('dashboard:order_list')
        response = customer_client.get(url)
        assert response.status_code == 302
        assert 'accounts/login' in response.url

    def test_vendor_cannot_access_admin_orders(self, client, vendor_user_1, vendor_profile_1):
        client.force_login(vendor_user_1)
        url = reverse('dashboard:order_list')
        response = client.get(url)
        assert response.status_code == 302
        assert 'accounts/login' in response.url

    def test_admin_can_access_admin_order_list(self, authenticated_client, multi_vendor_order):
        url = reverse('dashboard:order_list')
        response = authenticated_client.get(url)
        assert response.status_code == 200
        assert multi_vendor_order.order_number in response.content.decode()

    def test_admin_can_access_admin_order_detail(self, authenticated_client, multi_vendor_order):
        url = reverse('dashboard:order_detail', kwargs={'order_number': multi_vendor_order.order_number})
        response = authenticated_client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert multi_vendor_order.order_number in content
        assert 'Alpha Mechanical Keyboard' in content
        assert 'Beta Wireless Mouse' in content


# =========================================================================
# 2. Admin Order Filtering, Search, and Metrics Tests
# =========================================================================

@pytest.mark.django_db
class TestAdminOrderSearchAndFilters:
    """Verify admin order list search and filtering."""

    def test_search_by_order_number(self, authenticated_client, multi_vendor_order):
        url = reverse('dashboard:order_list') + f'?search={multi_vendor_order.order_number}'
        response = authenticated_client.get(url)
        assert response.status_code == 200
        assert multi_vendor_order.order_number in response.content.decode()

    def test_search_by_customer_name(self, authenticated_client, multi_vendor_order):
        url = reverse('dashboard:order_list') + '?search=John'
        response = authenticated_client.get(url)
        assert response.status_code == 200
        assert multi_vendor_order.order_number in response.content.decode()

    def test_filter_by_status(self, authenticated_client, multi_vendor_order):
        # Matching status
        url = reverse('dashboard:order_list') + '?status=CONFIRMED'
        response = authenticated_client.get(url)
        assert multi_vendor_order.order_number in response.content.decode()

        # Non-matching status
        url_pending = reverse('dashboard:order_list') + '?status=PENDING'
        response_pending = authenticated_client.get(url_pending)
        assert multi_vendor_order.order_number not in response_pending.content.decode()

    def test_filter_by_date_range(self, authenticated_client, multi_vendor_order):
        today = timezone.now().strftime('%Y-%m-%d')
        url = reverse('dashboard:order_list') + f'?date_from={today}&date_to={today}'
        response = authenticated_client.get(url)
        assert response.status_code == 200
        assert multi_vendor_order.order_number in response.content.decode()


# =========================================================================
# 3. Order Status State Machine and Audit Trail Tests
# =========================================================================

@pytest.mark.django_db
class TestOrderStatusStateMachineAndAudit:
    """Verify order status transitions, restrictions, and audit logs."""

    def test_valid_admin_status_transitions(self, multi_vendor_order, admin_user):
        # CONFIRMED -> PROCESSING
        update_order_status(multi_vendor_order, Order.Status.PROCESSING, performed_by=admin_user)
        multi_vendor_order.refresh_from_db()
        assert multi_vendor_order.status == Order.Status.PROCESSING

        # PROCESSING -> SHIPPED
        update_order_status(multi_vendor_order, Order.Status.SHIPPED, performed_by=admin_user)
        multi_vendor_order.refresh_from_db()
        assert multi_vendor_order.status == Order.Status.SHIPPED
        assert multi_vendor_order.shipped_at is not None

        # SHIPPED -> DELIVERED
        update_order_status(multi_vendor_order, Order.Status.DELIVERED, performed_by=admin_user)
        multi_vendor_order.refresh_from_db()
        assert multi_vendor_order.status == Order.Status.DELIVERED
        assert multi_vendor_order.delivered_at is not None

    def test_invalid_admin_status_transition_rejected(self, multi_vendor_order, admin_user):
        from django.core.exceptions import ValidationError
        # Cannot jump from CONFIRMED directly to DELIVERED
        with pytest.raises(ValidationError):
            update_order_status(multi_vendor_order, Order.Status.DELIVERED, performed_by=admin_user)

    def test_audit_log_created_on_status_change(self, multi_vendor_order, admin_user):
        initial_log_count = AuditLog.objects.count()
        update_order_status(
            multi_vendor_order,
            Order.Status.PROCESSING,
            performed_by=admin_user,
            notes='Admin started fulfillment packaging'
        )
        assert AuditLog.objects.count() == initial_log_count + 1
        log = AuditLog.objects.latest('created_at')
        assert log.action == AuditLog.ActionType.ORDER_STATUS_CHANGED
        assert log.details['order_number'] == multi_vendor_order.order_number
        assert log.details['old_status'] == Order.Status.CONFIRMED
        assert log.details['new_status'] == Order.Status.PROCESSING
        assert 'Admin started fulfillment' in log.details['notes']

    def test_order_cancellation_cancels_items_and_logs(self, multi_vendor_order, admin_user):
        update_order_status(
            multi_vendor_order,
            Order.Status.CANCELLED,
            performed_by=admin_user,
            notes='Customer requested cancellation'
        )
        multi_vendor_order.refresh_from_db()
        assert multi_vendor_order.status == Order.Status.CANCELLED

        # All items should now be CANCELLED
        for item in multi_vendor_order.items.all():
            assert item.status == OrderItem.Status.CANCELLED

        log = AuditLog.objects.latest('created_at')
        assert log.action == AuditLog.ActionType.ORDER_CANCELLED

    def test_admin_order_status_update_view_post(self, authenticated_client, multi_vendor_order):
        url = reverse('dashboard:order_status_update', kwargs={'order_number': multi_vendor_order.order_number})
        response = authenticated_client.post(url, {
            'status': Order.Status.PROCESSING,
            'admin_notes': 'Processing through UI test',
        })
        assert response.status_code == 302
        multi_vendor_order.refresh_from_db()
        assert multi_vendor_order.status == Order.Status.PROCESSING


# =========================================================================
# 4. Multi-Vendor Isolation & Privacy Tests
# =========================================================================

@pytest.mark.django_db
class TestMultiVendorIsolation:
    """Verify strict database-level isolation between different vendors."""

    def test_vendor_access_own_order_list(self, client, vendor_user_1, vendor_profile_1, multi_vendor_order):
        client.force_login(vendor_user_1)
        url = reverse('vendors:order_list')
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert multi_vendor_order.order_number in content
        # Vendor 1 should see only their item's subtotal (₹100), not the full order total (₹157.50)
        assert '100.00' in content

    def test_unrelated_vendor_does_not_see_order_in_list(self, client, vendor_user_3, vendor_profile_3, multi_vendor_order):
        client.force_login(vendor_user_3)
        url = reverse('vendors:order_list')
        response = client.get(url)
        assert response.status_code == 200
        assert multi_vendor_order.order_number not in response.content.decode()

    def test_vendor_order_detail_shows_only_own_items(self, client, vendor_user_1, vendor_profile_1, multi_vendor_order):
        client.force_login(vendor_user_1)
        url = reverse('vendors:order_detail', kwargs={'order_number': multi_vendor_order.order_number})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()

        # Vendor 1 owns Alpha Mechanical Keyboard
        assert 'Alpha Mechanical Keyboard' in content
        # Vendor 1 MUST NOT see Vendor 2's Beta Wireless Mouse
        assert 'Beta Wireless Mouse' not in content

    def test_unrelated_vendor_cannot_view_order_detail(self, client, vendor_user_3, vendor_profile_3, multi_vendor_order):
        client.force_login(vendor_user_3)
        url = reverse('vendors:order_detail', kwargs={'order_number': multi_vendor_order.order_number})
        response = client.get(url)
        # Should return 404 Http404 because queryset is filtered strictly by vendor
        assert response.status_code == 404

    def test_customer_cannot_access_vendor_orders(self, customer_client, multi_vendor_order):
        url = reverse('vendors:order_list')
        response = customer_client.get(url)
        assert response.status_code == 302
        assert 'accounts/login' in response.url

    def test_inactive_vendor_cannot_access_orders(self, client, vendor_user_1, vendor_profile_1):
        vendor_profile_1.is_active = False
        vendor_profile_1.save()
        client.force_login(vendor_user_1)
        url = reverse('vendors:order_list')
        response = client.get(url)
        assert response.status_code == 302
        assert 'accounts/login' in response.url

    def test_vendor_order_search_and_filter(self, client, vendor_user_1, vendor_profile_1, multi_vendor_order):
        client.force_login(vendor_user_1)
        # Search by order number
        url_search = reverse('vendors:order_list') + f'?search={multi_vendor_order.order_number}'
        resp_search = client.get(url_search)
        assert multi_vendor_order.order_number in resp_search.content.decode()

        # Filter by status matching
        url_status = reverse('vendors:order_list') + '?status=CONFIRMED'
        resp_status = client.get(url_status)
        assert multi_vendor_order.order_number in resp_status.content.decode()

        # Filter by status non-matching
        url_mismatch = reverse('vendors:order_list') + '?status=SHIPPED'
        resp_mismatch = client.get(url_mismatch)
        assert multi_vendor_order.order_number not in resp_mismatch.content.decode()


# =========================================================================
# 5. Vendor Item Fulfillment & Parent Order Sync Tests
# =========================================================================

@pytest.mark.django_db
class TestVendorItemFulfillment:
    """Verify vendor item fulfillment actions and parent order synchronization."""

    def test_vendor_can_advance_item_status(self, client, vendor_user_1, vendor_profile_1, multi_vendor_order):
        client.force_login(vendor_user_1)
        item = multi_vendor_order.items.get(vendor=vendor_profile_1)

        url = reverse('vendors:order_item_fulfill', kwargs={
            'order_number': multi_vendor_order.order_number,
            'item_pk': item.pk,
        })
        response = client.post(url, {'status': OrderItem.Status.PROCESSING})
        assert response.status_code == 302
        item.refresh_from_db()
        assert item.status == OrderItem.Status.PROCESSING

    def test_vendor_item_fulfillment_creates_audit_log(self, vendor_profile_1, multi_vendor_order, vendor_user_1):
        initial_logs = AuditLog.objects.count()
        item = multi_vendor_order.items.get(vendor=vendor_profile_1)
        update_vendor_order_item_status(
            item=item,
            new_status=OrderItem.Status.PROCESSING,
            vendor_profile=vendor_profile_1,
            performed_by=vendor_user_1,
        )
        assert AuditLog.objects.count() == initial_logs + 1
        log = AuditLog.objects.latest('created_at')
        assert log.action == AuditLog.ActionType.ORDER_ITEM_FULFILLED
        assert log.target_vendor == vendor_profile_1
        assert log.details['order_number'] == multi_vendor_order.order_number

    def test_vendor_cannot_fulfill_other_vendors_item(self, client, vendor_user_1, vendor_profile_1, vendor_profile_2, multi_vendor_order):
        client.force_login(vendor_user_1)
        # Try to fulfill Vendor 2's item while logged in as Vendor 1
        item_2 = multi_vendor_order.items.get(vendor=vendor_profile_2)

        url = reverse('vendors:order_item_fulfill', kwargs={
            'order_number': multi_vendor_order.order_number,
            'item_pk': item_2.pk,
        })
        response = client.post(url, {'status': OrderItem.Status.PROCESSING})
        # Should 404 because get_object_or_404 enforces vendor=request.user.vendor_profile
        assert response.status_code == 404

    def test_vendor_invalid_item_transition_rejected(self, vendor_profile_1, multi_vendor_order):
        from django.core.exceptions import ValidationError
        item = multi_vendor_order.items.get(vendor=vendor_profile_1)
        # Cannot jump directly from CONFIRMED to DELIVERED
        with pytest.raises(ValidationError):
            update_vendor_order_item_status(item, OrderItem.Status.DELIVERED, vendor_profile_1)

    def test_all_items_shipped_syncs_parent_order(self, vendor_profile_1, vendor_profile_2, multi_vendor_order):
        item_1 = multi_vendor_order.items.get(vendor=vendor_profile_1)
        item_2 = multi_vendor_order.items.get(vendor=vendor_profile_2)

        # Fulfill item 1 to SHIPPED
        update_vendor_order_item_status(item_1, OrderItem.Status.PROCESSING, vendor_profile_1)
        update_vendor_order_item_status(item_1, OrderItem.Status.SHIPPED, vendor_profile_1)
        multi_vendor_order.refresh_from_db()
        # Item 2 is still CONFIRMED, parent order should be PROCESSING, not yet SHIPPED
        assert multi_vendor_order.status == Order.Status.PROCESSING

        # Fulfill item 2 to SHIPPED
        update_vendor_order_item_status(item_2, OrderItem.Status.PROCESSING, vendor_profile_2)
        update_vendor_order_item_status(item_2, OrderItem.Status.SHIPPED, vendor_profile_2)
        multi_vendor_order.refresh_from_db()
        # Now that ALL items are shipped, parent order status advances to SHIPPED automatically
        assert multi_vendor_order.status == Order.Status.SHIPPED
        assert multi_vendor_order.shipped_at is not None

    def test_all_items_delivered_syncs_parent_order(self, vendor_profile_1, vendor_profile_2, multi_vendor_order):
        item_1 = multi_vendor_order.items.get(vendor=vendor_profile_1)
        item_2 = multi_vendor_order.items.get(vendor=vendor_profile_2)

        # Fast forward both items to DELIVERED
        update_vendor_order_item_status(item_1, OrderItem.Status.PROCESSING, vendor_profile_1)
        update_vendor_order_item_status(item_1, OrderItem.Status.SHIPPED, vendor_profile_1)
        update_vendor_order_item_status(item_1, OrderItem.Status.DELIVERED, vendor_profile_1)

        update_vendor_order_item_status(item_2, OrderItem.Status.PROCESSING, vendor_profile_2)
        update_vendor_order_item_status(item_2, OrderItem.Status.SHIPPED, vendor_profile_2)
        update_vendor_order_item_status(item_2, OrderItem.Status.DELIVERED, vendor_profile_2)

        multi_vendor_order.refresh_from_db()
        assert multi_vendor_order.status == Order.Status.DELIVERED
        assert multi_vendor_order.delivered_at is not None


# =========================================================================
# 6. Verification Criteria Specific Tests
# =========================================================================

@pytest.mark.django_db
class TestOrderSecurityAndStockIntegrity:
    """Verify criteria 6, 7, and 8 of the verification checklist."""

    def test_vendors_cannot_alter_payment_status_totals_or_refunds(self, client, vendor_user_1, vendor_profile_1, multi_vendor_order):
        client.force_login(vendor_user_1)
        original_total = multi_vendor_order.total
        payment = multi_vendor_order.payments.first()
        original_payment_status = payment.status

        # Vendor cannot post to admin status update view
        url_admin_update = reverse('dashboard:order_status_update', kwargs={'order_number': multi_vendor_order.order_number})
        response = client.post(url_admin_update, {
            'status': Order.Status.REFUNDED,
            'admin_notes': 'Vendor attempting unauthorized refund',
        })
        assert response.status_code == 302
        assert 'accounts/login' in response.url

        # Check that order total and payment status are unchanged
        multi_vendor_order.refresh_from_db()
        payment.refresh_from_db()
        assert multi_vendor_order.total == original_total
        assert multi_vendor_order.status == Order.Status.CONFIRMED
        assert payment.status == original_payment_status

    def test_cancellation_restores_stock_and_prevents_duplicate_updates(self, admin_user, multi_vendor_order, product_alpha, product_beta):
        initial_stock_alpha = product_alpha.inventory.quantity
        initial_stock_beta = product_beta.inventory.quantity

        # First cancellation restores stock
        update_order_status(multi_vendor_order, Order.Status.CANCELLED, performed_by=admin_user)
        product_alpha.inventory.refresh_from_db()
        product_beta.inventory.refresh_from_db()
        multi_vendor_order.refresh_from_db()

        assert multi_vendor_order.status == Order.Status.CANCELLED
        assert product_alpha.inventory.quantity == initial_stock_alpha + 1
        assert product_beta.inventory.quantity == initial_stock_beta + 1

        # Second cancellation attempt (duplicate) should be idempotent and NOT increment stock again
        update_order_status(multi_vendor_order, Order.Status.CANCELLED, performed_by=admin_user)
        product_alpha.inventory.refresh_from_db()
        product_beta.inventory.refresh_from_db()

        assert product_alpha.inventory.quantity == initial_stock_alpha + 1
        assert product_beta.inventory.quantity == initial_stock_beta + 1

    def test_dashboard_metrics_come_from_database(self, authenticated_client, multi_vendor_order):
        url = reverse('dashboard:admin_dashboard')
        response = authenticated_client.get(url)
        assert response.status_code == 200
        order_stats = response.context['order_stats']
        assert order_stats['total'] >= 1
        assert order_stats['revenue'] >= multi_vendor_order.total

