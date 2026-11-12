"""
Django management command to run scheduled analytical workflows.
Usage:
    python manage.py run_analytical_workflows --all
    python manage.py run_analytical_workflows --workflow REVENUE_ANALYTICS --force
"""

from django.core.management.base import BaseCommand
from inventory.models import AnalyticalWorkflowRun
from inventory.services.workflow_services import AnalyticalWorkflowScheduler


class Command(BaseCommand):
    help = "Executes automated analytical workflows with retry policies and execution logging."

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Execute all 7 analytical workflows sequentially.',
        )
        parser.add_argument(
            '--workflow',
            type=str,
            help='Execute a specific workflow by name (e.g., REVENUE_ANALYTICS, INVENTORY_FORECAST).',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Bypass active lock check and force execution.',
        )
        parser.add_argument(
            '--retries',
            type=int,
            default=3,
            help='Maximum retry attempts per workflow (default: 3).',
        )

    def handle(self, *args, **options):
        run_all = options['all']
        workflow_name = options['workflow']
        force = options['force']
        max_retries = options['retries']

        if not run_all and not workflow_name:
            self.stdout.write(self.style.WARNING("No workflow specified. Defaulting to --all."))
            run_all = True

        self.stdout.write(self.style.NOTICE("Starting ShopSense Automated Analytical Workflow Engine..."))

        if run_all:
            runs = AnalyticalWorkflowScheduler.execute_all_workflows(max_retries=max_retries, force=force)
        else:
            run = AnalyticalWorkflowScheduler.execute_workflow(workflow_name, max_retries=max_retries, force=force)
            runs = [run]

        success_count = sum(1 for r in runs if r.status == AnalyticalWorkflowRun.Status.SUCCESS)
        total_count = len(runs)
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0.0

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(f"{'WORKFLOW NAME':<35} | {'STATUS':<10} | {'DURATION':<10} | {'RETRIES'}")
        self.stdout.write("-" * 70)

        for r in runs:
            status_style = self.style.SUCCESS if r.status == AnalyticalWorkflowRun.Status.SUCCESS else self.style.ERROR
            self.stdout.write(
                f"{r.workflow_name:<35} | {status_style(r.status):<19} | {r.duration_seconds:<8.3f}s | {r.retry_count}"
            )

        self.stdout.write("=" * 70)
        self.stdout.write(
            self.style.SUCCESS(
                f"Completed: {success_count}/{total_count} succeeded ({success_rate:.1f}% success rate)."
            )
        )

