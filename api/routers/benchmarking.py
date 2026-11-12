"""
FastAPI Router: Marketplace Benchmarking API.
Provides vendor comparisons, category benchmarking, and platform-wide KPI indicators.
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Query
from django.db.models import Count, Sum

from api.auth import require_admin
from api.schemas import (
    MarketplaceBenchmarkingResponse,
    VendorBenchmark,
)
from inventory.services.bi_services import RevenueAnalyticsService
from orders.models import Order

router = APIRouter(prefix="/benchmarking", tags=["Marketplace Benchmarking"])


@router.get("/marketplace", response_model=MarketplaceBenchmarkingResponse)
def get_marketplace_benchmarks(user=Depends(require_admin)):
    """Retrieve platform-wide marketplace benchmarking metrics and top vendor comparisons."""
    kpis = RevenueAnalyticsService.get_kpis()
    perf = RevenueAnalyticsService.get_marketplace_performance()

    top_vendors = [
        VendorBenchmark(
            vendor_id=v['vendor_id'],
            name=v['name'],
            orders=v['orders'],
            units=v['units'],
            sales=v['sales'],
        )
        for v in perf['top_vendors']
    ]

    return MarketplaceBenchmarkingResponse(
        total_marketplace_revenue=float(kpis['total_revenue']),
        total_orders=kpis['total_orders'],
        average_order_value=float(kpis['average_order_value']),
        top_vendors=top_vendors,
        order_status_breakdown=perf['order_status_distribution'],
    )


@router.get("/vendors", response_model=List[VendorBenchmark])
def get_vendor_comparisons(user=Depends(require_admin)):
    """Retrieve ranked vendor performance benchmarks."""
    perf = RevenueAnalyticsService.get_marketplace_performance()
    return [
        VendorBenchmark(
            vendor_id=v['vendor_id'],
            name=v['name'],
            orders=v['orders'],
            units=v['units'],
            sales=v['sales'],
        )
        for v in perf['top_vendors']
    ]

