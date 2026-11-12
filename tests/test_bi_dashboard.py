"""
Tests for Business Intelligence Dashboard Views (Module 5).
Validates RBAC (Admin-only access, rejection of Customer/Vendor/Anonymous),
context payload generation, Plotly JSON configurations, and template rendering.
"""

import pytest
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal

from accounts.models import User
from catalog.models import Category, Inventory, Product
from orders.models import Order, OrderItem
from vendors.models import VendorProfile


@pytest.fixture
def admin_user(db):
    user = User.objects.create_superuser(
        email='bi_admin@example.com',
        password='TestPassword123!',
    )
    return user


@pytest.fixture
def vendor_user(db):
    user = User.objects.create_user(
        email='bi_vendor@example.com',
        password='TestPassword123!',
        role=User.Role.VENDOR,
    )
    VendorProfile.objects.create(
        user=user,
        vendor_id='VND-BI-101',
        business_name='BI Test Store',
        contact_email=user.email,
        is_active=True,
    )
    return user


@pytest.fixture
def customer_user(db):
    user = User.objects.create_user(
        email='bi_customer@example.com',
        password='TestPassword123!',
        role=User.Role.CUSTOMER,
    )
    return user


@pytest.fixture
def sample_data(db, vendor_user, customer_user):
    vendor = vendor_user.vendor_profile
    cat = Category.objects.create(name='Tech Gadgets', slug='tech-gadgets')
    prod = Product.objects.create(
        vendor=vendor,
        category=cat,
        name='BI Smart Sensor',
        slug='bi-smart-sensor',
        sku='BI-SENS-01',
        price=Decimal('1500.00'),
        status=Product.Status.ACTIVE,
    )
    Inventory.objects.create(product=prod, quantity=50, low_stock_threshold=10)
    order = Order.objects.create(
        user=customer_user,
        order_number='ORD-BI-1001',
        status=Order.Status.DELIVERED,
        subtotal=Decimal('3000.00'),
        total=Decimal('3000.00'),
    )
    OrderItem.objects.create(
        order=order,
        product=prod,
        vendor=vendor,
        product_name=prod.name,
        product_sku=prod.sku,
        quantity=2,
        unit_price=Decimal('1500.00'),
        total_price=Decimal('3000.00'),
        status=OrderItem.Status.DELIVERED,
    )
    return {'product': prod, 'order': order}


@pytest.mark.django_db
class TestBusinessIntelligenceDashboardRBAC:
    """RBAC validation: Only users with admin dashboard access may open BI dashboards."""

    def test_anonymous_user_redirected_to_login(self, client):
        urls = [
            reverse('dashboard:bi_overview'),
            reverse('dashboard:bi_customers'),
            reverse('dashboard:bi_inventory'),
            reverse('dashboard:bi_recommendations'),
        ]
        for url in urls:
            response = client.get(url)
            assert response.status_code == 302
            assert '/accounts/login/' in response.url

    def test_customer_user_forbidden_from_bi(self, client, customer_user):
        client.force_login(customer_user)
        urls = [
            reverse('dashboard:bi_overview'),
            reverse('dashboard:bi_customers'),
            reverse('dashboard:bi_inventory'),
            reverse('dashboard:bi_recommendations'),
        ]
        for url in urls:
            response = client.get(url)
            assert response.status_code == 302
            assert '/accounts/login/' in response.url

    def test_vendor_user_forbidden_from_admin_bi(self, client, vendor_user):
        client.force_login(vendor_user)
        urls = [
            reverse('dashboard:bi_overview'),
            reverse('dashboard:bi_customers'),
            reverse('dashboard:bi_inventory'),
            reverse('dashboard:bi_recommendations'),
        ]
        for url in urls:
            response = client.get(url)
            assert response.status_code == 302
            assert '/accounts/login/' in response.url


@pytest.mark.django_db
class TestBusinessIntelligenceDashboardViews:
    """Admin authorized access and context verification."""

    def test_admin_overview_renders_successfully(self, client, admin_user, sample_data):
        client.force_login(admin_user)
        url = reverse('dashboard:bi_overview')
        response = client.get(url)

        assert response.status_code == 200
        assert 'revenue_chart_json' in response.context
        assert 'category_chart_json' in response.context
        assert 'kpis' in response.context
        assert response.context['kpis']['total_revenue'] == Decimal('3000.00')
        assert response.context['kpis']['total_orders'] == 1
        assert b'Business Intelligence Overview' in response.content

    def test_admin_overview_date_filtering(self, client, admin_user, sample_data):
        client.force_login(admin_user)
        url = reverse('dashboard:bi_overview') + '?period=7'
        response = client.get(url)
        assert response.status_code == 200
        assert response.context['kpis']['total_orders'] == 1

    def test_customer_intelligence_renders(self, client, admin_user, sample_data):
        client.force_login(admin_user)
        url = reverse('dashboard:bi_customers')
        response = client.get(url)

        assert response.status_code == 200
        assert 'metrics' in response.context
        assert 'segments_chart_json' in response.context
        assert response.context['metrics']['total_customers'] >= 1
        assert b'Customer Intelligence' in response.content

    def test_inventory_intelligence_renders(self, client, admin_user, sample_data):
        client.force_login(admin_user)
        url = reverse('dashboard:bi_inventory')
        response = client.get(url)

        assert response.status_code == 200
        assert 'stock_donut_json' in response.context
        assert 'movement_chart_json' in response.context
        assert 'available_stock' in response.context['kpis']
        assert b'Inventory Intelligence' in response.content

    def test_recommendation_intelligence_renders(self, client, admin_user, sample_data):
        client.force_login(admin_user)
        url = reverse('dashboard:bi_recommendations')
        response = client.get(url)

        assert response.status_code == 200
        assert 'strategy_chart_json' in response.context
        assert 'kpis' in response.context
        assert b'Recommendation Intelligence' in response.content
