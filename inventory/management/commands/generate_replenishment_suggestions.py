"""
Command to evaluate inventory reorder points and generate replenishment suggestions.
"""

from django.core.management.base import BaseCommand
from inventory.services import ReplenishmentService


class Command(BaseCommand):
    help = 'Evaluate inventory demand and generate replenishment suggestions for low-stock items.'

    def add_arguments(self, parser):
        parser.add_argument('--lead-time', type=int, default=7, help='Supplier lead time in days (default: 7)')
        parser.add_argument('--safety-stock', type=int, default=10, help='Safety stock buffer in units (default: 10)')

    def handle(self, *args, **options):
        lead_time = options['lead_time']
        safety_stock = options['safety_stock']
        self.stdout.write(self.style.NOTICE(f'Calculating replenishment needs (Lead time: {lead_time}d, Safety: {safety_stock})...'))
        count = ReplenishmentService.generate_all_suggestions(
            lead_time_days=lead_time,
            safety_stock=safety_stock,
        )
        self.stdout.write(self.style.SUCCESS(f'Successfully generated {count} replenishment suggestions.'))
