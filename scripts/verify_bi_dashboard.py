"""
Verification script for Section 3: Business Intelligence Dashboard.
Validates all 4 dashboard views, Plotly charts JSON, date filtering,
empty states, RBAC enforcement, and database derivations.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_test')
import django
django.setup()

from django.test.utils import setup_test_environment
setup_test_environment()

from django.test import Client
from django.urls import reverse
from accounts.models import User
from vendors.models import VendorProfile


def main():
    print("==================================================================")
    print("  SECTION 3: BI DASHBOARD VERIFICATION")
    print("==================================================================")

    # 1. Accounts setup
    admin, _ = User.objects.get_or_create(
        email='admin@shopsense.com',
        defaults={'role': User.Role.ADMIN, 'is_staff': True, 'is_superuser': True, 'is_active': True},
    )
    cust, _ = User.objects.get_or_create(
        email='customer@shopsense.com',
        defaults={'role': User.Role.CUSTOMER, 'is_active': True},
    )
    v_user, _ = User.objects.get_or_create(
        email='vendor_user@shopsense.com',
        defaults={'role': User.Role.VENDOR, 'is_active': True},
    )

    client = Client()

    # --- RBAC Verification ---
    print("\n--- 1. RBAC Restriction Check ---")
    bi_urls = [
        reverse('dashboard:bi_overview'),
        reverse('dashboard:bi_customers'),
        reverse('dashboard:bi_inventory'),
        reverse('dashboard:bi_recommendations'),
    ]

    for url in bi_urls:
        # Anonymous
        r_anon = client.get(url)
        assert r_anon.status_code == 302, f"Anonymous expected 302 for {url}, got {r_anon.status_code}"
        
        # Customer
        client.force_login(cust)
        r_cust = client.get(url)
        assert r_cust.status_code == 302, f"Customer expected 302 for {url}, got {r_cust.status_code}"

        # Vendor
        client.force_login(v_user)
        r_vend = client.get(url)
        assert r_vend.status_code == 302, f"Vendor expected 302 for {url}, got {r_vend.status_code}"

    print("[+] RBAC verified: Anonymous, Customer, and Vendor are strictly barred (302 to login).")

    # --- Admin Authorized Access & Content Derivation ---
    print("\n--- 2. Admin Authorized Access & Real Database Metric Derivation ---")
    client.force_login(admin)

    # View 1: Overview
    resp1 = client.get(reverse('dashboard:bi_overview'))
    assert resp1.status_code == 200, f"Expected 200 for Overview, got {resp1.status_code}"
    kpis = resp1.context['kpis']
    print(f"  [BI Overview] Revenue: INR {kpis['total_revenue']:,.2f} | Orders: {kpis['total_orders']} | SKUs: {kpis['total_products']}")
    assert 'revenue_chart_json' in resp1.context
    assert 'category_chart_json' in resp1.context
    assert b'plotly' in resp1.content.lower()

    # View 2: Customer Intel
    resp2 = client.get(reverse('dashboard:bi_customers'))
    assert resp2.status_code == 200, f"Expected 200 for Customer Intel, got {resp2.status_code}"
    cust_metrics = resp2.context['metrics']
    print(f"  [Customer Intel] Total Customers: {cust_metrics['total_customers']} | Repeat Rate: {cust_metrics['repeat_purchase_rate']}% | Avg Spend: INR {cust_metrics['average_customer_spend']:,.2f}")
    assert 'segments_chart_json' in resp2.context

    # View 3: Inventory Intel
    resp3 = client.get(reverse('dashboard:bi_inventory'))
    assert resp3.status_code == 200, f"Expected 200 for Inventory Intel, got {resp3.status_code}"
    inv_kpis = resp3.context['kpis']
    print(f"  [Inventory Intel] On-hand Stock: {inv_kpis['on_hand_stock']} | Low-stock Alerts: {inv_kpis['low_stock_count']} | Replenishment Suggestions: {len(inv_kpis['replenishment_suggestions'])}")
    assert 'stock_donut_json' in resp3.context
    assert 'movement_chart_json' in resp3.context

    # View 4: Recommendation Intel
    resp4 = client.get(reverse('dashboard:bi_recommendations'))
    assert resp4.status_code == 200, f"Expected 200 for Recommendation Intel, got {resp4.status_code}"
    rec_kpis = resp4.context['kpis']
    print(f"  [Recommendation Intel] Candidates: {rec_kpis['total_candidates']} | Precision@5: {rec_kpis['precision_at_k']}% | Coverage: {rec_kpis['coverage_percentage']}%")
    assert 'strategy_chart_json' in resp4.context

    # --- Date Filters & Empty States ---
    print("\n--- 3. Date Filtering & Empty State Safeguards ---")
    for period in ['7', '30', '90', '365']:
        r = client.get(f"{reverse('dashboard:bi_overview')}?period={period}")
        assert r.status_code == 200, f"Period {period} failed: {r.status_code}"
    print("  [+] Standard periods (7d, 30d, 90d, 365d) rendered successfully.")

    # Custom period with historical range where orders exist
    r_custom = client.get(f"{reverse('dashboard:bi_overview')}?period=custom&start_date=2026-01-01&end_date=2026-12-31")
    assert r_custom.status_code == 200
    print("  [+] Custom period (2026-01-01 to 2026-12-31) rendered successfully.")

    # Empty State: Range far in the future
    r_empty = client.get(f"{reverse('dashboard:bi_overview')}?period=custom&start_date=2035-01-01&end_date=2035-12-31")
    assert r_empty.status_code == 200
    empty_kpis = r_empty.context['kpis']
    assert empty_kpis['total_revenue'] == 0.0
    assert empty_kpis['total_orders'] == 0
    print("  [+] Empty state (future dates: 0 orders, INR 0.00) rendered cleanly without 500 error.")

    print("\n==================================================================")
    print("  ALL BI DASHBOARD VERIFICATIONS PASSED")
    print("==================================================================")
    return 0


if __name__ == '__main__':
    sys.exit(main())
