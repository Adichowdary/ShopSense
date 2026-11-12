"""
Core stock movement, ledger auditing, and inventory reconciliation services.
"""

import logging
from typing import Optional, Dict, Any, List
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from catalog.models import Product, Inventory
from inventory.models import Warehouse, WarehouseStock, StockMovement

logger = logging.getLogger(__name__)


class StockService:
    """Authoritative service for managing stock balances and the append-only movement ledger."""

    @staticmethod
    def get_or_create_default_warehouse() -> Warehouse:
        """Retrieve the default warehouse or create it if none exists."""
        warehouse = Warehouse.objects.filter(is_default=True).first()
        if not warehouse:
            warehouse = Warehouse.objects.filter(code='WH-DEFAULT').first()
        if not warehouse:
            warehouse = Warehouse.objects.create(
                name='Central Distribution Center',
                code='WH-DEFAULT',
                city='Bangalore',
                state='Karnataka',
                country='India',
                status=Warehouse.Status.ACTIVE,
                is_default=True,
            )
        return warehouse

    @classmethod
    @transaction.atomic
    def record_stock_movement(
        cls,
        product: Product,
        warehouse: Optional[Warehouse],
        quantity_change: int,
        movement_type: str,
        reason: str,
        order=None,
        transfer=None,
        notes: str = '',
        idempotency_key: Optional[str] = None,
        performed_by=None,
    ) -> StockMovement:
        """
        Record an atomic, append-only stock movement and update warehouse stock balances.
        Guarantees idempotency and prevents negative stock balances.
        """
        if warehouse is None:
            warehouse = cls.get_or_create_default_warehouse()

        # Idempotency verification
        if idempotency_key:
            existing_movement = StockMovement.objects.filter(idempotency_key=idempotency_key).first()
            if existing_movement:
                # Validate payload integrity
                if (
                    existing_movement.product_id != product.pk or
                    existing_movement.warehouse_id != warehouse.pk or
                    existing_movement.quantity_change != quantity_change or
                    existing_movement.movement_type != movement_type
                ):
                    raise ValidationError(
                        _("Conflicting payload submitted for existing idempotency key '%(key)s'.") % {
                            'key': idempotency_key
                        }
                    )
                logger.info(f"Duplicate stock movement ignored due to matching idempotency key {idempotency_key}")
                return existing_movement

        # Lock warehouse stock row for concurrent consistency
        stock, _created = WarehouseStock.objects.select_for_update().get_or_create(
            warehouse=warehouse,
            product=product,
            defaults={'quantity': 0, 'reserved_quantity': 0, 'damaged_quantity': 0},
        )

        new_quantity = stock.quantity + quantity_change
        if new_quantity < 0:
            raise ValidationError(
                _("Insufficient stock for %(sku)s at %(wh)s. Current: %(curr)s, Requested change: %(change)s.") % {
                    'sku': product.sku,
                    'wh': warehouse.code,
                    'curr': stock.quantity,
                    'change': quantity_change,
                }
            )

        stock.quantity = new_quantity
        stock.save(update_fields=['quantity', 'updated_at'])

        # Create immutable ledger record
        movement = StockMovement.objects.create(
            product=product,
            warehouse=warehouse,
            quantity_change=quantity_change,
            movement_type=movement_type,
            reason=reason,
            order=order,
            transfer=transfer,
            notes=notes,
            idempotency_key=idempotency_key,
            performed_by=performed_by,
            timestamp=timezone.now(),
        )

        # Synchronize aggregate catalog.Inventory to keep storefront/cart accurate
        cls.sync_catalog_inventory(product)

        logger.info(
            f"StockMovement {movement.pk} recorded: {product.sku} {quantity_change:+d} at {warehouse.code} ({movement_type})"
        )
        return movement

    @classmethod
    def sync_catalog_inventory(cls, product: Product) -> None:
        """
        Synchronize product's aggregate catalog.Inventory quantity with total warehouse available stock.
        """
        total_available = sum(
            ws.available_quantity for ws in WarehouseStock.objects.filter(product=product)
        )
        inv, _created = Inventory.objects.get_or_create(
            product=product,
            defaults={'quantity': total_available, 'low_stock_threshold': 10},
        )
        if inv.quantity != total_available:
            inv.quantity = total_available
            inv.save(update_fields=['quantity', 'updated_at'])

        # Update product status if out of stock
        if total_available <= 0 and product.status == Product.Status.ACTIVE:
            product.status = Product.Status.OUT_OF_STOCK
            product.save(update_fields=['status', 'updated_at'])
        elif total_available > 0 and product.status == Product.Status.OUT_OF_STOCK:
            product.status = Product.Status.ACTIVE
            product.save(update_fields=['status', 'updated_at'])

    @classmethod
    @transaction.atomic
    def backfill_warehouse_stock(cls, warehouse: Optional[Warehouse] = None) -> int:
        """
        Backfill WarehouseStock from existing catalog.Inventory for legacy products.
        Safe, transactional, and idempotent.
        """
        if warehouse is None:
            warehouse = cls.get_or_create_default_warehouse()

        count = 0
        for inv in Inventory.objects.select_related('product').all():
            stock, created = WarehouseStock.objects.get_or_create(
                warehouse=warehouse,
                product=inv.product,
                defaults={
                    'quantity': inv.quantity,
                    'reserved_quantity': inv.reserved_quantity,
                },
            )
            if created:
                count += 1
                # Seed initial movement if no movements exist
                backfill_key = f"backfill-{warehouse.code}-{inv.product_id}"
                if (
                    not StockMovement.objects.filter(idempotency_key=backfill_key).exists()
                    and not StockMovement.objects.filter(product=inv.product, warehouse=warehouse).exists()
                ):
                    StockMovement.objects.create(
                        product=inv.product,
                        warehouse=warehouse,
                        quantity_change=inv.quantity,
                        movement_type=StockMovement.MovementType.PURCHASE,
                        reason="Initial system backfill from catalog inventory",
                        idempotency_key=backfill_key,
                    )
        return count

    @classmethod
    def reconcile_inventory(cls, warehouse: Optional[Warehouse] = None) -> List[Dict[str, Any]]:
        """
        Audit and compare recorded WarehouseStock balances against the append-only StockMovement ledger sum.
        Reports any discrepancies without silent modification.
        """
        discrepancies = []
        stocks_qs = WarehouseStock.objects.select_related('product', 'warehouse')
        if warehouse:
            stocks_qs = stocks_qs.filter(warehouse=warehouse)

        for stock in stocks_qs:
            ledger_movements = StockMovement.objects.filter(
                product=stock.product,
                warehouse=stock.warehouse,
            )
            ledger_total = sum(m.quantity_change for m in ledger_movements)
            difference = stock.quantity - ledger_total

            if difference != 0:
                discrepancies.append({
                    'product_id': stock.product_id,
                    'product_sku': stock.product.sku,
                    'product_name': stock.product.name,
                    'warehouse_id': stock.warehouse_id,
                    'warehouse_code': stock.warehouse.code,
                    'recorded_stock': stock.quantity,
                    'ledger_sum': ledger_total,
                    'difference': difference,
                })

        return discrepancies
