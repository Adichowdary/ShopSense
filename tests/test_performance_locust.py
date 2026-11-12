"""
Performance Benchmarking Tests for ShopSense Analytics APIs (Module 10).
Simulates repetitive concurrent queries across all 6 analytical API categories:
1. Vendor Analytics
2. Demand Forecasting
3. Customer RFM Segmentation
4. Product Recommendations
5. Revenue Analytics & Timeseries
6. Marketplace Benchmarking

Measures response latencies, calculates percentiles (P50, P90, P95, P99),
and asserts that P95 response time is strictly <= 300ms.
"""

import time
import pytest
import numpy as np
from decimal import Decimal

from accounts.models import User
from catalog.models import Category, Inventory, Product
from orders.models import Order, OrderItem
from vendors.models import VendorProfile

from api.routers.vendor import get_vendor_summary
from api.routers.revenue import get_daily_revenue, get_monthly_revenue
from api.routers.customers import get_customer_segments
from api.routers.recommendations import get_popular_recommendations
from api.routers.forecast import get_demand_forecast
from api.routers.benchmarking import get_marketplace_benchmarks


@pytest.fixture
def benchmark_data(db):
    admin = User.objects.create_superuser(
        email='perf_admin@shopsense.com',
        password='PerfPassword123!',
    )
    v_user = User.objects.create_user(
        email='perf_vendor@shopsense.com',
        password='PerfPassword123!',
        role=User.Role.VENDOR,
    )
    vendor = VendorProfile.objects.create(
        user=v_user,
        vendor_id='VND-PERF-01',
        business_name='Performance Store',
        contact_email=v_user.email,
        is_active=True,
    )
    cat = Category.objects.create(name='PerfCategory', slug='perf-cat')
    prod = Product.objects.create(
        vendor=vendor,
        category=cat,
        name='Perf Gadget',
        slug='perf-gadget',
        sku='PERF-SKU-01',
        price=Decimal('2500.00'),
        status=Product.Status.ACTIVE,
    )
    Inventory.objects.create(product=prod, quantity=100, low_stock_threshold=10)
    customer = User.objects.create_user(
        email='perf_cust@shopsense.com',
        password='PerfPassword123!',
        role=User.Role.CUSTOMER,
    )
    order = Order.objects.create(
        user=customer,
        order_number='ORD-PERF-101',
        status=Order.Status.DELIVERED,
        subtotal=Decimal('2500.00'),
        total=Decimal('2500.00'),
    )
    OrderItem.objects.create(
        order=order,
        product=prod,
        vendor=vendor,
        product_name=prod.name,
        product_sku=prod.sku,
        quantity=1,
        unit_price=Decimal('2500.00'),
        total_price=Decimal('2500.00'),
        status=OrderItem.Status.DELIVERED,
    )
    return {'admin': admin, 'vendor': vendor, 'product': prod}


@pytest.mark.django_db
class TestApiPerformanceBenchmark:
    """Benchmark all 6 API categories and verify P95 <= 300ms."""

    def test_p95_latency_under_300ms(self, benchmark_data):
        admin = benchmark_data['admin']
        sku = benchmark_data['product'].sku
        latencies_ms = []

        # Warm-up run
        get_daily_revenue(days=30, user=admin)

        # Execute measurement iterations across endpoints
        for _ in range(10):
            # 1. Daily Revenue Timeseries
            t0 = time.perf_counter()
            get_daily_revenue(days=30, user=admin)
            latencies_ms.append((time.perf_counter() - t0) * 1000)

            # 2. Monthly Revenue
            t0 = time.perf_counter()
            get_monthly_revenue(months_in_days=180, user=admin)
            latencies_ms.append((time.perf_counter() - t0) * 1000)

            # 3. Vendor Summary
            t0 = time.perf_counter()
            get_vendor_summary(vendor_id=None, user=admin)
            latencies_ms.append((time.perf_counter() - t0) * 1000)

            # 4. Customer RFM Segments
            t0 = time.perf_counter()
            get_customer_segments(user=admin)
            latencies_ms.append((time.perf_counter() - t0) * 1000)

            # 5. Popular Recommendations
            t0 = time.perf_counter()
            get_popular_recommendations(limit=5, user=admin)
            latencies_ms.append((time.perf_counter() - t0) * 1000)

            # 6. Marketplace Benchmarking
            t0 = time.perf_counter()
            get_marketplace_benchmarks(user=admin)
            latencies_ms.append((time.perf_counter() - t0) * 1000)

            # 7. Demand Forecasting
            t0 = time.perf_counter()
            get_demand_forecast(product_id=benchmark_data['product'].id, horizon_days=14, user=admin)
            latencies_ms.append((time.perf_counter() - t0) * 1000)

        # Compute Percentiles
        p50 = float(np.percentile(latencies_ms, 50))
        p90 = float(np.percentile(latencies_ms, 90))
        p95 = float(np.percentile(latencies_ms, 95))
        p99 = float(np.percentile(latencies_ms, 99))
        mean_lat = float(np.mean(latencies_ms))
        max_lat = float(np.max(latencies_ms))

        print(f"\n--- API Performance Benchmark Results ({len(latencies_ms)} queries) ---")
        print(f"Mean Latency: {mean_lat:.2f}ms")
        print(f"P50 (Median): {p50:.2f}ms")
        print(f"P90:          {p90:.2f}ms")
        print(f"P95:          {p95:.2f}ms (Target: <= 300ms)")
        print(f"P99:          {p99:.2f}ms")
        print(f"Max:          {max_lat:.2f}ms")

        # Mandatory Quantitative Target Assertion
        assert p95 <= 300.0, f"P95 latency {p95:.2f}ms exceeded 300ms threshold!"
