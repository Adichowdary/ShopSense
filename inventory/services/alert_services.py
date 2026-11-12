"""
Low stock alert evaluation, deduplication, and lifecycle services.
"""

import logging
from typing import List, Optional
from django.db import transaction
from django.utils import timezone

from catalog.models import Product, Inventory
from inventory.models import Warehouse, WarehouseStock, LowStockAlert

logger = logging.getLogger(__name__)


class AlertService:
    """Manages low stock, out of stock, and projected stockout alerts."""

    @classmethod
    @transaction.atomic
    def evaluate_product_stock(
        cls,
        product: Product,
        warehouse: Optional[Warehouse] = None,
    ) -> List[LowStockAlert]:
        """
        Evaluate stock levels for a product and trigger/resolve alerts.
        """
        created_alerts = []

        # Determine stock levels and threshold
        threshold = 10
        if hasattr(product, 'inventory'):
            threshold = product.inventory.low_stock_threshold

        if warehouse:
            stock = WarehouseStock.objects.filter(warehouse=warehouse, product=product).first()
            available = stock.available_quantity if stock else 0
        else:
            available = sum(ws.available_quantity for ws in WarehouseStock.objects.filter(product=product))
            if available == 0 and hasattr(product, 'inventory'):
                available = product.inventory.available_quantity

        # Check existing active or acknowledged alerts
        active_alerts = LowStockAlert.objects.filter(
            product=product,
            warehouse=warehouse,
            status__in=[LowStockAlert.Status.ACTIVE, LowStockAlert.Status.ACKNOWLEDGED],
        )

        now = timezone.now()

        # Resolution check: If stock is healthy (> threshold), resolve any active/acknowledged alerts
        if available > threshold:
            for alert in active_alerts:
                alert.status = LowStockAlert.Status.RESOLVED
                alert.resolved_at = now
                alert.save(update_fields=['status', 'resolved_at', 'updated_at'])
                logger.info(f"Resolved alert {alert.pk} for {product.sku} (stock recovered to {available})")
            return created_alerts

        # Out of stock condition
        if available <= 0:
            target_type = LowStockAlert.AlertType.OUT_OF_STOCK
            severity = LowStockAlert.Severity.CRITICAL
        else:
            target_type = LowStockAlert.AlertType.LOW_STOCK
            severity = LowStockAlert.Severity.WARNING

        # Deduplication check
        existing = active_alerts.filter(alert_type=target_type).first()
        if existing:
            # Update observed stock
            if existing.observed_stock != available:
                existing.observed_stock = available
                existing.save(update_fields=['observed_stock', 'updated_at'])
            return created_alerts

        # Create new active alert
        alert = LowStockAlert.objects.create(
            product=product,
            warehouse=warehouse,
            alert_type=target_type,
            severity=severity,
            threshold=threshold,
            observed_stock=available,
            status=LowStockAlert.Status.ACTIVE,
        )
        created_alerts.append(alert)
        logger.info(f"Created {target_type} alert for {product.sku} (stock {available} <= threshold {threshold})")
        return created_alerts

    @classmethod
    def generate_all_alerts(cls) -> int:
        """Scan all active products and generate/resolve alerts."""
        count = 0
        products = Product.objects.filter(status__in=[Product.Status.ACTIVE, Product.Status.OUT_OF_STOCK])
        for product in products:
            alerts = cls.evaluate_product_stock(product)
            count += len(alerts)
        return count

    @classmethod
    def acknowledge_alert(cls, alert: LowStockAlert, user=None) -> LowStockAlert:
        """Acknowledge an active alert without resolving it."""
        if alert.status == LowStockAlert.Status.ACTIVE:
            alert.status = LowStockAlert.Status.ACKNOWLEDGED
            alert.acknowledged_by = user
            alert.acknowledged_at = timezone.now()
            alert.save(update_fields=['status', 'acknowledged_by', 'acknowledged_at', 'updated_at'])
            logger.info(f"Alert {alert.pk} acknowledged by {user}")
        return alert

    @classmethod
    def resolve_alert(cls, alert: LowStockAlert) -> LowStockAlert:
        """Manually mark an alert as resolved."""
        alert.status = LowStockAlert.Status.RESOLVED
        alert.resolved_at = timezone.now()
        alert.save(update_fields=['status', 'resolved_at', 'updated_at'])
        return alert
