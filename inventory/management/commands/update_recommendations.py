"""
Command to refresh precomputed recommendation candidates for storefront and customers.
"""

from django.core.management.base import BaseCommand
from inventory.services import RecommendationService


class Command(BaseCommand):
    help = 'Refresh product recommendation candidates based on sales volume and co-purchases.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Refreshing recommendation candidate pool...'))
        count = RecommendationService.refresh_recommendation_candidates()
        self.stdout.write(self.style.SUCCESS(f'Successfully refreshed {count} recommendation candidates.'))
