"""
Verification script for Section 4: Data Consistency Audit.
1. Independently calculates revenue, orders, customers, products, and inventory from source DB.
2. Compares against RevenueAnalyticsService and InventoryIntelligenceService.
3. Tests CANCELLED and REFUNDED orders to ensure zero leakage into revenue.
4. Tests stock reservation mechanics.
5. Formally verifies consistency >= 99%.
"""

import os
import sys
from decimal import Decimal

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_test')
import django
django.setup()

from django.db.models import Sum, Count
from django.utils import timezone
from accounts.models import User
from catalog.models import Product
from orders.models import Order, OrderItem
from inventory.models import Warehouse, WarehouseStock, DataConsistencyLog
from inventory.services.bi_services import (
    RevenueAnalyticsService,
    CustomerIntelligenceService,
    InventoryIntelligenceService,
)
from inventory.services.consistency_services import DashboardDataConsistencyReconciler


def main():
    print("==================================================================")
    print("  SECTION 4: DATA CONSISTENCY AUDIT & EDGE CASE VERIFICATION")
    print("==================================================================")

    # 1. Independent Calculation from Source Tables
    print("\n--- 1. Independent Source Calculations ---")
    qualified = [Order.Status.CONFIRMED, Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED]

    raw_rev = float(Order.objects.filter(status__in=qualified).aggregate(s=Sum('total'))['s'] or 0.0)
    raw_orders = Order.objects.filter(status__in=qualified).count()
    raw_products = Product.objects.filter(status=Product.Status.ACTIVE).count()
    raw_customers = User.objects.filter(role=User.Role.CUSTOMER, is_active=True).count()
    raw_stock = int(WarehouseStock.objects.aggregate(s=Sum('quantity'))['s'] or 0)

    # Dashboard values
    kpis = RevenueAnalyticsService.get_kpis()
    inv_kpis = InventoryIntelligenceService.get_inventory_kpis()
    cust_metrics = CustomerIntelligenceService.get_customer_metrics()

    dash_rev = float(kpis['total_revenue'])
    dash_orders = kpis['total_orders']
    dash_products = kpis['total_products']
    dash_customers = cust_metrics['total_customers']
    dash_stock = inv_kpis['on_hand_stock']

    print(f"  Revenue:   Source={raw_rev:,.2f} | Dashboard={dash_rev:,.2f} | Match={abs(raw_rev - dash_rev) < 0.01}")
    print(f"  Orders:    Source={raw_orders} | Dashboard={dash_orders} | Match={raw_orders == dash_orders}")
    print(f"  Products:  Source={raw_products} | Dashboard={dash_products} | Match={raw_products == dash_products}")
    print(f"  Customers: Source={raw_customers} | Dashboard={dash_customers} | Match={raw_customers == dash_customers}")
    print(f"  Stock:     Source={raw_stock} | Dashboard={dash_stock} | Match={raw_stock == dash_stock}")

    assert abs(raw_rev - dash_rev) < 0.01
    assert raw_orders == dash_orders
    assert raw_products == dash_products
    assert raw_customers == dash_customers
    assert raw_stock == dash_stock

    # 2. Testing Edge Cases: CANCELLED & REFUNDED Orders
    print("\n--- 2. Edge Case Testing: Cancelled & Refunded Orders ---")
    cust = User.objects.filter(role=User.Role.CUSTOMER).first()

    # Create Cancelled Order
    cancelled_order = Order.objects.create(
        user=cust,
        order_number=f"ORD-CANC-{int(timezone.now().timestamp())}",
        status=Order.Status.CANCELLED,
        subtotal=Decimal('99999.00'),
        total=Decimal('99999.00'),
    )
    # Create Refunded Order
    refunded_order = Order.objects.create(
        user=cust,
        order_number=f"ORD-REF-{int(timezone.now().timestamp())}",
        status=Order.Status.REFUNDED,
        subtotal=Decimal('88888.00'),
        total=Decimal('88888.00'),
    )

    kpis_after = RevenueAnalyticsService.get_kpis()
    assert float(kpis_after['total_revenue']) == dash_rev, "Leakage detected: Cancelled or Refunded order counted in revenue!"
    assert kpis_after['total_orders'] == dash_orders, "Leakage detected: Cancelled or Refunded order counted in order count!"
    print(f"  [+] Cancelled order ({cancelled_order.order_number}, INR 99,999) correctly ignored.")
    print(f"  [+] Refunded order ({refunded_order.order_number}, INR 88,888) correctly ignored.")

    # 3. Stock Reservation Testing
    print("\n--- 3. Stock Reservation Mechanics ---")
    ws = WarehouseStock.objects.first()
    if ws:
        orig_avail = ws.available_quantity
        orig_res = ws.reserved_quantity
        ws.reserved_quantity += 5
        ws.save()

        ws.refresh_from_db()
        assert ws.available_quantity == orig_avail - 5, "Available stock did not decrease when reserved increased!"
        print(f"  [+] Stock reservation test passed: reserved {orig_res} -> {ws.reserved_quantity}, available {orig_avail} -> {ws.available_quantity}.")
        # Revert
        ws.reserved_quantity = orig_res
        ws.save()

    # 4. Formal Automated Reconciliation Audit
    print("\n--- 4. Full Automated Reconciliation Audit ---")
    audit = DashboardDataConsistencyReconciler.run_reconciliation_audit()
    print(f"  Overall Consistency Score: {audit['overall_consistency_percentage']:.2f}% (Threshold: >= {audit['target_threshold']}%)")
    print(f"  Audit Status: {'PASSED' if audit['passed'] else 'FAILED'}")
    assert audit['passed'] is True
    assert audit['overall_consistency_percentage'] >= 99.0

    print("\n==================================================================")
    print("  DATA CONSISTENCY AUDIT COMPLETED SUCCESSFULLY")
    print("==================================================================")
    return 0


if __name__ == '__main__':
    sys.exit(main())

