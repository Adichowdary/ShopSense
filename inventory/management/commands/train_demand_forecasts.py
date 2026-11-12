"""
Command to train chronological demand forecasting models and generate predictions.
"""

from django.core.management.base import BaseCommand
from inventory.services import ForecastService


class Command(BaseCommand):
    help = 'Train demand forecasting models on historical sales and generate future daily predictions.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Training demand forecasting models for active products...'))
        count = ForecastService.train_all_forecasts()
        self.stdout.write(self.style.SUCCESS(f'Successfully trained forecast models for {count} products.'))
