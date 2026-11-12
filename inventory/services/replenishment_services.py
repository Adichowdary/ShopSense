"""
Replenishment recommendation and approval workflow service.
Formula: Reorder Point (ROP) = (Average Daily Demand * Lead Time) + Safety Stock.
Suggested Quantity = max(0, ROP - (Available Stock + On-Order Stock)).
"""

import logging
from datetime import timedelta
from typing import List, Optional
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from catalog.models import Product
from orders.models import Order, OrderItem
from inventory.models import Warehouse, WarehouseStock, ReplenishmentRequest

logger = logging.getLogger(__name__)


class ReplenishmentService:
    """Calculates replenishment needs and provides approval workflows."""

    @classmethod
    def calculate_average_daily_demand(cls, product: Product, days: int = 30) -> float:
        """
        Calculate average daily units sold over the qualifying historical period.
        Excludes cancelled and refunded orders.
        """
        cutoff = timezone.now() - timedelta(days=days)
        qualifying_statuses = [
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
        ]
        total_units = OrderItem.objects.filter(
            product=product,
            order__status__in=qualifying_statuses,
            order__created_at__gte=cutoff,
        ).aggregate(total=Sum('quantity'))['total'] or 0

        return float(total_units) / max(1, days)

    @classmethod
    def evaluate_replenishment(
        cls,
        product: Product,
        warehouse: Optional[Warehouse] = None,
        lead_time_days: int = 7,
        safety_stock: int = 10,
    ) -> Optional[ReplenishmentRequest]:
        """
        Evaluate whether a product needs replenishment and generate a SUGGESTED request.
        Does NOT automatically execute supplier purchases.
        """
        # Determine available stock
        if warehouse:
            stock = WarehouseStock.objects.filter(warehouse=warehouse, product=product).first()
            available = stock.available_quantity if stock else 0
        else:
            available = sum(ws.available_quantity for ws in WarehouseStock.objects.filter(product=product))
            if available == 0 and hasattr(product, 'inventory'):
                available = product.inventory.available_quantity

        # Outstanding approved / ordered requests
        outstanding_ordered = ReplenishmentRequest.objects.filter(
            product=product,
            warehouse=warehouse,
            status__in=[ReplenishmentRequest.Status.APPROVED, ReplenishmentRequest.Status.ORDERED],
        ).aggregate(total=Sum('approved_quantity'))['total'] or 0

        avg_daily_demand = cls.calculate_average_daily_demand(product, days=30)
        reorder_point = int(round((avg_daily_demand * lead_time_days) + safety_stock))

        effective_stock = available + outstanding_ordered

        if effective_stock <= reorder_point:
            # Need to suggest replenishment
            suggested_qty = max(1, reorder_point - effective_stock + safety_stock)

            # Avoid spamming duplicate open suggestions
            existing_suggestion = ReplenishmentRequest.objects.filter(
                product=product,
                warehouse=warehouse,
                status=ReplenishmentRequest.Status.SUGGESTED,
            ).first()

            if existing_suggestion:
                existing_suggestion.suggested_quantity = suggested_qty
                existing_suggestion.observed_stock = available
                existing_suggestion.reorder_point = reorder_point
                existing_suggestion.safety_stock = safety_stock
                existing_suggestion.lead_time_days = lead_time_days
                existing_suggestion.save()
                return existing_suggestion

            req = ReplenishmentRequest.objects.create(
                product=product,
                warehouse=warehouse,
                suggested_quantity=suggested_qty,
                observed_stock=available,
                safety_stock=safety_stock,
                lead_time_days=lead_time_days,
                reorder_point=reorder_point,
                status=ReplenishmentRequest.Status.SUGGESTED,
            )
            logger.info(f"Generated replenishment suggestion for {product.sku}: suggested {suggested_qty} units.")
            return req

        return None

    @classmethod
    def generate_all_suggestions(cls, lead_time_days: int = 7, safety_stock: int = 10) -> int:
        """Scan active products and generate replenishment suggestions."""
        count = 0
        for product in Product.objects.filter(status__in=[Product.Status.ACTIVE, Product.Status.OUT_OF_STOCK]):
            req = cls.evaluate_replenishment(
                product=product,
                lead_time_days=lead_time_days,
                safety_stock=safety_stock,
            )
            if req:
                count += 1
        return count

    @classmethod
    def approve_request(
        cls,
        request_obj: ReplenishmentRequest,
        approved_quantity: int,
        approved_by=None,
        notes: str = '',
    ) -> ReplenishmentRequest:
        """
        Authorize and approve a replenishment request.
        """
        if approved_quantity <= 0:
            raise ValidationError(_("Approved quantity must be strictly positive."))

        request_obj.approved_quantity = approved_quantity
        request_obj.status = ReplenishmentRequest.Status.APPROVED
        request_obj.approved_by = approved_by
        if notes:
            request_obj.notes = f"{request_obj.notes}\nApproval notes: {notes}".strip()
        request_obj.save(update_fields=['approved_quantity', 'status', 'approved_by', 'notes', 'updated_at'])
        logger.info(f"Replenishment {request_obj.pk} approved for {approved_quantity} units by {approved_by}")
        return request_obj

    @classmethod
    def reject_request(cls, request_obj: ReplenishmentRequest, user=None, reason: str = '') -> ReplenishmentRequest:
        """Reject a suggested replenishment request."""
        request_obj.status = ReplenishmentRequest.Status.REJECTED
        if reason:
            request_obj.notes = f"{request_obj.notes}\nRejection reason: {reason}".strip()
        request_obj.save(update_fields=['status', 'notes', 'updated_at'])
        return request_obj
