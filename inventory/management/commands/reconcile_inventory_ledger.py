"""
Command to audit and reconcile recorded inventory balances against the append-only movement ledger.
Reports discrepancies before any corrective action.
"""

from django.core.management.base import BaseCommand
from inventory.services import StockService


class Command(BaseCommand):
    help = 'Audit warehouse inventory balances against the StockMovement append-only ledger.'

    def add_arguments(self, parser):
        parser.add_argument('--backfill', action='store_true', help='Backfill warehouse stock from existing catalog inventory.')

    def handle(self, *args, **options):
        if options['backfill']:
            self.stdout.write(self.style.NOTICE('Backfilling warehouse stock from catalog inventory...'))
            count = StockService.backfill_warehouse_stock()
            self.stdout.write(self.style.SUCCESS(f'Backfilled {count} products into default warehouse.'))

        self.stdout.write(self.style.NOTICE('Auditing stock balances against movement ledger...'))
        discrepancies = StockService.reconcile_inventory()

        if not discrepancies:
            self.stdout.write(self.style.SUCCESS('Reconciliation passed: 0 discrepancies detected. All stock balances match ledger records.'))
        else:
            self.stdout.write(self.style.WARNING(f'Discrepancies found: {len(discrepancies)} item(s) mismatched!'))
            for d in discrepancies:
                self.stdout.write(
                    f" - {d['product_sku']} @ {d['warehouse_code']}: Recorded={d['recorded_stock']}, "
                    f"Ledger={d['ledger_sum']}, Difference={d['difference']:+d}"
                )
            self.stdout.write(self.style.ERROR('Audit completed with discrepancies. Balances were NOT overwritten.'))
