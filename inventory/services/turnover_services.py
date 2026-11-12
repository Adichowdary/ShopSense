"""
Inventory turnover ratio, stock velocity, and movement analytics.
"""

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db.models import Sum, F
from django.utils import timezone

from catalog.models import Product, Inventory
from orders.models import Order, OrderItem
from inventory.models import StockMovement

logger = logging.getLogger(__name__)


class TurnoverService:
    """Computes inventory turnover ratio, days sales of inventory (DSI), and velocity classification."""

    @classmethod
    def get_turnover_metrics(
        cls,
        product: Optional[Product] = None,
        vendor=None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Calculate turnover metrics over the given window.
        Returns:
            - units_sold: total qualifying units sold
            - cogs: Cost of Goods Sold (INR)
            - revenue: total sales revenue (INR)
            - avg_inventory_units: average inventory units on hand
            - turnover_ratio: units_sold / avg_inventory_units
            - dsi: Days Sales of Inventory (days / turnover_ratio)
            - velocity_tier: FAST, MEDIUM, SLOW, DEAD
        """
        cutoff = timezone.now() - timedelta(days=days)
        qualifying_statuses = [
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
        ]

        items_qs = OrderItem.objects.filter(
            order__status__in=qualifying_statuses,
            order__created_at__gte=cutoff,
        )
        if product:
            items_qs = items_qs.filter(product=product)
        if vendor:
            items_qs = items_qs.filter(vendor=vendor)

        sales_agg = items_qs.aggregate(
            total_units=Sum('quantity'),
            total_revenue=Sum('total_price'),
        )
        units_sold = sales_agg['total_units'] or 0
        revenue = sales_agg['total_revenue'] or Decimal('0.00')

        # Current stock as proxy for average inventory
        inv_qs = Inventory.objects.all()
        if product:
            inv_qs = inv_qs.filter(product=product)
        if vendor:
            inv_qs = inv_qs.filter(product__vendor=vendor)

        current_stock = inv_qs.aggregate(total=Sum('quantity'))['total'] or 0
        avg_inventory = max(1, current_stock)

        turnover_ratio = round(float(units_sold) / float(avg_inventory), 2)
        if turnover_ratio > 0:
            dsi = round(float(days) / turnover_ratio, 1)
        else:
            dsi = None  # Infinite or undefined

        # Velocity classification
        if turnover_ratio >= 3.0:
            velocity_tier = 'FAST_MOVING'
        elif turnover_ratio >= 1.0:
            velocity_tier = 'MEDIUM_MOVING'
        elif turnover_ratio > 0:
            velocity_tier = 'SLOW_MOVING'
        else:
            velocity_tier = 'NON_MOVING'

        return {
            'period_days': days,
            'units_sold': units_sold,
            'revenue': revenue,
            'current_stock': current_stock,
            'turnover_ratio': turnover_ratio,
            'days_sales_of_inventory': dsi,
            'velocity_tier': velocity_tier,
        }

    @classmethod
    def get_product_turnover_table(cls, vendor=None, days: int = 30) -> List[Dict[str, Any]]:
        """Compute turnover metrics per product for table display."""
        products = Product.objects.filter(status=Product.Status.ACTIVE)
        if vendor:
            products = products.filter(vendor=vendor)

        results = []
        for p in products:
            metrics = cls.get_turnover_metrics(product=p, days=days)
            results.append({
                'product': p,
                'metrics': metrics,
            })
        # Sort by turnover ratio descending
        results.sort(key=lambda x: x['metrics']['turnover_ratio'], reverse=True)
        return results
