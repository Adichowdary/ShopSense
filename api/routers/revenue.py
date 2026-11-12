"""
FastAPI Router: Advanced Revenue Analytics API.
Provides high-granularity revenue timeseries, growth indicators, AOV trends, and product performance.
"""

from typing import List
from fastapi import APIRouter, Depends, Query
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from api.auth import require_admin
from api.schemas import (
    RevenueTimeSeriesResponse,
    TimeSeriesPoint,
    RevenueGrowthResponse,
    SalesTrendsResponse,
    CategoryTrend,
    VendorProductPerformance,
)
from inventory.services.bi_services import RevenueAnalyticsService
from orders.models import Order

router = APIRouter(prefix="/revenue", tags=["Revenue Analytics"])


@router.get("/daily", response_model=RevenueTimeSeriesResponse)
def get_daily_revenue(
    days: int = Query(30, ge=7, le=180),
    user=Depends(require_admin),
):
    """Retrieve daily revenue timeseries and order volume."""
    pts = RevenueAnalyticsService.get_revenue_timeseries(days=days, grouping='day')
    return RevenueTimeSeriesResponse(
        period="day",
        count=len(pts),
        data=[TimeSeriesPoint(date=p['date'], revenue=p['revenue'], orders=p['orders']) for p in pts],
    )


@router.get("/monthly", response_model=RevenueTimeSeriesResponse)
def get_monthly_revenue(
    months_in_days: int = Query(365, ge=60, le=730),
    user=Depends(require_admin),
):
    """Retrieve monthly revenue timeseries and order volume."""
    pts = RevenueAnalyticsService.get_revenue_timeseries(days=months_in_days, grouping='month')
    return RevenueTimeSeriesResponse(
        period="month",
        count=len(pts),
        data=[TimeSeriesPoint(date=p['date'], revenue=p['revenue'], orders=p['orders']) for p in pts],
    )


@router.get("/growth", response_model=RevenueGrowthResponse)
def get_revenue_growth(user=Depends(require_admin)):
    """Retrieve period-over-period revenue and order volume growth percentages."""
    growth = RevenueAnalyticsService.get_growth_metrics()
    return RevenueGrowthResponse(
        current_period_revenue=float(growth['current_period_revenue']),
        previous_period_revenue=float(growth['previous_period_revenue']),
        revenue_growth_percent=growth['revenue_growth_percent'],
        current_period_orders=growth['current_period_orders'],
        previous_period_orders=growth['previous_period_orders'],
        orders_growth_percent=growth['orders_growth_percent'],
    )


@router.get("/trends", response_model=SalesTrendsResponse)
def get_sales_trends(user=Depends(require_admin)):
    """Retrieve category-level revenue and sales volume trends."""
    cat_trends = RevenueAnalyticsService.get_sales_trends_by_category()
    return SalesTrendsResponse(
        categories=[CategoryTrend(category=c['category'], units=c['units'], revenue=c['revenue']) for c in cat_trends]
    )


@router.get("/top-products", response_model=List[VendorProductPerformance])
def get_top_products(
    limit: int = Query(10, ge=1, le=50),
    user=Depends(require_admin),
):
    """Retrieve top-selling products by revenue and volume."""
    prods = RevenueAnalyticsService.get_top_selling_products(limit=limit)
    return [
        VendorProductPerformance(
            product_id=p['id'],
            name=p['name'],
            sku=p['sku'],
            price=p['price'],
            units_sold=p['units_sold'],
            revenue=p['revenue'],
            stock_quantity=p['stock'],
            status="ACTIVE",
        )
        for p in prods
    ]

