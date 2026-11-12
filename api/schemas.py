"""
Pydantic response and request schemas for ShopSense FastAPI Analytics.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# -------------------------------------------------------------------------
# Common Schemas
# -------------------------------------------------------------------------

class StatusMessage(BaseModel):
    status: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaginatedMeta(BaseModel):
    total: int
    limit: int
    offset: int


# -------------------------------------------------------------------------
# Vendor Analytics Schemas
# -------------------------------------------------------------------------

class VendorSummaryResponse(BaseModel):
    vendor_id: str
    business_name: str
    total_sales: float
    total_orders: int
    total_units_sold: int
    active_products_count: int
    average_order_value: float


class VendorProductPerformance(BaseModel):
    product_id: int
    name: str
    sku: str
    price: float
    units_sold: int
    revenue: float
    stock_quantity: int
    status: str


class VendorInventorySummary(BaseModel):
    total_stock_on_hand: int
    available_stock: int
    reserved_stock: int
    low_stock_items_count: int
    out_of_stock_items_count: int


# -------------------------------------------------------------------------
# Forecasting Schemas
# -------------------------------------------------------------------------

class DailyDemandPrediction(BaseModel):
    date: date
    predicted_demand: float
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    actual_demand: Optional[float] = None


class DemandForecastResponse(BaseModel):
    product_id: int
    sku: str
    product_name: str
    horizon_days: int
    accuracy_percentage: float
    predictions: List[DailyDemandPrediction]


class ForecastAccuracyResponse(BaseModel):
    model_version: str
    overall_accuracy: float
    wape: float
    evaluated_products_count: int
    cutoff_date: Optional[datetime] = None


class ReplenishmentSuggestion(BaseModel):
    product_id: int
    sku: str
    product_name: str
    warehouse: str
    current_stock: int
    reorder_point: int
    suggested_order_quantity: int


# -------------------------------------------------------------------------
# Customer Intelligence Schemas
# -------------------------------------------------------------------------

class CustomerSegmentSummary(BaseModel):
    code: str
    name: str
    customer_count: int
    total_spent: float
    average_frequency: float


class CustomerBehaviorResponse(BaseModel):
    total_customers: int
    average_spend: float
    purchase_frequency: float
    customer_lifetime_value: float
    repeat_purchase_rate: float


class CustomerSegmentListResponse(BaseModel):
    segments: List[CustomerSegmentSummary]


# -------------------------------------------------------------------------
# Recommendation Schemas
# -------------------------------------------------------------------------

class RecommendationItem(BaseModel):
    product_id: int
    sku: str
    name: str
    score: float
    rank: int
    reason: str
    price: float


class RecommendationResponse(BaseModel):
    strategy: str
    count: int
    recommendations: List[RecommendationItem]


class RecommendationMetricsResponse(BaseModel):
    precision_at_k: float
    coverage_percentage: float
    total_candidates: int
    k_value: int = 5


# -------------------------------------------------------------------------
# Advanced Revenue Analytics Schemas
# -------------------------------------------------------------------------

class TimeSeriesPoint(BaseModel):
    date: str
    revenue: float
    orders: int


class RevenueTimeSeriesResponse(BaseModel):
    period: str
    count: int
    data: List[TimeSeriesPoint]


class RevenueGrowthResponse(BaseModel):
    current_period_revenue: float
    previous_period_revenue: float
    revenue_growth_percent: float
    current_period_orders: int
    previous_period_orders: int
    orders_growth_percent: float


class CategoryTrend(BaseModel):
    category: str
    units: int
    revenue: float


class SalesTrendsResponse(BaseModel):
    categories: List[CategoryTrend]


# -------------------------------------------------------------------------
# Marketplace Benchmarking Schemas
# -------------------------------------------------------------------------

class VendorBenchmark(BaseModel):
    vendor_id: int
    name: str
    orders: int
    units: int
    sales: float


class MarketplaceBenchmarkingResponse(BaseModel):
    total_marketplace_revenue: float
    total_orders: int
    average_order_value: float
    top_vendors: List[VendorBenchmark]
    order_status_breakdown: List[Dict[str, Any]]

