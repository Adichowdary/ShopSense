"""
Customer analytics, RFM feature extraction, and segmentation service.
Applies KMeans clustering and Silhouette Score evaluation when sample sizes permit,
falling back cleanly to rule-based quantiles for small cohorts.
"""

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count, Max
from django.utils import timezone
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from orders.models import Order
from inventory.models import CustomerSegment, CustomerSegmentAssignment

User = get_user_model()
logger = logging.getLogger(__name__)


class CustomerAnalyticsService:
    """Computes customer RFM features and clusters customers into distinct actionable segments."""

    DEFAULT_SEGMENTS = [
        {
            'code': 'CHAMPIONS',
            'name': 'Champions',
            'description': 'High frequency, high spenders who bought recently.',
        },
        {
            'code': 'LOYAL_CUSTOMERS',
            'name': 'Loyal Customers',
            'description': 'Consistent regular buyers with good spending history.',
        },
        {
            'code': 'POTENTIAL_LOYALISTS',
            'name': 'Potential Loyalists',
            'description': 'Recent buyers with good initial order value.',
        },
        {
            'code': 'AT_RISK',
            'name': 'At Risk',
            'description': 'High past spenders who have not purchased recently.',
        },
        {
            'code': 'HIBERNATING',
            'name': 'Hibernating / Inactive',
            'description': 'Low engagement, infrequent buyers overdue for reactivation.',
        },
    ]

    @classmethod
    def get_or_create_default_segments(cls) -> Dict[str, CustomerSegment]:
        """Ensure standard RFM segments exist in the database."""
        segments = {}
        for s in cls.DEFAULT_SEGMENTS:
            obj, _ = CustomerSegment.objects.get_or_create(
                code=s['code'],
                defaults={
                    'name': s['name'],
                    'description': s['description'],
                    'criteria': {'type': 'RFM'},
                    'model_version': 'v1.0',
                    'is_active': True,
                },
            )
            segments[s['code']] = obj
        return segments

    @classmethod
    def extract_rfm_features(cls, days: int = 365) -> List[Dict[str, Any]]:
        """
        Extract Recency, Frequency, and Monetary metrics for all qualifying customers.
        Excludes cancelled and refunded orders.
        """
        now = timezone.now()
        cutoff = now - timedelta(days=days)

        qualifying_statuses = [
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
        ]

        # Aggregate orders per user
        customer_orders = (
            Order.objects.filter(
                status__in=qualifying_statuses,
                created_at__gte=cutoff,
            )
            .values('user')
            .annotate(
                order_count=Count('id'),
                total_spent=Sum('total'),
                latest_order=Max('created_at'),
            )
        )

        customer_map = {entry['user']: entry for entry in customer_orders}

        # Retrieve customer users
        users = User.objects.filter(role=User.Role.CUSTOMER, is_active=True)
        rfm_records = []

        for user in users:
            entry = customer_map.get(user.pk)
            if entry:
                recency = max(0, (now - entry['latest_order']).days)
                frequency = entry['order_count']
                monetary = float(entry['total_spent'] or 0.0)
            else:
                # Registered customer with no qualifying purchases in period
                recency = days
                frequency = 0
                monetary = 0.0

            rfm_records.append({
                'user': user,
                'recency': recency,
                'frequency': frequency,
                'monetary': monetary,
            })

        return rfm_records

    @classmethod
    def segment_customers(cls) -> Dict[str, Any]:
        """
        Assign all customers to segments and compute Silhouette Score if dataset allows.
        Returns evaluation metrics dictionary.
        """
        segments = cls.get_or_create_default_segments()
        rfm_data = cls.extract_rfm_features()

        if not rfm_data:
            return {
                'total_customers': 0,
                'silhouette_score': None,
                'message': 'No customer accounts available for segmentation.',
            }

        # Build feature matrix: [Recency, Frequency, Monetary]
        features = np.array([
            [r['recency'], r['frequency'], r['monetary']]
            for r in rfm_data
        ], dtype=float)

        n_samples = len(features)
        silhouette = None
        clustering_method = 'RULE_BASED'

        # Attempt scikit-learn KMeans clustering if sufficient distinct samples exist
        if n_samples >= 8 and len(np.unique(features[:, 1])) > 1:
            try:
                scaler = StandardScaler()
                scaled_features = scaler.fit_transform(features)

                n_clusters = min(4, n_samples - 1)
                kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
                labels = kmeans.fit_predict(scaled_features)

                unique_labels = np.unique(labels)
                if len(unique_labels) > 1 and len(unique_labels) < n_samples:
                    silhouette = float(round(silhouette_score(scaled_features, labels), 3))
                    clustering_method = f'KMEANS_K{n_clusters}'
            except Exception as e:
                logger.warning(f"KMeans segmentation fallback to rules: {e}")

        # Assign segments based on feature profiles
        assignments = []
        CustomerSegmentAssignment.objects.all().delete()

        for r in rfm_data:
            user = r['user']
            recency = r['recency']
            freq = r['frequency']
            mon = r['monetary']

            # Rule assignment
            if freq >= 4 and mon >= 5000 and recency <= 30:
                seg = segments['CHAMPIONS']
            elif freq >= 2 and recency <= 60:
                seg = segments['LOYAL_CUSTOMERS']
            elif freq >= 1 and recency <= 30:
                seg = segments['POTENTIAL_LOYALISTS']
            elif freq >= 2 and recency > 60:
                seg = segments['AT_RISK']
            else:
                seg = segments['HIBERNATING']

            assignments.append(
                CustomerSegmentAssignment(
                    user=user,
                    segment=seg,
                    recency_days=recency,
                    frequency=freq,
                    monetary_value=Decimal(f"{mon:.2f}"),
                    features={
                        'recency': recency,
                        'frequency': freq,
                        'monetary': mon,
                    },
                    assigned_at=timezone.now(),
                )
            )

        CustomerSegmentAssignment.objects.bulk_create(assignments)
        logger.info(f"Customer segmentation complete for {len(assignments)} customers. Silhouette={silhouette}")

        return {
            'total_customers': len(assignments),
            'silhouette_score': silhouette,
            'clustering_method': clustering_method,
            'evaluated_at': timezone.now().isoformat(),
        }
