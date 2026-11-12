"""
Views for ShopSense Inventory and Analytics Dashboard.
Provides full Admin Inventory Overview and strictly isolated Vendor Inventory views.
"""

import logging
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db.models import Sum, Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView, ListView, DetailView

from catalog.models import Product, Inventory
from inventory.models import (
    Warehouse,
    WarehouseStock,
    StockMovement,
    StockTransfer,
    StockTransferItem,
    LowStockAlert,
    ReplenishmentRequest,
    ForecastModel,
    ForecastPrediction,
    CustomerSegment,
    CustomerSegmentAssignment,
    RecommendationCandidate,
    RecommendationEvaluation,
)
from inventory.services import (
    StockService,
    TransferService,
    AlertService,
    ReplenishmentService,
    TurnoverService,
    ForecastService,
    CustomerAnalyticsService,
    RecommendationService,
)

logger = logging.getLogger(__name__)


class AdminRequiredMixin(UserPassesTestMixin):
    """Enforces admin access on views."""

    def test_func(self):
        return self.request.user.can_access_admin_dashboard()

    def handle_no_permission(self):
        messages.error(self.request, _('You do not have permission to access administrator inventory.'))
        return redirect('accounts:login')


class VendorRequiredMixin(UserPassesTestMixin):
    """Enforces vendor role on views."""

    def test_func(self):
        return self.request.user.is_vendor()

    def handle_no_permission(self):
        messages.error(self.request, _('You do not have permission to access vendor inventory.'))
        return redirect('accounts:login')


class AdminInventoryDashboardView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Comprehensive Admin Inventory & Analytics Dashboard."""

    template_name = 'dashboard/inventory/admin_overview.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Inventory & Analytics Overview')

        # Overall Stock Metrics
        total_products = Product.objects.filter(status=Product.Status.ACTIVE).count()
        total_stock = Inventory.objects.aggregate(total=Sum('quantity'))['total'] or 0

        # Calculate Total Inventory Valuation in INR (price * quantity)
        stock_value = sum(
            p.price * (p.inventory.quantity if hasattr(p, 'inventory') else 0)
            for p in Product.objects.select_related('inventory').filter(status=Product.Status.ACTIVE)
        )

        active_alerts_count = LowStockAlert.objects.filter(status=LowStockAlert.Status.ACTIVE).count()
        pending_replenishments_count = ReplenishmentRequest.objects.filter(
            status=ReplenishmentRequest.Status.SUGGESTED
        ).count()

        # Warehouses
        warehouses = Warehouse.objects.annotate(
            stock_count=Count('stocks'),
            total_units=Sum('stocks__quantity'),
        )

        # Recent alerts
        alerts = (
            LowStockAlert.objects.filter(status__in=[LowStockAlert.Status.ACTIVE, LowStockAlert.Status.ACKNOWLEDGED])
            .select_related('product', 'warehouse')
            .order_by('-created_at')[:10]
        )

        # Replenishment queue
        replenishments = (
            ReplenishmentRequest.objects.filter(status=ReplenishmentRequest.Status.SUGGESTED)
            .select_related('product', 'warehouse')
            .order_by('-created_at')[:10]
        )

        # Recent stock movements
        recent_movements = (
            StockMovement.objects.select_related('product', 'warehouse', 'performed_by')
            .order_by('-timestamp')[:15]
        )

        # Turnover Analytics
        turnover_summary = TurnoverService.get_turnover_metrics(days=30)
        turnover_table = TurnoverService.get_product_turnover_table(days=30)[:10]

        # Forecast Evaluation
        latest_forecast_model = ForecastModel.objects.filter(is_active=True).first()
        recent_predictions = (
            ForecastPrediction.objects.filter(prediction_date__gte=timezone.now().date())
            .select_related('product')
            .order_by('prediction_date')[:10]
        )

        # Customer Segments
        segments = CustomerSegment.objects.annotate(member_count=Count('assignments'))
        recent_segment_assignments = (
            CustomerSegmentAssignment.objects.select_related('user', 'segment')
            .order_by('-assigned_at')[:8]
        )

        # Recommendation Evaluation
        latest_rec_eval = RecommendationEvaluation.objects.order_by('-created_at').first()
        recommendation_candidates = (
            RecommendationCandidate.objects.filter(user__isnull=True)
            .select_related('product')
            .order_by('rank')[:8]
        )

        context.update({
            'total_products': total_products,
            'total_stock': total_stock,
            'stock_value': stock_value,
            'active_alerts_count': active_alerts_count,
            'pending_replenishments_count': pending_replenishments_count,
            'warehouses': warehouses,
            'alerts': alerts,
            'replenishments': replenishments,
            'recent_movements': recent_movements,
            'turnover_summary': turnover_summary,
            'turnover_table': turnover_table,
            'latest_forecast_model': latest_forecast_model,
            'recent_predictions': recent_predictions,
            'segments': segments,
            'recent_segment_assignments': recent_segment_assignments,
            'latest_rec_eval': latest_rec_eval,
            'recommendation_candidates': recommendation_candidates,
        })
        return context


class VendorInventoryDashboardView(LoginRequiredMixin, VendorRequiredMixin, TemplateView):
    """
    Vendor-specific isolated Inventory Dashboard.
    Enforces strict server-side filtering so vendor only sees their own products and metrics.
    """

    template_name = 'dashboard/inventory/vendor_overview.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Vendor Inventory & Stock Health')

        vendor = self.request.user.vendor_profile

        # Vendor's products only
        vendor_products = (
            Product.objects.filter(vendor=vendor)
            .select_related('inventory', 'category')
            .order_by('name')
        )

        total_vendor_stock = sum(
            p.inventory.quantity for p in vendor_products if hasattr(p, 'inventory')
        )
        total_vendor_value = sum(
            p.price * (p.inventory.quantity if hasattr(p, 'inventory') else 0)
            for p in vendor_products
        )

        # Vendor's alerts only
        alerts = (
            LowStockAlert.objects.filter(
                product__vendor=vendor,
                status__in=[LowStockAlert.Status.ACTIVE, LowStockAlert.Status.ACKNOWLEDGED],
            )
            .select_related('product')
            .order_by('-created_at')
        )

        # Vendor's replenishment suggestions only
        replenishments = (
            ReplenishmentRequest.objects.filter(
                product__vendor=vendor,
                status=ReplenishmentRequest.Status.SUGGESTED,
            )
            .select_related('product')
            .order_by('-created_at')
        )

        # Vendor's turnover metrics only
        turnover_summary = TurnoverService.get_turnover_metrics(vendor=vendor, days=30)
        turnover_table = TurnoverService.get_product_turnover_table(vendor=vendor, days=30)

        context.update({
            'vendor': vendor,
            'products': vendor_products,
            'total_stock': total_vendor_stock,
            'total_value': total_vendor_value,
            'alerts': alerts,
            'replenishments': replenishments,
            'turnover_summary': turnover_summary,
            'turnover_table': turnover_table,
        })
        return context


class AcknowledgeAlertActionView(LoginRequiredMixin, View):
    """Action to acknowledge a low stock alert."""

    def post(self, request, pk):
        alert = get_object_or_404(LowStockAlert, pk=pk)

        # Authorization: Admin or Vendor who owns the product
        if not (request.user.can_access_admin_dashboard() or (request.user.is_vendor() and alert.product.vendor == request.user.vendor_profile)):
            messages.error(request, _('Unauthorized to modify this alert.'))
            return redirect('inventory:admin_overview' if request.user.can_access_admin_dashboard() else 'inventory:vendor_overview')

        AlertService.acknowledge_alert(alert, user=request.user)
        messages.success(request, _('Alert for %(sku)s acknowledged successfully.') % {'sku': alert.product.sku})

        if request.user.can_access_admin_dashboard():
            return redirect('inventory:admin_overview')
        return redirect('inventory:vendor_overview')


class ApproveReplenishmentActionView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Admin action to approve a replenishment request."""

    def post(self, request, pk):
        replenishment = get_object_or_404(ReplenishmentRequest, pk=pk)
        try:
            approved_qty = int(request.POST.get('approved_quantity', replenishment.suggested_quantity))
        except (ValueError, TypeError):
            approved_qty = replenishment.suggested_quantity

        action = request.POST.get('action', 'approve')
        if action == 'approve':
            ReplenishmentService.approve_request(
                replenishment,
                approved_quantity=approved_qty,
                approved_by=request.user,
                notes=request.POST.get('notes', ''),
            )
            messages.success(request, _('Replenishment for %(sku)s approved (%(qty)s units).') % {
                'sku': replenishment.product.sku,
                'qty': approved_qty,
            })
        elif action == 'reject':
            ReplenishmentService.reject_request(
                replenishment,
                user=request.user,
                reason=request.POST.get('notes', ''),
            )
            messages.info(request, _('Replenishment for %(sku)s rejected.') % {'sku': replenishment.product.sku})

        return redirect('inventory:admin_overview')


class WarehouseTransferListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """List of all warehouse stock transfers."""

    model = StockTransfer
    template_name = 'dashboard/inventory/transfers.html'
    context_object_name = 'transfers'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Warehouse Stock Transfers')
        context['warehouses'] = Warehouse.objects.filter(status=Warehouse.Status.ACTIVE)
        context['products'] = Product.objects.filter(status=Product.Status.ACTIVE).order_by('name')
        return context


class WarehouseTransferCreateView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Create a new stock transfer between warehouses."""

    def post(self, request):
        source_id = request.POST.get('source_warehouse')
        dest_id = request.POST.get('destination_warehouse')
        product_id = request.POST.get('product')
        try:
            quantity = int(request.POST.get('quantity', 0))
        except (ValueError, TypeError):
            quantity = 0

        notes = request.POST.get('notes', '').strip()

        source = get_object_or_404(Warehouse, pk=source_id)
        dest = get_object_or_404(Warehouse, pk=dest_id)
        product = get_object_or_404(Product, pk=product_id)

        try:
            transfer = TransferService.create_transfer(
                source_warehouse=source,
                destination_warehouse=dest,
                items_data=[{'product': product, 'quantity': quantity}],
                requested_by=request.user,
                notes=notes,
            )
            messages.success(request, _('Transfer %(num)s requested successfully.') % {'num': transfer.transfer_number})
        except ValidationError as e:
            messages.error(request, str(e))

        return redirect('inventory:transfer_list')


class WarehouseTransferActionView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Execute status transition actions on stock transfers (approve, ship, receive, cancel)."""

    def post(self, request, pk):
        transfer = get_object_or_404(StockTransfer, pk=pk)
        action = request.POST.get('action')

        try:
            if action == 'approve':
                TransferService.approve_transfer(transfer, approved_by=request.user)
                messages.success(request, _('Transfer %(num)s approved.') % {'num': transfer.transfer_number})
            elif action == 'ship':
                TransferService.ship_transfer(transfer)
                messages.success(request, _('Transfer %(num)s shipped and marked in-transit.') % {'num': transfer.transfer_number})
            elif action == 'receive':
                TransferService.receive_transfer(transfer)
                messages.success(request, _('Transfer %(num)s received and stock credited.') % {'num': transfer.transfer_number})
            elif action == 'cancel':
                reason = request.POST.get('reason', '')
                TransferService.cancel_transfer(transfer, cancelled_by=request.user, reason=reason)
                messages.info(request, _('Transfer %(num)s cancelled.') % {'num': transfer.transfer_number})
            else:
                messages.error(request, _('Unrecognized transfer action.'))
        except ValidationError as e:
            messages.error(request, str(e))

        return redirect('inventory:transfer_list')
