"""
Tests for FastAPI Analytics APIs.
Verifies all 6 analytical domains, RBAC authorization logic,
multi-tenant vendor isolation, and parameter validation.
"""

import pytest
from fastapi import HTTPException

from accounts.models import User
from api.auth import require_admin, require_vendor, require_admin_or_vendor
from api.routers.vendor import (
    get_vendor_summary,
    get_vendor_products_performance,
    get_vendor_inventory_summary,
    resolve_target_vendor,
)
from api.routers.forecast import (
    get_demand_forecast,
    get_forecast_accuracy,
    get_replenishment_suggestions,
)
from api.routers.customers import (
    get_customer_segments,
    get_customer_behavior,
    get_high_spenders,
    get_dormant_cohort,
)
from api.routers.recommendations import (
    get_popular_recommendations,
    get_co_purchased_recommendations,
    get_customer_personalized_recommendations,
    get_recommendation_performance,
)
from api.routers.revenue import (
    get_daily_revenue,
    get_monthly_revenue,
    get_revenue_growth,
    get_sales_trends,
    get_top_products,
)
from api.routers.benchmarking import (
    get_marketplace_benchmarks,
    get_vendor_comparisons,
)
from catalog.models import Category, Inventory, Product
from orders.models import Order, OrderItem
from vendors.models import VendorProfile

pytestmark = pytest.mark.django_db


@pytest.fixture
def test_data(db):
    """Set up vendor, products, orders, and customer for API analytics tests."""
    v_user = User.objects.create_user(
        email='api_vendor@example.com',
        password='TestPass123!',
        role=User.Role.VENDOR,
    )
    vendor = VendorProfile.objects.create(
        user=v_user,
        vendor_id='VND99999999',
        business_name='API Test Store',
        contact_email='api_vendor@example.com',
        is_active=True,
    )

    v_user2 = User.objects.create_user(
        email='api_vendor2@example.com',
        password='TestPass123!',
        role=User.Role.VENDOR,
    )
    vendor2 = VendorProfile.objects.create(
        user=v_user2,
        vendor_id='VND88888888',
        business_name='Second Store',
        contact_email='api_vendor2@example.com',
        is_active=True,
    )

    admin = User.objects.create_superuser(
        email='api_admin@example.com',
        password='AdminPass123!',
    )

    customer = User.objects.create_user(
        email='api_customer@example.com',
        password='CustPass123!',
        role=User.Role.CUSTOMER,
    )

    cat = Category.objects.create(name='Electronics', slug='electronics')
    prod = Product.objects.create(
        vendor=vendor,
        category=cat,
        name='Smart Watch Pro',
        slug='smart-watch-pro',
        sku='SW-PRO-01',
        price=1999.00,
        status=Product.Status.ACTIVE,
    )
    Inventory.objects.create(product=prod, quantity=50, low_stock_threshold=10)

    order = Order.objects.create(
        user=customer,
        order_number='ORD-API-001',
        status=Order.Status.DELIVERED,
        subtotal=1999.00,
        total=1999.00,
    )
    OrderItem.objects.create(
        order=order,
        product=prod,
        vendor=vendor,
        product_name=prod.name,
        product_sku=prod.sku,
        unit_price=prod.price,
        quantity=1,
        total_price=prod.price,
        status=OrderItem.Status.DELIVERED,
    )

    return {
        'admin': admin,
        'vendor': vendor,
        'vendor_user': v_user,
        'vendor2': vendor2,
        'vendor2_user': v_user2,
        'customer': customer,
        'product': prod,
        'order': order,
    }


class TestAuthAndRBAC:
    """Tests authentication dependencies and role verification."""

    def test_require_admin_allows_admin(self, test_data):
        admin = test_data['admin']
        user = require_admin(user=admin)
        assert user == admin

    def test_require_admin_blocks_vendor_and_customer(self, test_data):
        vendor_user = test_data['vendor_user']
        customer = test_data['customer']
        with pytest.raises(HTTPException) as exc:
            require_admin(user=vendor_user)
        assert exc.value.status_code == 403

        with pytest.raises(HTTPException) as exc:
            require_admin(user=customer)
        assert exc.value.status_code == 403

    def test_require_vendor_allows_active_vendor(self, test_data):
        vendor_user = test_data['vendor_user']
        user = require_vendor(user=vendor_user)
        assert user == vendor_user

    def test_require_vendor_blocks_customer(self, test_data):
        customer = test_data['customer']
        with pytest.raises(HTTPException) as exc:
            require_vendor(user=customer)
        assert exc.value.status_code == 403


class TestVendorAnalyticsAPI:
    """Tests Vendor Analytics endpoints."""

    def test_vendor_summary(self, test_data):
        vendor_user = test_data['vendor_user']
        res = get_vendor_summary(vendor_id=None, user=vendor_user)
        assert res.vendor_id == 'VND99999999'
        assert res.total_sales == 1999.00
        assert res.total_orders == 1
        assert res.active_products_count == 1

    def test_vendor_cannot_access_other_vendor(self, test_data):
        vendor_user = test_data['vendor_user']
        vendor2 = test_data['vendor2']
        with pytest.raises(HTTPException) as exc:
            resolve_target_vendor(user=vendor_user, vendor_id=vendor2.id)
        assert exc.value.status_code == 403

    def test_admin_can_inspect_any_vendor(self, test_data):
        admin = test_data['admin']
        vendor = test_data['vendor']
        res = get_vendor_summary(vendor_id=vendor.id, user=admin)
        assert res.vendor_id == 'VND99999999'

    def test_vendor_products_performance(self, test_data):
        vendor_user = test_data['vendor_user']
        res = get_vendor_products_performance(vendor_id=None, limit=10, offset=0, user=vendor_user)
        assert len(res) == 1
        assert res[0].sku == 'SW-PRO-01'
        assert res[0].units_sold == 1
        assert res[0].revenue == 1999.00

    def test_vendor_inventory_summary(self, test_data):
        vendor_user = test_data['vendor_user']
        res = get_vendor_inventory_summary(vendor_id=None, user=vendor_user)
        assert res.total_stock_on_hand == 50
        assert res.available_stock >= 0


class TestForecastingAPI:
    """Tests Forecasting Analytics endpoints."""

    def test_demand_forecast(self, test_data):
        admin = test_data['admin']
        prod = test_data['product']
        res = get_demand_forecast(product_id=prod.id, horizon_days=14, user=admin)
        assert res.product_id == prod.id
        assert res.horizon_days == 14
        assert len(res.predictions) == 14
        assert res.accuracy_percentage >= 0.0

    def test_forecast_accuracy(self, test_data):
        admin = test_data['admin']
        res = get_forecast_accuracy(user=admin)
        assert res.overall_accuracy >= 0.0

    def test_replenishment_suggestions(self, test_data):
        admin = test_data['admin']
        res = get_replenishment_suggestions(limit=10, user=admin)
        assert isinstance(res, list)


class TestCustomerIntelligenceAPI:
    """Tests Customer Intelligence endpoints."""

    def test_customer_segments(self, test_data):
        admin = test_data['admin']
        res = get_customer_segments(user=admin)
        assert len(res.segments) > 0
        codes = [s.code for s in res.segments]
        assert 'CHAMPIONS' in codes

    def test_customer_behavior(self, test_data):
        admin = test_data['admin']
        res = get_customer_behavior(user=admin)
        assert res.total_customers >= 1
        assert res.average_spend >= 0.0
        assert res.customer_lifetime_value >= 0.0

    def test_high_spenders(self, test_data):
        admin = test_data['admin']
        res = get_high_spenders(limit=5, user=admin)
        assert isinstance(res, list)

    def test_dormant_cohort(self, test_data):
        admin = test_data['admin']
        res = get_dormant_cohort(limit=5, user=admin)
        assert isinstance(res, list)


class TestRecommendationAPI:
    """Tests Recommendation Intelligence endpoints."""

    def test_popular_recommendations(self, test_data):
        admin = test_data['admin']
        res = get_popular_recommendations(limit=5, user=admin)
        assert res.strategy == 'POPULAR'
        assert isinstance(res.recommendations, list)

    def test_co_purchased_recommendations(self, test_data):
        admin = test_data['admin']
        prod = test_data['product']
        res = get_co_purchased_recommendations(product_id=prod.id, limit=4, user=admin)
        assert res.strategy == 'CO_PURCHASE'

    def test_personalized_recommendations_owner_or_admin(self, test_data):
        admin = test_data['admin']
        customer = test_data['customer']
        # Admin can view
        res = get_customer_personalized_recommendations(customer_id=customer.id, limit=5, current_user=admin)
        assert res.strategy == 'PERSONALIZED'

        # Customer can view own
        res_own = get_customer_personalized_recommendations(customer_id=customer.id, limit=5, current_user=customer)
        assert res_own.strategy == 'PERSONALIZED'

    def test_customer_cannot_view_other_recommendations(self, test_data):
        customer = test_data['customer']
        other_user = test_data['vendor_user']
        with pytest.raises(HTTPException) as exc:
            get_customer_personalized_recommendations(customer_id=other_user.id, limit=5, current_user=customer)
        assert exc.value.status_code == 403

    def test_recommendation_performance(self, test_data):
        admin = test_data['admin']
        res = get_recommendation_performance(user=admin)
        assert res.precision_at_k >= 0.0
        assert res.coverage_percentage >= 0.0


class TestRevenueAnalyticsAPI:
    """Tests Revenue Analytics endpoints."""

    def test_daily_revenue(self, test_data):
        admin = test_data['admin']
        res = get_daily_revenue(days=14, user=admin)
        assert res.period == 'day'
        assert len(res.data) == 15

    def test_revenue_growth(self, test_data):
        admin = test_data['admin']
        res = get_revenue_growth(user=admin)
        assert res.current_period_revenue >= 1999.00
        assert isinstance(res.revenue_growth_percent, float)

    def test_sales_trends(self, test_data):
        admin = test_data['admin']
        res = get_sales_trends(user=admin)
        assert len(res.categories) >= 1
        assert res.categories[0].category == 'Electronics'

    def test_top_products(self, test_data):
        admin = test_data['admin']
        res = get_top_products(limit=5, user=admin)
        assert len(res) >= 1
        assert res[0].sku == 'SW-PRO-01'


class TestBenchmarkingAPI:
    """Tests Marketplace Benchmarking endpoints."""

    def test_marketplace_benchmarks(self, test_data):
        admin = test_data['admin']
        res = get_marketplace_benchmarks(user=admin)
        assert res.total_marketplace_revenue >= 1999.00
        assert res.total_orders >= 1
        assert len(res.top_vendors) >= 1
        assert res.top_vendors[0].name == 'API Test Store'

    def test_vendor_comparisons(self, test_data):
        admin = test_data['admin']
        res = get_vendor_comparisons(user=admin)
        assert len(res) >= 1
