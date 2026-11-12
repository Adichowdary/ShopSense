"""
Dashboard Data Consistency Engine for ShopSense (Module 11).
Reconciles transactional source records (PostgreSQL / SQLite) against
analytical dashboard metrics surfaced in the Business Intelligence views.

Validates that:
1. Total revenue strictly reconciles with verified order totals (0 discrepancy).
2. Order counts match authoritative transactional logs.
3. Catalog active products match live inventory ledgers.
4. Customer counts match active registered accounts.
5. Vendor counts match approved vendor profile records.
6. Stock on-hand aligns with warehouse ledger sums.

Enforces target threshold: Consistency >= 99%.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone

from catalog.models import Product
from inventory.models import DataConsistencyLog, WarehouseStock
from inventory.services.bi_services import (
    CustomerIntelligenceService,
    InventoryIntelligenceService,
    RevenueAnalyticsService,
)
from orders.models import Order
from vendors.models import VendorProfile

User = get_user_model()
logger = logging.getLogger(__name__)


class DashboardDataConsistencyReconciler:
    """Automated auditor comparing source database facts against analytics services."""

    CONSISTENCY_PASS_THRESHOLD = 99.0

    @classmethod
    def run_reconciliation_audit(cls) -> Dict[str, Any]:
        """Perform comprehensive source-to-analytics audit and record to DataConsistencyLog."""
        audit_start = timezone.now()
        discrepancies: List[Dict[str, Any]] = []
        metrics_compared: Dict[str, Any] = {}

        # 1. Total Revenue Check
        source_rev_agg = (
            Order.objects.filter(status__in=RevenueAnalyticsService.QUALIFIED_STATUSES)
            .aggregate(total=Sum('total'))
        )
        source_rev = float(source_rev_agg['total'] or 0.0)
        kpis = RevenueAnalyticsService.get_kpis()
        analytics_rev = float(kpis['total_revenue'])
        rev_match = abs(source_rev - analytics_rev) < 0.01

        metrics_compared['total_revenue'] = {
            'source_value': round(source_rev, 2),
            'analytics_value': round(analytics_rev, 2),
            'matched': rev_match,
        }
        if not rev_match:
            discrepancies.append({
                'metric': 'total_revenue',
                'source': source_rev,
                'analytics': analytics_rev,
                'difference': abs(source_rev - analytics_rev),
            })

        # 2. Total Completed Orders Check
        source_orders = Order.objects.filter(status__in=RevenueAnalyticsService.QUALIFIED_STATUSES).count()
        analytics_orders = kpis['total_orders']
        orders_match = (source_orders == analytics_orders)

        metrics_compared['total_orders'] = {
            'source_value': source_orders,
            'analytics_value': analytics_orders,
            'matched': orders_match,
        }
        if not orders_match:
            discrepancies.append({
                'metric': 'total_orders',
                'source': source_orders,
                'analytics': analytics_orders,
                'difference': abs(source_orders - analytics_orders),
            })

        # 3. Active Products Count
        source_products = Product.objects.filter(status=Product.Status.ACTIVE).count()
        analytics_products = kpis['total_products']
        products_match = (source_products == analytics_products)

        metrics_compared['total_products'] = {
            'source_value': source_products,
            'analytics_value': analytics_products,
            'matched': products_match,
        }
        if not products_match:
            discrepancies.append({
                'metric': 'total_products',
                'source': source_products,
                'analytics': analytics_products,
                'difference': abs(source_products - analytics_products),
            })

        # 4. Total Registered Customers
        source_customers = User.objects.filter(role=User.Role.CUSTOMER, is_active=True).count()
        analytics_customers = kpis['total_customers']
        customers_match = (source_customers == analytics_customers)

        metrics_compared['total_customers'] = {
            'source_value': source_customers,
            'analytics_value': analytics_customers,
            'matched': customers_match,
        }
        if not customers_match:
            discrepancies.append({
                'metric': 'total_customers',
                'source': source_customers,
                'analytics': analytics_customers,
                'difference': abs(source_customers - analytics_customers),
            })

        # 5. Active Vendors Count
        source_vendors = VendorProfile.objects.filter(is_active=True).count()
        analytics_vendors = kpis['active_vendors']
        vendors_match = (source_vendors == analytics_vendors)

        metrics_compared['active_vendors'] = {
            'source_value': source_vendors,
            'analytics_value': analytics_vendors,
            'matched': vendors_match,
        }
        if not vendors_match:
            discrepancies.append({
                'metric': 'active_vendors',
                'source': source_vendors,
                'analytics': analytics_vendors,
                'difference': abs(source_vendors - analytics_vendors),
            })

        # 6. Warehouse On-Hand Stock Ledger Consistency
        inv_kpis = InventoryIntelligenceService.get_inventory_kpis()
        source_stock_agg = WarehouseStock.objects.aggregate(total=Sum('quantity'))
        source_stock = int(source_stock_agg['total'] or 0)
        analytics_stock = inv_kpis['on_hand_stock']
        stock_match = (source_stock == analytics_stock)

        metrics_compared['on_hand_stock'] = {
            'source_value': source_stock,
            'analytics_value': analytics_stock,
            'matched': stock_match,
        }
        if not stock_match:
            discrepancies.append({
                'metric': 'on_hand_stock',
                'source': source_stock,
                'analytics': analytics_stock,
                'difference': abs(source_stock - analytics_stock),
            })

        # Calculate Overall Consistency Score
        total_checks = len(metrics_compared)
        matched_checks = sum(1 for m in metrics_compared.values() if m['matched'])
        consistency_pct = round((matched_checks / max(1, total_checks)) * 100.0, 2)
        passed = consistency_pct >= cls.CONSISTENCY_PASS_THRESHOLD

        # Persist audit record in DataConsistencyLog
        log_entry = DataConsistencyLog.objects.create(
            run_date=audit_start,
            overall_consistency_percentage=consistency_pct,
            passed=passed,
            metrics_compared=metrics_compared,
            discrepancies=discrepancies,
            notes=f"Audited {total_checks} core operational metrics. Matched: {matched_checks}/{total_checks}",
        )

        logger.info(
            "Dashboard Data Consistency Audit finished: %.2f%% (Passed: %s) with %d discrepancies",
            consistency_pct,
            passed,
            len(discrepancies),
        )

        return {
            'log_id': log_entry.id,
            'run_date': audit_start.isoformat(),
            'overall_consistency_percentage': consistency_pct,
            'passed': passed,
            'metrics_compared': metrics_compared,
            'discrepancies': discrepancies,
            'target_threshold': cls.CONSISTENCY_PASS_THRESHOLD,
        }

