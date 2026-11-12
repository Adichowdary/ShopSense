"""
Service layer for order status transitions, multi-vendor fulfillment, and audit logging.
"""

import logging

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from catalog.models import Product
from vendors.models import AuditLog

from .models import Order, OrderItem

logger = logging.getLogger(__name__)

# Valid transition state machines
VALID_ORDER_TRANSITIONS = {
    Order.Status.PENDING: [Order.Status.CONFIRMED, Order.Status.CANCELLED],
    Order.Status.CONFIRMED: [Order.Status.PROCESSING, Order.Status.CANCELLED],
    Order.Status.PROCESSING: [Order.Status.SHIPPED, Order.Status.CANCELLED],
    Order.Status.SHIPPED: [Order.Status.DELIVERED, Order.Status.CANCELLED],
    Order.Status.DELIVERED: [Order.Status.REFUNDED],
    Order.Status.CANCELLED: [Order.Status.REFUNDED],
    Order.Status.REFUNDED: [],
}

VALID_ITEM_TRANSITIONS = {
    OrderItem.Status.PENDING: [OrderItem.Status.CONFIRMED, OrderItem.Status.CANCELLED],
    OrderItem.Status.CONFIRMED: [OrderItem.Status.PROCESSING, OrderItem.Status.CANCELLED],
    OrderItem.Status.PROCESSING: [OrderItem.Status.SHIPPED, OrderItem.Status.CANCELLED],
    OrderItem.Status.SHIPPED: [OrderItem.Status.DELIVERED],
    OrderItem.Status.DELIVERED: [],
    OrderItem.Status.CANCELLED: [],
}


def can_transition_order(current_status, new_status):
    """Check if the transition between order statuses is allowed."""
    if current_status == new_status:
        return True
    allowed = VALID_ORDER_TRANSITIONS.get(current_status, [])
    return new_status in allowed


def can_transition_item(current_status, new_status):
    """Check if the transition between order item statuses is allowed."""
    if current_status == new_status:
        return True
    allowed = VALID_ITEM_TRANSITIONS.get(current_status, [])
    return new_status in allowed


def update_order_status(order, new_status, performed_by=None, notes='', ip_address=None, user_agent=''):
    """
    Safely transition an order's status, update appropriate timestamps,
    sync child items if applicable, and log the action in AuditLog.
    """
    old_status = order.status
    if old_status == new_status:
        if notes:
            now_str = timezone.now().strftime('%Y-%m-%d %H:%M')
            order.admin_notes = f"{order.admin_notes}\n[{now_str}] {notes}".strip()
            order.save(update_fields=['admin_notes', 'updated_at'])
        return order

    if not can_transition_order(old_status, new_status):
        raise ValidationError(
            _("Cannot change order status from %(old)s to %(new)s.") % {
                'old': old_status,
                'new': new_status
            }
        )

    now = timezone.now()
    order.status = new_status
    update_fields = ['status', 'updated_at']

    if notes:
        now_str = now.strftime('%Y-%m-%d %H:%M')
        order.admin_notes = f"{order.admin_notes}\n[{now_str}] {notes}".strip()
        update_fields.append('admin_notes')

    if new_status == Order.Status.CONFIRMED and not order.confirmed_at:
        order.confirmed_at = now
        update_fields.append('confirmed_at')
    elif new_status == Order.Status.SHIPPED and not order.shipped_at:
        order.shipped_at = now
        update_fields.append('shipped_at')
    elif new_status == Order.Status.DELIVERED and not order.delivered_at:
        order.delivered_at = now
        update_fields.append('delivered_at')

    order.save(update_fields=update_fields)

    # Sync child item statuses on major order transitions and restore stock safely
    if new_status == Order.Status.CANCELLED and old_status not in [Order.Status.CANCELLED, Order.Status.REFUNDED]:
        items_to_cancel = list(
            order.items.exclude(status__in=[OrderItem.Status.DELIVERED, OrderItem.Status.CANCELLED])
            .select_related('product__inventory')
        )
        for itm in items_to_cancel:
            if itm.product and hasattr(itm.product, 'inventory'):
                inv = itm.product.inventory
                inv.quantity += itm.quantity
                inv.save(update_fields=['quantity', 'updated_at'])
                if itm.product.status == Product.Status.OUT_OF_STOCK and inv.quantity > 0:
                    itm.product.status = Product.Status.ACTIVE
                    itm.product.save(update_fields=['status', 'updated_at'])
            itm.status = OrderItem.Status.CANCELLED
            itm.save(update_fields=['status'])
    elif new_status == Order.Status.SHIPPED:
        order.items.filter(status__in=[OrderItem.Status.PENDING, OrderItem.Status.CONFIRMED, OrderItem.Status.PROCESSING]).update(
            status=OrderItem.Status.SHIPPED,
            shipped_at=now
        )
    elif new_status == Order.Status.DELIVERED:
        order.items.filter(status__in=[OrderItem.Status.PENDING, OrderItem.Status.CONFIRMED, OrderItem.Status.PROCESSING, OrderItem.Status.SHIPPED]).update(
            status=OrderItem.Status.DELIVERED,
            delivered_at=now
        )

    # Record in AuditLog
    if new_status == Order.Status.CANCELLED:
        action = AuditLog.ActionType.ORDER_CANCELLED
    elif new_status == Order.Status.REFUNDED:
        action = AuditLog.ActionType.ORDER_REFUNDED
    else:
        action = AuditLog.ActionType.ORDER_STATUS_CHANGED

    AuditLog.objects.create(
        user=performed_by if (performed_by and performed_by.is_authenticated) else None,
        action=action,
        target_user=order.user,
        details={
            'order_id': order.pk,
            'order_number': order.order_number,
            'old_status': old_status,
            'new_status': new_status,
            'notes': notes,
        },
        ip_address=ip_address,
        user_agent=user_agent or '',
    )

    logger.info(
        f"Order {order.order_number} status changed from {old_status} to {new_status} by {performed_by}"
    )
    return order


def update_vendor_order_item_status(item, new_status, vendor_profile, performed_by=None, ip_address=None, user_agent=''):
    """
    Safely transition a vendor's item status, enforce vendor ownership,
    and propagate parent order status if all items reach milestones.
    """
    if item.vendor_id != vendor_profile.pk:
        raise ValidationError(_("Vendor does not own this order item."))

    old_status = item.status
    if old_status == new_status:
        return item

    if not can_transition_item(old_status, new_status):
        raise ValidationError(
            _("Cannot change item status from %(old)s to %(new)s.") % {
                'old': old_status,
                'new': new_status
            }
        )

    now = timezone.now()
    item.status = new_status
    update_fields = ['status']

    if new_status == OrderItem.Status.SHIPPED and not item.shipped_at:
        item.shipped_at = now
        update_fields.append('shipped_at')
    elif new_status == OrderItem.Status.DELIVERED and not item.delivered_at:
        item.delivered_at = now
        update_fields.append('delivered_at')
    elif new_status == OrderItem.Status.CANCELLED and old_status != OrderItem.Status.CANCELLED:
        if item.product and hasattr(item.product, 'inventory'):
            inv = item.product.inventory
            inv.quantity += item.quantity
            inv.save(update_fields=['quantity', 'updated_at'])
            if item.product.status == Product.Status.OUT_OF_STOCK and inv.quantity > 0:
                item.product.status = Product.Status.ACTIVE
                item.product.save(update_fields=['status', 'updated_at'])

    item.save(update_fields=update_fields)

    # Create audit entry
    AuditLog.objects.create(
        user=performed_by if (performed_by and performed_by.is_authenticated) else None,
        action=AuditLog.ActionType.ORDER_ITEM_FULFILLED,
        target_vendor=vendor_profile,
        details={
            'order_item_id': item.pk,
            'order_number': item.order.order_number,
            'product_name': item.product_name,
            'old_status': old_status,
            'new_status': new_status,
        },
        ip_address=ip_address,
        user_agent=user_agent or '',
    )

    # Sync parent order milestone if applicable
    order = item.order
    all_items = list(order.items.all())
    active_items = [i for i in all_items if i.status != OrderItem.Status.CANCELLED]

    if active_items:
        if all(i.status == OrderItem.Status.DELIVERED for i in active_items):
            if order.status != Order.Status.DELIVERED:
                order.status = Order.Status.DELIVERED
                order.delivered_at = now
                order.save(update_fields=['status', 'delivered_at', 'updated_at'])
        elif all(i.status in [OrderItem.Status.SHIPPED, OrderItem.Status.DELIVERED] for i in active_items):
            if order.status not in [Order.Status.SHIPPED, Order.Status.DELIVERED]:
                order.status = Order.Status.SHIPPED
                order.shipped_at = now
                order.save(update_fields=['status', 'shipped_at', 'updated_at'])
        elif any(i.status in [OrderItem.Status.PROCESSING, OrderItem.Status.SHIPPED] for i in active_items):
            if order.status == Order.Status.CONFIRMED:
                order.status = Order.Status.PROCESSING
                order.save(update_fields=['status', 'updated_at'])

    logger.info(
        f"OrderItem #{item.pk} for Order {order.order_number} changed from {old_status} to {new_status} by vendor {vendor_profile.business_name}"
    )
    return item
