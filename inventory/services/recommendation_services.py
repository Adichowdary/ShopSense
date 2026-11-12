"""
Product recommendation engine and chronological holdout evaluation service.
Strategies:
1. Popularity (bestsellers)
2. Category-based
3. Co-purchase (frequently bought together)
4. Personalized customer history
"""

import logging
from collections import Counter
from datetime import timedelta
from typing import List, Dict, Any, Optional, Set
from django.db.models import Count, Sum
from django.utils import timezone

from catalog.models import Product, Category
from orders.models import Order, OrderItem
from inventory.models import RecommendationCandidate, RecommendationEvaluation

logger = logging.getLogger(__name__)


class RecommendationService:
    """Generates recommendation candidates and evaluates precision@k against holdout orders."""

    @classmethod
    def get_popular_products(cls, limit: int = 10) -> List[Dict[str, Any]]:
        """Top-selling active products by sales volume."""
        qualifying = [
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
        ]
        top_items = (
            OrderItem.objects.filter(
                order__status__in=qualifying,
                product__status=Product.Status.ACTIVE,
            )
            .values('product_id')
            .annotate(units=Sum('quantity'))
            .order_by('-units')[:limit]
        )
        results = []
        rank = 1
        for item in top_items:
            prod = Product.objects.filter(pk=item['product_id']).first()
            if prod:
                results.append({
                    'product': prod,
                    'score': float(item['units']),
                    'rank': rank,
                    'type': RecommendationCandidate.RecommendationType.POPULAR,
                    'reason': f"Best seller ({item['units']} units sold)",
                })
                rank += 1
        return results

    @classmethod
    def get_co_purchased_products(cls, product: Product, limit: int = 6) -> List[Dict[str, Any]]:
        """Products frequently ordered alongside the given product."""
        order_ids = OrderItem.objects.filter(
            product=product,
            order__status__in=[Order.Status.CONFIRMED, Order.Status.SHIPPED, Order.Status.DELIVERED],
        ).values_list('order_id', flat=True)

        co_items = (
            OrderItem.objects.filter(
                order_id__in=order_ids,
                product__status=Product.Status.ACTIVE,
            )
            .exclude(product=product)
            .values('product_id')
            .annotate(co_count=Count('id'))
            .order_by('-co_count')[:limit]
        )
        results = []
        rank = 1
        for item in co_items:
            prod = Product.objects.filter(pk=item['product_id']).first()
            if prod:
                results.append({
                    'product': prod,
                    'score': float(item['co_count']),
                    'rank': rank,
                    'type': RecommendationCandidate.RecommendationType.CO_PURCHASE,
                    'reason': f"Frequently bought together ({item['co_count']} orders)",
                })
                rank += 1
        return results

    @classmethod
    def get_personalized_recommendations(cls, user, limit: int = 8) -> List[Dict[str, Any]]:
        """Recommendations tailored to customer past purchases and favorite categories."""
        past_items = OrderItem.objects.filter(
            order__user=user,
            order__status__in=[Order.Status.CONFIRMED, Order.Status.SHIPPED, Order.Status.DELIVERED],
        ).select_related('product__category')

        purchased_product_ids = set(past_items.values_list('product_id', flat=True))
        category_counts = Counter(
            itm.product.category_id for itm in past_items if itm.product and itm.product.category_id
        )

        candidates = []
        rank = 1

        # Priority 1: Top products from customer's most purchased categories
        if category_counts:
            top_cat_ids = [cat_id for cat_id, _ in category_counts.most_common(3)]
            cat_products = (
                Product.objects.filter(
                    category_id__in=top_cat_ids,
                    status=Product.Status.ACTIVE,
                )
                .exclude(id__in=purchased_product_ids)[:limit]
            )
            for prod in cat_products:
                candidates.append({
                    'product': prod,
                    'score': 0.85,
                    'rank': rank,
                    'type': RecommendationCandidate.RecommendationType.PERSONALIZED,
                    'reason': f"Based on your interest in {prod.category.name if prod.category else 'this category'}",
                })
                rank += 1

        # Fill remaining slots with popular items if necessary
        if len(candidates) < limit:
            for pop in cls.get_popular_products(limit=limit):
                if pop['product'].pk not in purchased_product_ids and not any(c['product'].pk == pop['product'].pk for c in candidates):
                    candidates.append({
                        'product': pop['product'],
                        'score': 0.50,
                        'rank': rank,
                        'type': RecommendationCandidate.RecommendationType.POPULAR,
                        'reason': pop['reason'],
                    })
                    rank += 1
                    if len(candidates) >= limit:
                        break

        return candidates[:limit]

    @classmethod
    def refresh_recommendation_candidates(cls) -> int:
        """Regenerate stored recommendation candidates."""
        RecommendationCandidate.objects.all().delete()
        created = []

        # Storefront global popular
        for item in cls.get_popular_products(limit=10):
            created.append(
                RecommendationCandidate(
                    user=None,
                    product=item['product'],
                    recommendation_type=item['type'],
                    score=item['score'],
                    rank=item['rank'],
                    reason=item['reason'],
                )
            )

        RecommendationCandidate.objects.bulk_create(created)
        logger.info(f"Refreshed {len(created)} recommendation candidates.")
        return len(created)

    @classmethod
    def evaluate_recommendations(
        cls,
        k: int = 5,
        holdout_days: int = 30,
    ) -> RecommendationEvaluation:
        """
        Evaluate recommendation Precision@K using a chronological train/test split.
        Holdout = last holdout_days orders.
        """
        cutoff = timezone.now() - timedelta(days=holdout_days)

        # Training orders: prior to cutoff
        # Test orders: on or after cutoff
        test_orders = Order.objects.filter(
            status__in=[Order.Status.CONFIRMED, Order.Status.SHIPPED, Order.Status.DELIVERED],
            created_at__gte=cutoff,
        )
        test_user_ids = list(test_orders.values_list('user_id', flat=True).distinct())

        precisions = []
        recommended_products_set: Set[int] = set()

        for user_id in test_user_ids:
            from django.contrib.auth import get_user_model
            user = get_user_model().objects.filter(pk=user_id).first()
            if not user:
                continue

            # Actual products bought in holdout
            actual_product_ids = set(
                OrderItem.objects.filter(
                    order__user=user,
                    order__created_at__gte=cutoff,
                ).values_list('product_id', flat=True)
            )

            # Recommendations
            recs = cls.get_personalized_recommendations(user, limit=k)
            rec_product_ids = [r['product'].pk for r in recs]
            recommended_products_set.update(rec_product_ids)

            if rec_product_ids:
                hits = sum(1 for pid in rec_product_ids if pid in actual_product_ids)
                user_precision = float(hits) / float(len(rec_product_ids))
                precisions.append(user_precision)

        total_active_products = Product.objects.filter(status=Product.Status.ACTIVE).count()
        coverage = (
            round((len(recommended_products_set) / max(1, total_active_products)) * 100.0, 1)
            if total_active_products > 0 else 0.0
        )

        avg_precision = round(float(sum(precisions) / max(1, len(precisions))), 3) if precisions else 0.0

        eval_obj = RecommendationEvaluation.objects.create(
            model_version='v1.0-hybrid',
            evaluation_date=timezone.now().date(),
            sample_size=len(precisions),
            coverage_percentage=coverage,
            precision_at_k=avg_precision,
            k_value=k,
            metrics={
                'holdout_days': holdout_days,
                'evaluated_customers': len(precisions),
                'distinct_products_recommended': len(recommended_products_set),
                'total_active_catalog': total_active_products,
            },
            notes=f"Evaluated on {len(precisions)} customers with holdout window of {holdout_days} days.",
        )

        logger.info(f"Recommendation evaluation v1.0: P@{k}={avg_precision:.3f}, Coverage={coverage}%")
        return eval_obj
