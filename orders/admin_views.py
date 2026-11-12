"""
Admin Order Management views for ShopSense.
Provides order listing, search, status filtering, order detail with audit trail,
and controlled status transitions.
"""

import logging
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.utils.dateparse import parse_date
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, View

from vendors.models import AuditLog

from .models import Order, OrderItem, Payment
from .permissions import AdminRequiredMixin
from .services import (
    VALID_ORDER_TRANSITIONS,
    can_transition_order,
    update_order_status,
)

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Extract client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


class AdminOrderListView(AdminRequiredMixin, ListView):
    """
    Comprehensive administrative order listing with search, filtering,
    date-range filtering, and key financial/status metrics.
    """

    model = Order
    template_name = 'dashboard/orders/order_list.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            Order.objects.select_related('user')
            .prefetch_related('items__vendor', 'payments')
            .order_by('-created_at')
        )

        # Status filter
        status = self.request.GET.get('status', '').strip()
        if status and status in dict(Order.Status.choices):
            queryset = queryset.filter(status=status)

        # Search filter (order number, customer name, email, phone)
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(order_number__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(shipping_first_name__icontains=search)
                | Q(shipping_last_name__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__email__icontains=search)
            )

        # Date range filters
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
        all_orders = Order.objects.all()

        # Aggregated marketplace metrics
        metrics = all_orders.aggregate(
            total_count=Count('id'),
            total_revenue=Sum('total', filter=~Q(status=Order.Status.CANCELLED)),
            pending_count=Count('id', filter=Q(status=Order.Status.PENDING)),
            confirmed_count=Count('id', filter=Q(status=Order.Status.CONFIRMED)),
            processing_count=Count('id', filter=Q(status=Order.Status.PROCESSING)),
            shipped_count=Count('id', filter=Q(status=Order.Status.SHIPPED)),
            delivered_count=Count('id', filter=Q(status=Order.Status.DELIVERED)),
            cancelled_count=Count('id', filter=Q(status=Order.Status.CANCELLED)),
            refunded_count=Count('id', filter=Q(status=Order.Status.REFUNDED)),
        )

        context.update({
            'page_title': _('Order Management | ShopSense Admin'),
            'metrics': metrics,
            'status_choices': Order.Status.choices,
            'current_status': self.request.GET.get('status', '').strip(),
            'search_query': self.request.GET.get('search', '').strip(),
            'date_from': self.request.GET.get('date_from', '').strip(),
            'date_to': self.request.GET.get('date_to', '').strip(),
        })
        return context


class AdminOrderDetailView(AdminRequiredMixin, DetailView):
    """
    Detailed administrative view of an order with full line items,
    vendor breakdown, payment status, customer shipping info, and audit trail.
    """

    model = Order
    template_name = 'dashboard/orders/order_detail.html'
    context_object_name = 'order'
    slug_field = 'order_number'
    slug_url_kwarg = 'order_number'

    def get_queryset(self):
        return (
            Order.objects.select_related('user')
            .prefetch_related('items__product__images', 'items__vendor', 'payments')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object

        # Retrieve items and group vendor breakdown if multi-vendor
        items = list(order.items.select_related('product', 'vendor').all())
        payments = list(order.payments.all())

        # Audit logs for this order
        audit_logs = AuditLog.objects.filter(
            details__order_number=order.order_number
        ).select_related('user').order_by('-created_at')

        # Allowed transitions for this order
        allowed_transitions = VALID_ORDER_TRANSITIONS.get(order.status, [])

        context.update({
            'page_title': _('Order %(num)s | Admin') % {'num': order.order_number},
            'items': items,
            'payments': payments,
            'audit_logs': audit_logs,
            'allowed_transitions': allowed_transitions,
            'status_choices': Order.Status.choices,
        })
        return context


class AdminOrderStatusUpdateView(AdminRequiredMixin, View):
    """
    Process order status transitions with validation, automatic timestamping,
    and audit logging.
    """

    def post(self, request, order_number, *args, **kwargs):
        order = get_object_or_404(Order, order_number=order_number)
        new_status = request.POST.get('status', '').strip().upper()
        admin_notes = request.POST.get('admin_notes', '').strip()

        if new_status not in dict(Order.Status.choices):
            messages.error(request, _('Invalid order status selected.'))
            return redirect('dashboard:order_detail', order_number=order.order_number)

        try:
            update_order_status(
                order=order,
                new_status=new_status,
                performed_by=request.user,
                notes=admin_notes,
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
            messages.success(
                request,
                _('Order %(num)s status updated to %(status)s.') % {
                    'num': order.order_number,
                    'status': order.get_status_display(),
                },
            )
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, 'message') else str(e))
        except Exception:
            logger.exception(f'Failed to update status for order {order_number}')
            messages.error(request, _('An error occurred while updating the order status.'))

        return redirect('dashboard:order_detail', order_number=order.order_number)
