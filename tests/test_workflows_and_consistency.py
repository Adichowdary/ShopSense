"""
Tests for Automated Analytical Workflows and Data Consistency Reconciliation (Modules 9, 11, 12).
Validates:
1. Execution of all 7 analytical workflows with retry policies and execution logging.
2. 100% workflow success rate across scheduled runs (Module 12 target).
3. Dashboard data consistency reconciliation against source facts (>= 99% target, Module 11).
4. CLI management commands: run_analytical_workflows & validate_dashboard_consistency.
"""

import io
import pytest
from decimal import Decimal
from django.core.management import call_command
from django.utils import timezone

from accounts.models import User
from catalog.models import Category, Inventory, Product
from orders.models import Order, OrderItem
from vendors.models import VendorProfile

from inventory.models import AnalyticalWorkflowRun, DataConsistencyLog, Warehouse, WarehouseStock
from inventory.services.workflow_services import AnalyticalWorkflowScheduler
from inventory.services.consistency_services import DashboardDataConsistencyReconciler


@pytest.fixture
def workflow_test_data(db):
    """Seed minimal valid operational data for end-to-end workflow validation."""
    admin = User.objects.create_superuser(
        email='wf_admin@shopsense.com',
        password='TestPassword123!',
    )
    v_user = User.objects.create_user(
        email='wf_vendor@shopsense.com',
        password='TestPassword123!',
        role=User.Role.VENDOR,
    )
    vendor = VendorProfile.objects.create(
        user=v_user,
        vendor_id='VND-WF-001',
        business_name='Workflow Vendor Store',
        contact_email=v_user.email,
        is_active=True,
    )
    customer = User.objects.create_user(
        email='wf_customer@shopsense.com',
        password='TestPassword123!',
        role=User.Role.CUSTOMER,
    )
    cat = Category.objects.create(name='Workflow Cat', slug='workflow-cat')
    prod = Product.objects.create(
        vendor=vendor,
        category=cat,
        name='Workflow Drone',
        slug='workflow-drone',
        sku='WF-DRONE-01',
        price=Decimal('12000.00'),
        status=Product.Status.ACTIVE,
    )
    Inventory.objects.create(product=prod, quantity=30, low_stock_threshold=5)

    wh = Warehouse.objects.create(name='Main Hub', code='WH-MAIN', status=Warehouse.Status.ACTIVE)
    WarehouseStock.objects.create(warehouse=wh, product=prod, quantity=30, reserved_quantity=2)

    order = Order.objects.create(
        user=customer,
        order_number='ORD-WF-5001',
        status=Order.Status.DELIVERED,
        subtotal=Decimal('12000.00'),
        total=Decimal('12000.00'),
    )
    OrderItem.objects.create(
        order=order,
        product=prod,
        vendor=vendor,
        product_name=prod.name,
        product_sku=prod.sku,
        quantity=1,
        unit_price=Decimal('12000.00'),
        total_price=Decimal('12000.00'),
        status=OrderItem.Status.DELIVERED,
    )
    return {'admin': admin, 'vendor': vendor, 'product': prod, 'order': order}


@pytest.mark.django_db
class TestAnalyticalWorkflowScheduler:
    """Validate all 7 analytical workflows, retry handling, and 100% success rate."""

    def test_revenue_analytics_workflow(self, workflow_test_data):
        run = AnalyticalWorkflowScheduler.execute_workflow(
            AnalyticalWorkflowRun.WorkflowName.REVENUE_ANALYTICS,
            force=True,
        )
        assert run.status == AnalyticalWorkflowRun.Status.SUCCESS
        assert run.duration_seconds > 0.0
        assert "total_revenue" in run.metadata

    def test_inventory_forecast_workflow(self, workflow_test_data):
        run = AnalyticalWorkflowScheduler.execute_workflow(
            AnalyticalWorkflowRun.WorkflowName.INVENTORY_FORECAST,
            force=True,
        )
        assert run.status == AnalyticalWorkflowRun.Status.SUCCESS
        assert "catalog_products_processed" in run.metadata

    def test_customer_segmentation_workflow(self, workflow_test_data):
        run = AnalyticalWorkflowScheduler.execute_workflow(
            AnalyticalWorkflowRun.WorkflowName.CUSTOMER_SEGMENTATION,
            force=True,
        )
        assert run.status == AnalyticalWorkflowRun.Status.SUCCESS
        assert "total_customers" in run.metadata

    def test_product_recommendation_workflow(self, workflow_test_data):
        run = AnalyticalWorkflowScheduler.execute_workflow(
            AnalyticalWorkflowRun.WorkflowName.PRODUCT_RECOMMENDATION,
            force=True,
        )
        assert run.status == AnalyticalWorkflowRun.Status.SUCCESS
        assert "precision_at_k" in run.metadata

    def test_dashboard_metric_refresh_workflow(self, workflow_test_data):
        run = AnalyticalWorkflowScheduler.execute_workflow(
            AnalyticalWorkflowRun.WorkflowName.DASHBOARD_METRIC_REFRESH,
            force=True,
        )
        assert run.status == AnalyticalWorkflowRun.Status.SUCCESS
        assert "on_hand_stock" in run.metadata

    def test_analytical_report_generation_workflow(self, workflow_test_data):
        run = AnalyticalWorkflowScheduler.execute_workflow(
            AnalyticalWorkflowRun.WorkflowName.ANALYTICAL_REPORT_GENERATION,
            force=True,
        )
        assert run.status == AnalyticalWorkflowRun.Status.SUCCESS
        assert "pdf_report_size_bytes" in run.metadata

    def test_model_evaluation_tracking_workflow(self, workflow_test_data):
        run = AnalyticalWorkflowScheduler.execute_workflow(
            AnalyticalWorkflowRun.WorkflowName.MODEL_EVALUATION_TRACKING,
            force=True,
        )
        assert run.status == AnalyticalWorkflowRun.Status.SUCCESS
        assert run.metadata.get("all_passed") is True

    def test_all_workflows_100_percent_success_rate(self, workflow_test_data):
        """Mandatory quantitative target: 100% workflow success rate across scheduled runs."""
        runs = AnalyticalWorkflowScheduler.execute_all_workflows(force=True)
        assert len(runs) == 7

        success_count = sum(1 for r in runs if r.status == AnalyticalWorkflowRun.Status.SUCCESS)
        success_rate = (success_count / len(runs)) * 100.0

        assert success_rate == 100.0, f"Workflow success rate was {success_rate:.1f}%, expected 100.0%"

    def test_unknown_workflow_graceful_failure(self, workflow_test_data):
        run = AnalyticalWorkflowScheduler.execute_workflow("UNKNOWN_WORKFLOW_NAME", force=True)
        assert run.status == AnalyticalWorkflowRun.Status.FAILED
        assert "Unknown workflow name" in run.error_message


@pytest.mark.django_db
class TestDashboardDataConsistencyReconciler:
    """Validate source-to-analytics consistency target >= 99%."""

    def test_reconciliation_audit_passes_threshold(self, workflow_test_data):
        result = DashboardDataConsistencyReconciler.run_reconciliation_audit()

        assert result['passed'] is True
        assert result['overall_consistency_percentage'] >= 99.0
        assert len(result['discrepancies']) == 0

        # Verify entry in DataConsistencyLog
        latest_log = DataConsistencyLog.objects.first()
        assert latest_log is not None
        assert latest_log.overall_consistency_percentage >= 99.0
        assert latest_log.passed is True


@pytest.mark.django_db
class TestManagementCommands:
    """Validate CLI management command execution."""

    def test_run_analytical_workflows_command(self, workflow_test_data):
        out = io.StringIO()
        call_command('run_analytical_workflows', '--all', '--force', stdout=out)
        output = out.getvalue()
        assert "Completed: 7/7 succeeded (100.0% success rate)" in output

    def test_validate_dashboard_consistency_command(self, workflow_test_data):
        out = io.StringIO()
        call_command('validate_dashboard_consistency', stdout=out)
        output = out.getvalue()
        assert "DATA CONSISTENCY AUDIT PASSED" in output
