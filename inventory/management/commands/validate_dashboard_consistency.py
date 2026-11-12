"""
Django management command to audit dashboard data consistency against source records.
Usage:
    python manage.py validate_dashboard_consistency
"""

import sys
from django.core.management.base import BaseCommand
from inventory.services.consistency_services import DashboardDataConsistencyReconciler


class Command(BaseCommand):
    help = "Validates consistency between source database facts and analytics dashboard metrics."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Running ShopSense Dashboard Data Consistency Audit..."))

        result = DashboardDataConsistencyReconciler.run_reconciliation_audit()

        self.stdout.write("\n" + "=" * 75)
        self.stdout.write(f"{'METRIC NAME':<25} | {'SOURCE VALUE':<15} | {'ANALYTICS VALUE':<15} | {'MATCH'}")
        self.stdout.write("-" * 75)

        for metric_name, data in result['metrics_compared'].items():
            match_style = self.style.SUCCESS("PASS") if data['matched'] else self.style.ERROR("FAIL")
            self.stdout.write(
                f"{metric_name:<25} | {str(data['source_value']):<15} | {str(data['analytics_value']):<15} | {match_style}"
            )

        self.stdout.write("=" * 75)
        overall_pct = result['overall_consistency_percentage']
        passed = result['passed']

        if passed:
            self.stdout.write(
                self.style.SUCCESS(
                    f"DATA CONSISTENCY AUDIT PASSED: {overall_pct:.2f}% consistency (Target: >= {result['target_threshold']:.1f}%)."
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"DATA CONSISTENCY AUDIT FAILED: {overall_pct:.2f}% consistency (Target: >= {result['target_threshold']:.1f}%)."
                )
            )
            for d in result['discrepancies']:
                self.stdout.write(self.style.WARNING(f"  Discrepancy in {d['metric']}: diff={d['difference']}"))
            sys.exit(1)

