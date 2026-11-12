"""
FastAPI Router: Recommendation Intelligence API.
Provides product recommendations, co-purchase associations, and engine evaluation metrics.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from django.contrib.auth import get_user_model

from api.auth import get_current_user
from api.schemas import (
    RecommendationResponse,
    RecommendationItem,
    RecommendationMetricsResponse,
)
from catalog.models import Product
from inventory.services.bi_services import RecommendationIntelligenceService
from inventory.services.recommendation_services import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["Recommendation Intelligence"])
User = get_user_model()


@router.get("/popular", response_model=RecommendationResponse)
def get_popular_recommendations(
    limit: int = Query(10, ge=1, le=50),
    user=Depends(get_current_user),
):
    """Retrieve top-selling product recommendations across the marketplace."""
    items = RecommendationService.get_popular_products(limit=limit)
    recs = [
        RecommendationItem(
            product_id=it['product'].id,
            sku=it['product'].sku,
            name=it['product'].name,
            score=it['score'],
            rank=it['rank'],
            reason=it['reason'],
            price=float(it['product'].price),
        )
        for it in items
    ]
    return RecommendationResponse(
        strategy="POPULAR",
        count=len(recs),
        recommendations=recs,
    )


@router.get("/co-purchase/{product_id}", response_model=RecommendationResponse)
def get_co_purchased_recommendations(
    product_id: int,
    limit: int = Query(6, ge=1, le=20),
    user=Depends(get_current_user),
):
    """Retrieve products frequently ordered alongside the given product."""
    product = Product.objects.filter(pk=product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    items = RecommendationService.get_co_purchased_products(product=product, limit=limit)
    recs = [
        RecommendationItem(
            product_id=it['product'].id,
            sku=it['product'].sku,
            name=it['product'].name,
            score=it['score'],
            rank=it['rank'],
            reason=it['reason'],
            price=float(it['product'].price),
        )
        for it in items
    ]
    return RecommendationResponse(
        strategy="CO_PURCHASE",
        count=len(recs),
        recommendations=recs,
    )


@router.get("/customer/{customer_id}", response_model=RecommendationResponse)
def get_customer_personalized_recommendations(
    customer_id: int,
    limit: int = Query(8, ge=1, le=20),
    current_user=Depends(get_current_user),
):
    """Retrieve personalized product recommendations based on customer purchase history."""
    # Ensure customers cannot snoop on another customer's personalized suggestions
    is_admin = hasattr(current_user, 'can_access_admin_dashboard') and current_user.can_access_admin_dashboard()
    if not is_admin and current_user.id != customer_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot view another customer's recommendations")

    target_user = User.objects.filter(pk=customer_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Customer not found")

    items = RecommendationService.get_personalized_recommendations(user=target_user, limit=limit)
    recs = [
        RecommendationItem(
            product_id=it['product'].id,
            sku=it['product'].sku,
            name=it['product'].name,
            score=it['score'],
            rank=it['rank'],
            reason=it['reason'],
            price=float(it['product'].price),
        )
        for it in items
    ]
    return RecommendationResponse(
        strategy="PERSONALIZED",
        count=len(recs),
        recommendations=recs,
    )


@router.get("/performance", response_model=RecommendationMetricsResponse)
def get_recommendation_performance(user=Depends(get_current_user)):
    """Retrieve recommendation engine performance metrics (Precision@K, coverage)."""
    kpis = RecommendationIntelligenceService.get_recommendation_kpis()
    return RecommendationMetricsResponse(
        precision_at_k=kpis['precision_at_k'],
        coverage_percentage=kpis['coverage_percentage'],
        total_candidates=kpis['total_candidates'],
        k_value=5,
    )

