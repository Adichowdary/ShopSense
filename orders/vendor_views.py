"""
Vendor Order Management views for ShopSense.
Provides vendor order listing with strict database-level vendor isolation,
detail view showing only vendor-owned items, and per-item fulfillment actions.
"""

import logging
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils.dateparse import parse_date
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, View

from .models import Order, OrderItem
from .permissions import VendorRequiredMixin
from .services import (
    VALID_ITEM_TRANSITIONS,
    can_transition_item,
    update_vendor_order_item_status,
)

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Extract client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


class VendorOrderListView(VendorRequiredMixin, ListView):
    """
    Vendor orders view. Displays only orders that contain products
    from the authenticated vendor's catalog.
    """

    model = Order
    template_name = 'vendors/orders/order_list.html'
    context_object_name = 'orders'
    paginate_by = 15

    def get_queryset(self):
        vendor = self.request.user.vendor_profile

        # Only orders containing at least one item from this vendor
        queryset = (
            Order.objects.filter(items__vendor=vendor)
            .distinct()
            .select_related('user')
            .prefetch_related('items__product')
            .order_by('-created_at')
        )

        # Status filter based on item status or order status
        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(items__vendor=vendor, items__status=status).distinct()

        # Search filter (order number, customer name, shipping city)
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(order_number__icontains=search)
                | Q(shipping_first_name__icontains=search)
                | Q(shipping_last_name__icontains=search)
                | Q(shipping_city__icontains=search)
            ).distinct()

        # Date range filter
        date_from = self.request.GET.get('date_from', '').strip()
        if date_from:
            parsed_from = parse_date(date_from)
            if parsed_from:
                queryset = queryset.filter(created_at__date__gte=parsed_from)

        date_to = self.request.GET.get('date_to', '').strip()
        if date_to:
            parsed_to = parse_date(date_to)
            if parsed_to:
                queryset = queryset.filter(created_at__date__lte=parsed_to)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        vendor = self.request.user.vendor_profile

        # Vendor-specific item statistics
        vendor_items = OrderItem.objects.filter(vendor=vendor)
        metrics = vendor_items.aggregate(
            total_items=Count('id'),
            total_revenue=Sum('total_price', filter=~Q(status=OrderItem.Status.CANCELLED)),
            pending_items=Count('id', filter=Q(status=OrderItem.Status.PENDING)),
            confirmed_items=Count('id', filter=Q(status=OrderItem.Status.CONFIRMED)),
            processing_items=Count('id', filter=Q(status=OrderItem.Status.PROCESSING)),
            shipped_items=Count('id', filter=Q(status=OrderItem.Status.SHIPPED)),
            delivered_items=Count('id', filter=Q(status=OrderItem.Status.DELIVERED)),
            cancelled_items=Count('id', filter=Q(status=OrderItem.Status.CANCELLED)),
        )

        # Attach vendor-specific subtotal and items for each order in context
        orders_list = list(context['orders'])
        for order in orders_list:
            order.vendor_items_list = [i for i in order.items.all() if i.vendor_id == vendor.pk]
            order.vendor_items_count = sum(i.quantity for i in order.vendor_items_list)
            order.vendor_subtotal = sum(i.total_price for i in order.vendor_items_list)

        context.update({
            'page_title': _('My Orders & Fulfillment | Vendor Portal'),
            'metrics': metrics,
            'status_choices': OrderItem.Status.choices,
            'current_status': self.request.GET.get('status', '').strip(),
            'search_query': self.request.GET.get('search', '').strip(),
            'date_from': self.request.GET.get('date_from', '').strip(),
            'date_to': self.request.GET.get('date_to', '').strip(),
        })
        return context


class VendorOrderDetailView(VendorRequiredMixin, DetailView):
    """
    Vendor-specific order detail view.
    Enforces strict isolation: displays ONLY items belonging to this vendor
    and shipping details needed to fulfill the delivery.
    """

    model = Order
    template_name = 'vendors/orders/order_detail.html'
    context_object_name = 'order'
    slug_field = 'order_number'
    slug_url_kwarg = 'order_number'

    def get_queryset(self):
        vendor = self.request.user.vendor_profile
        # Only allow viewing orders containing at least one item from this vendor
        return Order.objects.filter(items__vendor=vendor).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        vendor = self.request.user.vendor_profile
        order = self.object

        # Strict isolation: filter items strictly belonging to this vendor
        vendor_items = list(
            order.items.filter(vendor=vendor)
            .select_related('product')
            .prefetch_related('product__images')
        )

        vendor_subtotal = sum(i.total_price for i in vendor_items)
        vendor_items_count = sum(i.quantity for i in vendor_items)

        # Map allowed transitions per item
        for item in vendor_items:
            item.allowed_transitions = VALID_ITEM_TRANSITIONS.get(item.status, [])

        context.update({
            'page_title': _('Order %(num)s Fulfillment | Vendor Portal') % {'num': order.order_number},
            'vendor_items': vendor_items,
            'vendor_subtotal': vendor_subtotal,
            'vendor_items_count': vendor_items_count,
            'status_choices': OrderItem.Status.choices,
        })
        return context


class VendorOrderItemFulfillView(VendorRequiredMixin, View):
    """
    Handle vendor updating fulfillment status for an individual item.
    Enforces vendor ownership server-side.
    """

    def post(self, request, order_number, item_pk, *args, **kwargs):
        vendor = request.user.vendor_profile
        order = get_object_or_404(Order, order_number=order_number)
        item = get_object_or_404(OrderItem, pk=item_pk, order=order, vendor=vendor)

        new_status = request.POST.get('status', '').strip().upper()
        if new_status not in dict(OrderItem.Status.choices):
            messages.error(request, _('Invalid status selected.'))
            return redirect('vendors:order_detail', order_number=order.order_number)

        try:
            update_vendor_order_item_status(
                item=item,
                new_status=new_status,
                vendor_profile=vendor,
                performed_by=request.user,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
            messages.success(
                request,
                _('Fulfillment status for "%(name)s" updated to %(status)s.') % {
                    'name': item.product_name,
                    'status': item.get_status_display(),
                },
            )
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, 'message') else str(e))
        except Exception:
            logger.exception(f'Vendor failed to fulfill item {item_pk}')
            messages.error(request, _('An error occurred while updating fulfillment status.'))

        return redirect('vendors:order_detail', order_number=order.order_number)
