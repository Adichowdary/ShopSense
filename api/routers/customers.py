"""
FastAPI Router: Customer Intelligence API.
Provides customer segmentation, RFM features, CLV, and retention metrics.
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Query
from django.db.models import Count, Sum, Avg

from api.auth import require_admin
from api.schemas import (
    CustomerSegmentSummary,
    CustomerSegmentListResponse,
    CustomerBehaviorResponse,
)
from inventory.models import CustomerSegment, CustomerSegmentAssignment
from inventory.services.bi_services import CustomerIntelligenceService

router = APIRouter(prefix="/customers", tags=["Customer Intelligence"])


@router.get("/segments", response_model=CustomerSegmentListResponse)
def get_customer_segments(user=Depends(require_admin)):
    """Retrieve all RFM customer segments and member distribution."""
    metrics = CustomerIntelligenceService.get_customer_metrics()
    segments = [
        CustomerSegmentSummary(
            code=s['code'],
            name=s['name'],
            customer_count=s['count'],
            total_spent=s['total_spent'],
            average_frequency=s['avg_frequency'],
        )
        for s in metrics['segments']
    ]
    return CustomerSegmentListResponse(segments=segments)


@router.get("/behavior", response_model=CustomerBehaviorResponse)
def get_customer_behavior(user=Depends(require_admin)):
    """Retrieve macro customer purchase behavior, frequency, repeat rate, and CLV."""
    metrics = CustomerIntelligenceService.get_customer_metrics()
    total_customers = sum(s['count'] for s in metrics['segments']) or 1

    return CustomerBehaviorResponse(
        total_customers=total_customers,
        average_spend=metrics['average_customer_spend'],
        purchase_frequency=metrics['purchase_frequency'],
        customer_lifetime_value=metrics['customer_lifetime_value'],
        repeat_purchase_rate=metrics['repeat_purchase_rate'],
    )


@router.get("/high-spenders", response_model=List[Dict[str, Any]])
def get_high_spenders(
    limit: int = Query(10, ge=1, le=50),
    user=Depends(require_admin),
):
    """Retrieve top customer spenders by monetary value."""
    metrics = CustomerIntelligenceService.get_customer_metrics()
    return metrics['high_spenders'][:limit]


@router.get("/dormant", response_model=List[Dict[str, Any]])
def get_dormant_cohort(
    limit: int = Query(10, ge=1, le=50),
    user=Depends(require_admin),
):
    """Retrieve dormant customers who haven't ordered recently."""
    metrics = CustomerIntelligenceService.get_customer_metrics()
    return metrics['dormant_customers'][:limit]

