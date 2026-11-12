"""
Command to evaluate stock levels and generate low-stock/out-of-stock alerts.
Safe to rerun repeatedly.
"""

from django.core.management.base import BaseCommand
from inventory.services import AlertService


class Command(BaseCommand):
    help = 'Evaluate stock levels across all active products and generate or resolve alerts.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Evaluating product inventory levels for stock alerts...'))
        count = AlertService.generate_all_alerts()
        self.stdout.write(self.style.SUCCESS(f'Successfully completed alert evaluation. Created {count} new alerts.'))
