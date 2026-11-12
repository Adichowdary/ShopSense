"""
Command to compute RFM features and update customer segmentation assignments.
"""

from django.core.management.base import BaseCommand
from inventory.services import CustomerAnalyticsService


class Command(BaseCommand):
    help = 'Extract RFM features from qualifying orders and cluster customers into segments.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Extracting customer order history and clustering segments...'))
        results = CustomerAnalyticsService.segment_customers()
        total = results.get('total_customers', 0)
        silhouette = results.get('silhouette_score')
        method = results.get('clustering_method', 'RULE_BASED')

        silhouette_str = f"{silhouette:.3f}" if silhouette is not None else "N/A (sample size insufficient)"
        self.stdout.write(self.style.SUCCESS(
            f"Segmented {total} customers using {method}. Measured Silhouette Score: {silhouette_str}."
        ))
