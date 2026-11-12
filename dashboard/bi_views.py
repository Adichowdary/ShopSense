"""
Business Intelligence Views for ShopSense Dashboard.
Integrates Admin BI Overview, Customer Intelligence, Inventory Intelligence,
and Recommendation Analytics with interactive Plotly data visualizations.
"""

import json
import logging
from datetime import date, timedelta
from typing import Any, Dict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from dashboard.views import AdminRequiredMixin
from inventory.services.bi_services import (
    CustomerIntelligenceService,
    InventoryIntelligenceService,
    RecommendationIntelligenceService,
    RevenueAnalyticsService,
)
from inventory.services.export_services import (
    ExcelReportGenerator,
    PDFReportGenerator,
)

logger = logging.getLogger(__name__)


class AdminBusinessIntelligenceView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Authoritative Business Intelligence Admin Overview Dashboard."""

    template_name = 'dashboard/bi/admin_overview.html'

    def get_context_data(self, **kwargs) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Business Intelligence Overview')

        # Date range filter handling
        period = self.request.GET.get('period', '30')
        start_date = None
        end_date = None

        if period == 'custom':
            s_str = self.request.GET.get('start_date')
            e_str = self.request.GET.get('end_date')
            if s_str:
                start_date = parse_date(s_str)
            if e_str:
                end_date = parse_date(e_str)
            days = (end_date - start_date).days if (start_date and end_date) else 30
        else:
            try:
                days = int(period)
            except (ValueError, TypeError):
                days = 30
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=days)

        # Retrieve authoritative KPIs & growth metrics
        kpis = RevenueAnalyticsService.get_kpis(start_date=start_date, end_date=end_date)
        growth = RevenueAnalyticsService.get_growth_metrics()
        timeseries = RevenueAnalyticsService.get_revenue_timeseries(days=days, grouping='day' if days <= 60 else 'week')
        category_trends = RevenueAnalyticsService.get_sales_trends_by_category()
        top_products = RevenueAnalyticsService.get_top_selling_products(limit=10)
        marketplace = RevenueAnalyticsService.get_marketplace_performance()

        # Build Plotly Chart Configs
        revenue_trace = {
            'x': [p['date'] for p in timeseries],
            'y': [p['revenue'] for p in timeseries],
            'type': 'scatter',
            'mode': 'lines+markers',
            'name': _('Revenue (₹)'),
            'line': {'color': '#4f46e5', 'width': 3, 'shape': 'spline'},
            'fill': 'tozeroy',
            'fillcolor': 'rgba(79, 70, 229, 0.1)',
        }
        order_trace = {
            'x': [p['date'] for p in timeseries],
            'y': [p['orders'] for p in timeseries],
            'type': 'bar',
            'name': _('Orders'),
            'yaxis': 'y2',
            'marker': {'color': 'rgba(16, 185, 129, 0.6)'},
        }
        revenue_chart_data = {
            'data': [order_trace, revenue_trace],
            'layout': {
                'margin': {'t': 20, 'r': 40, 'l': 50, 'b': 40},
                'legend': {'orientation': 'h', 'y': 1.15},
                'xaxis': {'title': _('Date'), 'showgrid': False},
                'yaxis': {'title': _('Revenue (₹)'), 'showgrid': True, 'gridcolor': '#f1f5f9'},
                'yaxis2': {'title': _('Orders'), 'overlaying': 'y', 'side': 'right', 'showgrid': False},
                'paper_bgcolor': 'transparent',
                'plot_bgcolor': 'transparent',
            },
        }

        # Category Donut Chart
        cat_labels = [c['category'] for c in category_trends]
        cat_values = [c['revenue'] for c in category_trends]
        category_chart_data = {
            'data': [{
                'labels': cat_labels or [_('No Category')],
                'values': cat_values or [1],
                'type': 'pie',
                'hole': 0.5,
                'marker': {'colors': ['#4f46e5', '#10b981', '#f59e0b', '#3b82f6', '#ec4899', '#8b5cf6']},
                'textinfo': 'label+percent',
            }],
            'layout': {
                'margin': {'t': 10, 'r': 10, 'l': 10, 'b': 10},
                'showlegend': True,
                'legend': {'orientation': 'h', 'y': -0.1},
                'paper_bgcolor': 'transparent',
            },
        }

        context.update({
            'kpis': kpis,
            'growth': growth,
            'category_trends': category_trends,
            'top_products': top_products,
            'marketplace': marketplace,
            'period': period,
            'start_date': start_date,
            'end_date': end_date,
            'revenue_chart_json': json.dumps(revenue_chart_data, cls=DjangoJSONEncoder),
            'category_chart_json': json.dumps(category_chart_data, cls=DjangoJSONEncoder),
        })
        return context


class CustomerIntelligenceDashboardView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Customer Intelligence, RFM Segmentation, CLV, and Retention Analytics."""

    template_name = 'dashboard/bi/customer_intelligence.html'

    def get_context_data(self, **kwargs) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Customer Intelligence & Segmentation')

        metrics = CustomerIntelligenceService.get_customer_metrics()

        # Segment Distribution Bar Chart
        seg_names = [s['name'] for s in metrics['segments']]
        seg_counts = [s['count'] for s in metrics['segments']]
        seg_spend = [s['total_spent'] for s in metrics['segments']]

        segments_chart_data = {
            'data': [
                {
                    'x': seg_names,
                    'y': seg_counts,
                    'type': 'bar',
                    'name': _('Customers'),
                    'marker': {'color': '#4f46e5'},
                },
                {
                    'x': seg_names,
                    'y': seg_spend,
                    'type': 'scatter',
                    'mode': 'lines+markers',
                    'name': _('Total Spend (₹)'),
                    'yaxis': 'y2',
                    'line': {'color': '#10b981', 'width': 3},
                },
            ],
            'layout': {
                'margin': {'t': 20, 'r': 40, 'l': 50, 'b': 40},
                'legend': {'orientation': 'h', 'y': 1.15},
                'xaxis': {'showgrid': False},
                'yaxis': {'title': _('Customers Count'), 'showgrid': True, 'gridcolor': '#f1f5f9'},
                'yaxis2': {'title': _('Spend (₹)'), 'overlaying': 'y', 'side': 'right', 'showgrid': False},
                'paper_bgcolor': 'transparent',
                'plot_bgcolor': 'transparent',
            },
        }

        context.update({
            'metrics': metrics,
            'segments_chart_json': json.dumps(segments_chart_data, cls=DjangoJSONEncoder),
        })
        return context


class InventoryIntelligenceDashboardView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Inventory Intelligence, Stock Movements, Risk Indicators, and Replenishment."""

    template_name = 'dashboard/bi/inventory_intelligence.html'

    def get_context_data(self, **kwargs) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Inventory Intelligence & Turnover')

        kpis = InventoryIntelligenceService.get_inventory_kpis()
        movements = InventoryIntelligenceService.get_stock_movement_analytics(days=30)

        # Stock breakdown Donut
        stock_donut = {
            'data': [{
                'labels': [_('Available'), _('Reserved'), _('Damaged')],
                'values': [kpis['available_stock'], kpis['reserved_stock'], kpis['damaged_stock']],
                'type': 'pie',
                'hole': 0.5,
                'marker': {'colors': ['#10b981', '#f59e0b', '#ef4444']},
                'textinfo': 'label+percent',
            }],
            'layout': {
                'margin': {'t': 10, 'r': 10, 'l': 10, 'b': 10},
                'showlegend': True,
                'legend': {'orientation': 'h', 'y': -0.1},
                'paper_bgcolor': 'transparent',
            },
        }

        # Movements Bar
        move_types = [m['type'] for m in movements]
        move_counts = [m['count'] for m in movements]
        movement_chart = {
            'data': [{
                'x': move_types,
                'y': move_counts,
                'type': 'bar',
                'marker': {'color': '#3b82f6'},
            }],
            'layout': {
                'margin': {'t': 20, 'r': 20, 'l': 40, 'b': 40},
                'xaxis': {'title': _('Movement Type'), 'showgrid': False},
                'yaxis': {'title': _('Transactions'), 'showgrid': True, 'gridcolor': '#f1f5f9'},
                'paper_bgcolor': 'transparent',
                'plot_bgcolor': 'transparent',
            },
        }

        context.update({
            'kpis': kpis,
            'movements': movements,
            'stock_donut_json': json.dumps(stock_donut, cls=DjangoJSONEncoder),
            'movement_chart_json': json.dumps(movement_chart, cls=DjangoJSONEncoder),
        })
        return context


class RecommendationIntelligenceDashboardView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Recommendation Intelligence, Precision@K, Strategy Coverage, and Bestsellers."""

    template_name = 'dashboard/bi/recommendation_intelligence.html'

    def get_context_data(self, **kwargs) -> Dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Recommendation Intelligence & Performance')

        kpis = RecommendationIntelligenceService.get_recommendation_kpis()

        # Strategy Distribution Pie
        strat_labels = [s['recommendation_type'] for s in kpis['strategy_distribution']]
        strat_values = [s['count'] for s in kpis['strategy_distribution']]

        strategy_chart = {
            'data': [{
                'labels': strat_labels or [_('Popular')],
                'values': strat_values or [1],
                'type': 'pie',
                'hole': 0.45,
                'marker': {'colors': ['#4f46e5', '#10b981', '#f59e0b', '#ec4899']},
                'textinfo': 'label+percent',
            }],
            'layout': {
                'margin': {'t': 10, 'r': 10, 'l': 10, 'b': 10},
                'showlegend': True,
                'legend': {'orientation': 'h', 'y': -0.1},
                'paper_bgcolor': 'transparent',
            },
        }

        context.update({
            'kpis': kpis,
            'strategy_chart_json': json.dumps(strategy_chart, cls=DjangoJSONEncoder),
        })
        return context


class ExportReportView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Unified dispatcher for exporting analytical reports via query params:
    ?format=pdf|excel&report=revenue|customers|inventory|recommendations|sales|all
    """

    def get(self, request, *args, **kwargs):
        fmt = (request.GET.get('format') or 'pdf').lower().strip()
        report_type = request.GET.get('report') or request.GET.get('report_type') or 'revenue'
        start_date = parse_date(request.GET.get('start_date', ''))
        end_date = parse_date(request.GET.get('end_date', ''))

        if fmt == 'excel':
            excel_bytes = ExcelReportGenerator.generate_comprehensive_bi_workbook(
                start_date=start_date,
                end_date=end_date,
            )
            filename = f"shopsense_bi_analytics_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            response = HttpResponse(
                excel_bytes,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        else:
            pdf_bytes = PDFReportGenerator.generate_pdf_report(
                report_type=report_type,
                start_date=start_date,
                end_date=end_date,
            )
            filename = f"shopsense_{report_type}_report_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response


class ExportPDFReportView(LoginRequiredMixin, AdminRequiredMixin, View):
    """View to export professional ReportLab PDF reports."""

    def get(self, request, *args, **kwargs):
        report_type = request.GET.get('report_type', 'revenue')
        start_date = parse_date(request.GET.get('start_date', ''))
        end_date = parse_date(request.GET.get('end_date', ''))

        pdf_bytes = PDFReportGenerator.generate_pdf_report(
            report_type=report_type,
            start_date=start_date,
            end_date=end_date,
        )

        filename = f"shopsense_{report_type}_report_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class ExportExcelReportView(LoginRequiredMixin, AdminRequiredMixin, View):
    """View to export comprehensive multi-sheet openpyxl Excel reports."""

    def get(self, request, *args, **kwargs):
        start_date = parse_date(request.GET.get('start_date', ''))
        end_date = parse_date(request.GET.get('end_date', ''))

        excel_bytes = ExcelReportGenerator.generate_comprehensive_bi_workbook(
            start_date=start_date,
            end_date=end_date,
        )

        filename = f"shopsense_bi_analytics_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        response = HttpResponse(
            excel_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

