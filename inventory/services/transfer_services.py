"""
Warehouse stock transfer lifecycle management service.
Handles REQUESTED -> APPROVED -> IN_TRANSIT -> RECEIVED and CANCELLED states.
"""

import logging
from typing import List, Dict, Any, Optional
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from catalog.models import Product
from inventory.models import Warehouse, StockTransfer, StockTransferItem, StockMovement
from .stock_services import StockService

logger = logging.getLogger(__name__)


class TransferService:
    """Manages multi-warehouse transfer workflows and inventory movements."""

    @classmethod
    @transaction.atomic
    def create_transfer(
        cls,
        source_warehouse: Warehouse,
        destination_warehouse: Warehouse,
        items_data: List[Dict[str, Any]],
        requested_by=None,
        notes: str = '',
    ) -> StockTransfer:
        """
        Initiate a transfer request.
        items_data format: [{'product': Product or int, 'quantity': int}]
        """
        if source_warehouse.pk == destination_warehouse.pk:
            raise ValidationError(_("Source and destination warehouses cannot be the same."))

        if not items_data:
            raise ValidationError(_("Transfer must contain at least one item."))

        transfer_number = f"TRF-{timezone.now():%Y%m%d%H%M%S}-{source_warehouse.code}"
        transfer = StockTransfer.objects.create(
            transfer_number=transfer_number,
            source_warehouse=source_warehouse,
            destination_warehouse=destination_warehouse,
            status=StockTransfer.TransferStatus.REQUESTED,
            requested_by=requested_by,
            notes=notes,
        )

        for item in items_data:
            product = item['product']
            if isinstance(product, int):
                product = Product.objects.get(pk=product)
            qty = int(item['quantity'])
            if qty <= 0:
                raise ValidationError(_("Requested transfer quantity must be strictly positive."))

            StockTransferItem.objects.create(
                transfer=transfer,
                product=product,
                requested_quantity=qty,
            )

        logger.info(f"Created stock transfer {transfer.transfer_number} with {len(items_data)} items")
        return transfer

    @classmethod
    def approve_transfer(cls, transfer: StockTransfer, approved_by=None) -> StockTransfer:
        """Approve a requested transfer."""
        if transfer.status != StockTransfer.TransferStatus.REQUESTED:
            raise ValidationError(
                _("Only transfers in REQUESTED status can be approved. Current status: %(status)s") % {
                    'status': transfer.status
                }
            )

        transfer.status = StockTransfer.TransferStatus.APPROVED
        transfer.approved_by = approved_by
        transfer.save(update_fields=['status', 'approved_by', 'updated_at'])
        logger.info(f"Transfer {transfer.transfer_number} approved by {approved_by}")
        return transfer

    @classmethod
    @transaction.atomic
    def ship_transfer(
        cls,
        transfer: StockTransfer,
        shipped_items: Optional[Dict[int, int]] = None,
    ) -> StockTransfer:
        """
        Transition transfer from APPROVED to IN_TRANSIT.
        Deducts stock from source warehouse and records TRANSFER_OUT movements.
        shipped_items format: {product_id: shipped_qty} or None to ship all requested.
        """
        if transfer.status != StockTransfer.TransferStatus.APPROVED:
            raise ValidationError(
                _("Only APPROVED transfers can be shipped. Current status: %(status)s") % {
                    'status': transfer.status
                }
            )

        items = list(transfer.items.select_related('product'))
        for item in items:
            product_id = item.product_id
            ship_qty = shipped_items.get(product_id, item.requested_quantity) if shipped_items else item.requested_quantity

            if ship_qty <= 0:
                raise ValidationError(_("Shipped quantity must be greater than zero."))
            if ship_qty > item.requested_quantity:
                raise ValidationError(
                    _("Cannot over-ship product %(sku)s. Requested: %(req)s, Attempted: %(ship)s.") % {
                        'sku': item.product.sku,
                        'req': item.requested_quantity,
                        'ship': ship_qty,
                    }
                )

            item.shipped_quantity = ship_qty
            item.save(update_fields=['shipped_quantity'])

            # Deduct stock from source warehouse
            StockService.record_stock_movement(
                product=item.product,
                warehouse=transfer.source_warehouse,
                quantity_change=-ship_qty,
                movement_type=StockMovement.MovementType.TRANSFER_OUT,
                reason=f"Transfer {transfer.transfer_number} shipped to {transfer.destination_warehouse.code}",
                transfer=transfer,
                idempotency_key=f"ship-{transfer.transfer_number}-{item.product_id}",
            )

        transfer.status = StockTransfer.TransferStatus.IN_TRANSIT
        transfer.shipped_at = timezone.now()
        transfer.save(update_fields=['status', 'shipped_at', 'updated_at'])
        logger.info(f"Transfer {transfer.transfer_number} shipped and in transit.")
        return transfer

    @classmethod
    @transaction.atomic
    def receive_transfer(
        cls,
        transfer: StockTransfer,
        received_items: Optional[Dict[int, int]] = None,
    ) -> StockTransfer:
        """
        Transition transfer from IN_TRANSIT to RECEIVED.
        Credits stock to destination warehouse and records TRANSFER_IN movements.
        """
        if transfer.status != StockTransfer.TransferStatus.IN_TRANSIT:
            raise ValidationError(
                _("Only IN_TRANSIT transfers can be received. Current status: %(status)s") % {
                    'status': transfer.status
                }
            )

        items = list(transfer.items.select_related('product'))
        for item in items:
            product_id = item.product_id
            recv_qty = received_items.get(product_id, item.shipped_quantity) if received_items else item.shipped_quantity

            if recv_qty < 0:
                raise ValidationError(_("Received quantity cannot be negative."))
            if recv_qty > item.shipped_quantity:
                raise ValidationError(
                    _("Cannot over-receive product %(sku)s. Shipped: %(ship)s, Attempted: %(recv)s.") % {
                        'sku': item.product.sku,
                        'ship': item.shipped_quantity,
                        'recv': recv_qty,
                    }
                )

            item.received_quantity = recv_qty
            item.save(update_fields=['received_quantity'])

            if recv_qty > 0:
                # Credit stock to destination warehouse
                StockService.record_stock_movement(
                    product=item.product,
                    warehouse=transfer.destination_warehouse,
                    quantity_change=recv_qty,
                    movement_type=StockMovement.MovementType.TRANSFER_IN,
                    reason=f"Transfer {transfer.transfer_number} received from {transfer.source_warehouse.code}",
                    transfer=transfer,
                    idempotency_key=f"recv-{transfer.transfer_number}-{item.product_id}",
                )

        transfer.status = StockTransfer.TransferStatus.RECEIVED
        transfer.received_at = timezone.now()
        transfer.save(update_fields=['status', 'received_at', 'updated_at'])
        logger.info(f"Transfer {transfer.transfer_number} received at {transfer.destination_warehouse.code}.")
        return transfer

    @classmethod
    def cancel_transfer(cls, transfer: StockTransfer, cancelled_by=None, reason: str = '') -> StockTransfer:
        """
        Cancel a transfer before it is shipped.
        Transfers already IN_TRANSIT or RECEIVED cannot be cancelled.
        """
        if transfer.status not in [StockTransfer.TransferStatus.REQUESTED, StockTransfer.TransferStatus.APPROVED]:
            raise ValidationError(
                _("Cannot cancel transfer in %(status)s status. Transfers in transit or received cannot be cancelled directly.") % {
                    'status': transfer.status
                }
            )

        transfer.status = StockTransfer.TransferStatus.CANCELLED
        transfer.cancelled_at = timezone.now()
        if reason:
            transfer.notes = f"{transfer.notes}\nCancellation reason: {reason}".strip()
        transfer.save(update_fields=['status', 'cancelled_at', 'notes', 'updated_at'])
        logger.info(f"Transfer {transfer.transfer_number} cancelled by {cancelled_by}")
        return transfer
