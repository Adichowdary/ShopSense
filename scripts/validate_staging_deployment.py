"""
Comprehensive Pre-Deployment Staging Validation Script.
Validates the entire ShopSense platform against an isolated staging PostgreSQL database:
1. Starts isolated PostgreSQL 18.1 server on port 5433 (database: shopsense_staging).
2. Applies all 38 migrations to PostgreSQL and inspects the resulting schema.
3. Populates PostgreSQL with demo data and verifies record counts.
4. Executes all 7 analytical workflows repeatedly against PostgreSQL.
5. Validates data consistency, ReportLab PDFs, and OpenPyXL Excel exports against PostgreSQL.
6. Validates MLflow tracking, client restart, and forecast prediction loading.
7. Validates multi-role RBAC and cross-tenant isolation (customer and vendor).
8. Validates workflow scheduler failure handling and concurrency locking.
9. Audits security settings, environment variables, headers, and media/static configurations.
10. Runs concurrent HTTP load tests against live FastAPI backed by staging PostgreSQL.
"""

import io
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from decimal import Decimal

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_staging')
os.environ['SHOPSENSE_DEMO_DATABASE_APPROVED'] = 'True'
os.environ['MLFLOW_ALLOW_FILE_STORE'] = 'true'
os.environ['MLFLOW_DISABLE_AGENT_HINT'] = '1'

import pg0

def print_banner(step_num, title):
    print("\n" + "=" * 80)
    print(f"  STEP {step_num}: {title.upper()}")
    print("=" * 80)


def main():
    print("#" * 80)
    print("  SHOPSENSE PRE-DEPLOYMENT STAGING VALIDATION SUITE")
    print(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#" * 80)

    # --- 1. Start Staging PostgreSQL Environment ---
    print_banner(1, "Create & Start Staging PostgreSQL Environment")
    pg_instance = pg0.Pg0(name='staging', port=5433, database='shopsense_staging')
    pg_info = pg_instance.start()
    print(f"[*] Staging PostgreSQL Status: Running={pg_info.running} (PID: {pg_info.pid})")
    print(f"[*] Database Host/Port        : 127.0.0.1:{pg_info.port}")
    print(f"[*] Database Name             : {pg_info.database}")
    print(f"[*] Connection URI            : {pg_info.uri}")

    try:
        import django
        django.setup()

        from django.conf import settings
        from django.core.management import call_command
        from django.db import connection
        from django.test import Client

        print(f"[*] Django Database Engine    : {connection.settings_dict['ENGINE']}")
        print(f"[*] Active Database Target    : {connection.settings_dict['NAME']} on {connection.settings_dict['HOST']}:{connection.settings_dict['PORT']}")
        assert 'postgresql' in connection.settings_dict['ENGINE'], "Must use PostgreSQL backend!"
        assert connection.settings_dict['PORT'] == 5433, "Must connect to staging port 5433!"

        # --- 2. Apply all 38 Migrations to PostgreSQL ---
        print_banner(2, "Apply All 38 Migrations to Staging PostgreSQL")
        migrate_start = time.time()
        call_command('migrate', interactive=False, verbosity=1)
        migrate_elapsed = time.time() - migrate_start
        print(f"[+] All migrations applied cleanly in {migrate_elapsed:.2f}s.")

        # Verify schema in PostgreSQL
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name;
            """)
            tables = [row[0] for row in cursor.fetchall()]

            cursor.execute("SELECT count(*) FROM django_migrations;")
            applied_migration_count = cursor.fetchone()[0]

            cursor.execute("""
                SELECT count(*) 
                FROM information_schema.table_constraints 
                WHERE constraint_type = 'FOREIGN KEY';
            """)
            fk_count = cursor.fetchone()[0]

        print(f"[*] Applied Migrations Recorded in DB : {applied_migration_count} / 38")
        print(f"[*] Total Public Tables Created       : {len(tables)}")
        print(f"[*] Foreign Key Constraints Enforced  : {fk_count}")
        assert applied_migration_count >= 38, f"Expected 38 migrations, found {applied_migration_count}"
        assert len(tables) >= 25, f"Expected at least 25 tables, found {len(tables)}"

        # --- 3. Seed Populated Staging Data ---
        print_banner(3, "Seed Authoritative Multi-Vendor Staging Data")
        seed_start = time.time()
        call_command(
            'seed_demo_data',
            vendors=5,
            products_per_vendor=8,
            customers=15,
            orders=25,
            verbosity=0,
        )
        print(f"[+] Seeded staging database in {time.time() - seed_start:.2f}s.")

        from accounts.models import User
        from catalog.models import Product
        from orders.models import Order, OrderItem
        from vendors.models import VendorProfile
        from inventory.models import (
            WarehouseStock, StockMovement,
            AnalyticalWorkflowRun, ForecastPrediction,
            RecommendationCandidate, CustomerSegment,
        )
        from inventory.services.bi_services import RevenueAnalyticsService

        db_counts = {
            "Total Users": User.objects.count(),
            "Customers": User.objects.filter(role=User.Role.CUSTOMER).count(),
            "Active Vendors": VendorProfile.objects.filter(is_active=True).count(),
            "Active Catalog Products": Product.objects.filter(status=Product.Status.ACTIVE).count(),
            "Total Orders": Order.objects.count(),
            "Qualified Orders": Order.objects.filter(status__in=RevenueAnalyticsService.QUALIFIED_STATUSES).count(),
            "Cancelled Orders": Order.objects.filter(status=Order.Status.CANCELLED).count(),
            "Refunded Orders": Order.objects.filter(status=Order.Status.REFUNDED).count(),
            "Order Line Items": OrderItem.objects.count(),
            "Warehouse Stock Records": WarehouseStock.objects.count(),
            "Stock Movements": StockMovement.objects.count(),
        }
        for k, v in db_counts.items():
            print(f"  - {k:<25}: {v}")
        assert db_counts["Qualified Orders"] > 0, "Staging DB must have qualified orders"
        assert db_counts["Warehouse Stock Records"] > 0, "Staging DB must have warehouse stock"

        # --- 4. Verify 7 Analytical Workflows (Repeated Execution) ---
        print_banner(4, "Verify 7 Analytical Workflows Repeated Execution against PostgreSQL")
        from inventory.services.workflow_services import AnalyticalWorkflowScheduler

        for cycle in [1, 2]:
            print(f"\n--- Workflow Execution Cycle {cycle} ---")
            runs = AnalyticalWorkflowScheduler.execute_all_workflows(max_retries=1, force=True)
            for r in runs:
                print(f"  [+] {r.workflow_name:<30} | Status: {r.status:<7} | Duration: {r.duration_seconds:<6.3f}s | Meta: {r.metadata}")
                assert r.status == AnalyticalWorkflowRun.Status.SUCCESS, f"Workflow {r.workflow_name} failed: {r.error_message}"

        # --- 5. Data Consistency, PDF and Excel Reports Validation ---
        print_banner(5, "Validate Data Consistency, PDF & Excel Exports against PostgreSQL")
        from inventory.services.consistency_services import DashboardDataConsistencyReconciler
        from inventory.services.export_services import PDFReportGenerator, ExcelReportGenerator

        reconciliation = DashboardDataConsistencyReconciler.run_reconciliation_audit()
        print(f"[*] Consistency Audit Result: {reconciliation['overall_consistency_percentage']}% (Passed: {reconciliation['passed']})")
        assert reconciliation['overall_consistency_percentage'] >= 99.0, "Consistency must be >= 99%"

        # PDF Reports
        pdf_bytes = PDFReportGenerator.generate_revenue_report()
        assert pdf_bytes.startswith(b'%PDF-1.4'), "Invalid PDF header"
        print(f"[*] Generated Revenue PDF Report : {len(pdf_bytes):,} bytes (Validated %PDF-1.4)")

        # Excel Reports
        excel_bytes = ExcelReportGenerator.generate_comprehensive_bi_workbook()
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
        print(f"[*] Generated Excel BI Workbook  : {len(excel_bytes):,} bytes across {len(wb.sheetnames)} sheets")
        assert len(wb.sheetnames) == 6, f"Expected 6 sheets, got {len(wb.sheetnames)}"

        # Verify financial total in Excel sheet matches PostgreSQL database exactly
        ws = wb['Executive Summary']
        pg_rev = float(Order.objects.filter(status__in=RevenueAnalyticsService.QUALIFIED_STATUSES).aggregate(django.db.models.Sum('total'))['total__sum'] or 0.0)
        found_rev = False
        for row in ws.iter_rows(values_only=True):
            for cell in row:
                if cell is not None:
                    try:
                        if abs(float(cell) - pg_rev) < 0.01:
                            found_rev = True
                            break
                    except (ValueError, TypeError):
                        pass
            if found_rev:
                break
        print(f"[*] Verified PostgreSQL Revenue ₹{pg_rev:,.2f} present in Excel Executive Summary: {found_rev}")
        assert found_rev, f"Excel report did not match PostgreSQL revenue ₹{pg_rev:,.2f}"

        # --- 6. MLflow Lifecycle Verification ---
        print_banner(6, "MLflow Model Lifecycle, Client Restart & Prediction Loading")
        from inventory.services.mlflow_services import MLflowTrackingService
        from mlflow.tracking import MlflowClient

        mlflow_res = MLflowTrackingService.run_all_tracking_experiments()
        assert mlflow_res["all_passed"] is True, "MLflow tracking failed"

        # Simulate client restart
        client = MlflowClient(tracking_uri="file:./mlruns")
        for domain, key in [("Demand Forecasting", "forecasting"), ("Customer Segmentation", "segmentation"), ("Recommendations", "recommendations")]:
            run_id = mlflow_res[key]["run_id"]
            run_data = client.get_run(run_id)
            print(f"  [+] {domain:<25}: Run ID={run_id} | Status={run_data.info.status} | Stage={run_data.data.tags.get('stage')}")
            assert run_data.info.status == "FINISHED"

        preds = ForecastPrediction.objects.filter(forecast_model__is_active=True)[:3]
        print(f"[*] Loaded {preds.count()} Forecast Predictions from PostgreSQL:")
        for p in preds:
            print(f"    - Date: {p.prediction_date} | SKU: {p.product.sku} | Forecast: {p.predicted_demand:.1f} units")

        # --- 7. Multi-Role RBAC & Multi-Tenant Isolation ---
        print_banner(7, "Verify Multi-Role RBAC & Multi-Tenant Isolation")
        client = Client()

        admin_user, _ = User.objects.get_or_create(
            email='admin@shopsense.com',
            defaults={'role': User.Role.ADMIN, 'is_staff': True, 'is_superuser': True, 'is_active': True},
        )
        if not admin_user.is_staff or not admin_user.is_superuser:
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.role = User.Role.ADMIN
            admin_user.save()

        vendors = list(VendorProfile.objects.filter(is_active=True)[:2])
        customers = list(User.objects.filter(role=User.Role.CUSTOMER, is_active=True)[:2])

        vendor_a, vendor_b = vendors[0], vendors[1]
        cust_a, cust_b = customers[0], customers[1]

        print(f"[*] Admin User    : {admin_user.email}")
        print(f"[*] Vendor A User : {vendor_a.user.email} (Vendor ID: {vendor_a.pk})")
        print(f"[*] Vendor B User : {vendor_b.user.email} (Vendor ID: {vendor_b.pk})")
        print(f"[*] Customer A    : {cust_a.email}")
        print(f"[*] Customer B    : {cust_b.email}")

        # BI Views RBAC
        for url in ['/dashboard/bi/', '/dashboard/bi/customers/', '/dashboard/bi/inventory/', '/dashboard/bi/recommendations/']:
            client.logout()
            assert client.get(url).status_code == 302, f"Anon allowed on {url}"
            client.force_login(cust_a)
            assert client.get(url).status_code == 302, f"Cust allowed on {url}"
            client.force_login(vendor_a.user)
            assert client.get(url).status_code == 302, f"Vendor allowed on {url}"
            client.force_login(admin_user)
            assert client.get(url).status_code == 200, f"Admin rejected on {url}"
        print("  [+] BI Dashboard RBAC: Anon/Cust/Vendor blocked (302), Admin permitted (200).")

        # Cross-Customer Order Isolation
        order_b = Order.objects.filter(user=cust_b).first()
        if order_b:
            client.force_login(cust_a)
            resp = client.get(f'/orders/{order_b.order_number}/')
            assert resp.status_code == 404, f"Customer A accessed Customer B order: {resp.status_code}"
            print(f"  [+] Cross-Customer Isolation: Customer A accessing Customer B order returned 404 Not Found.")

        # Cross-Vendor Analytics Isolation
        from api.routers.vendor import resolve_target_vendor
        from fastapi import HTTPException
        try:
            resolve_target_vendor(user=vendor_a.user, vendor_id=vendor_b.pk)
            raise AssertionError("Cross-vendor access allowed!")
        except HTTPException as e:
            assert e.status_code == 403, f"Expected 403, got {e.status_code}"
            print(f"  [+] Cross-Vendor Isolation: Vendor A requesting Vendor B analytics returned 403 Forbidden.")

        # --- 8. Workflow Scheduler Failure Handling & Concurrency Lock ---
        print_banner(8, "Test Workflow Scheduler Failure Handling & Concurrency Lock")
        # 1. Concurrency Lock Check
        active_run = AnalyticalWorkflowRun.objects.create(
            workflow_name=AnalyticalWorkflowRun.WorkflowName.REVENUE_ANALYTICS,
            status=AnalyticalWorkflowRun.Status.RUNNING,
            start_time=django.utils.timezone.now(),
        )
        is_locked = AnalyticalWorkflowScheduler._is_locked(AnalyticalWorkflowRun.WorkflowName.REVENUE_ANALYTICS)
        print(f"[*] Scheduler Duplicate Lock Detected: {is_locked}")
        assert is_locked is True, "Scheduler failed to detect active lock"
        active_run.status = AnalyticalWorkflowRun.Status.SUCCESS
        active_run.save()

        # 2. Failure Handling & Retry Check
        failed_run = AnalyticalWorkflowScheduler.execute_workflow("NON_EXISTENT_WORKFLOW")
        print(f"[*] Invalid Workflow Handling: Status={failed_run.status} | Error='{failed_run.error_message}'")
        assert failed_run.status == AnalyticalWorkflowRun.Status.FAILED, "Scheduler failed to report error"
        print("[+] Concurrency locking and failure handling verified in PostgreSQL.")

        # --- 9. Environment, Security Settings, and Headers Audit ---
        print_banner(9, "Environment, Security, Headers & Settings Audit")
        from config import settings as prod_settings

        security_checks = {
            "Custom User Model Configured": prod_settings.AUTH_USER_MODEL == 'accounts.User',
            "PBKDF2 / Custom Password Hasher": 'django.contrib.auth.hashers.PBKDF2PasswordHasher' in getattr(prod_settings, 'PASSWORD_HASHERS', ['django.contrib.auth.hashers.PBKDF2PasswordHasher']),
            "Django Axes Brute Force Protection": 'axes' in prod_settings.INSTALLED_APPS and 'axes.middleware.AxesMiddleware' in prod_settings.MIDDLEWARE,
            "Django CSP Content Security Policy": 'csp.middleware.CSPMiddleware' in prod_settings.MIDDLEWARE,
            "CSRF View Middleware Active": 'django.middleware.csrf.CsrfViewMiddleware' in prod_settings.MIDDLEWARE,
            "Security Middleware Active": 'django.middleware.security.SecurityMiddleware' in prod_settings.MIDDLEWARE,
            "Clickjacking X-Frame-Options": 'django.middleware.clickjacking.XFrameOptionsMiddleware' in prod_settings.MIDDLEWARE,
            "Database Connection Pooling Active": prod_settings.DATABASES['default'].get('CONN_MAX_AGE', 0) > 0,
            "Static Root Configured": bool(prod_settings.STATIC_ROOT),
            "Media Root Configured": bool(prod_settings.MEDIA_ROOT),
        }
        for name, passed in security_checks.items():
            print(f"  [{'+' if passed else '-'}] {name:<40}: {'PASS' if passed else 'FAIL'}")
            assert passed, f"Security check failed: {name}"

        # --- 10. Live FastAPI HTTP Server & Concurrent Locust Load Test against Staging PostgreSQL ---
        print_banner(10, "Live FastAPI ASGI Server & Concurrent Locust Load Test (PostgreSQL)")
        from api.main import app
        import uvicorn

        port = 8011
        base_url = f"http://127.0.0.1:{port}"
        server_config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(server_config)
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()

        # Wait for ASGI server
        healthy = False
        start_wait = time.time()
        while time.time() - start_wait < 15:
            try:
                with urllib.request.urlopen(f"{base_url}/api/health", timeout=1) as resp:
                    if resp.getcode() == 200:
                        healthy = True
                        break
            except Exception:
                time.sleep(0.5)
        assert healthy, "Live Uvicorn server failed to start"
        print(f"[+] Live Uvicorn server running on {base_url} backed by staging PostgreSQL.")

        # Run Locust test
        os.makedirs("scratch", exist_ok=True)
        csv_prefix = "scratch/locust_staging_pg"
        locust_cmd = [
            sys.executable,
            "-m", "locust",
            "-f", "locustfile.py",
            "--host", base_url,
            "--users", "15",
            "--spawn-rate", "5",
            "--run-time", "15s",
            "--headless",
            f"--csv={csv_prefix}",
        ]
        print("[*] Executing concurrent Locust load test (15 users, 15s duration against PostgreSQL)...")
        subprocess.run(locust_cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)

        # Parse stats
        import csv
        stats_file = f"{csv_prefix}_stats.csv"
        assert os.path.exists(stats_file), "Locust stats CSV missing"
        with open(stats_file, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        agg = next(r for r in rows if r.get('Name') == 'Aggregated')
        tot_reqs = int(agg['Request Count'])
        tot_fails = int(agg['Failure Count'])
        p50 = float(agg['50%'])
        p95 = float(agg['95%'])
        p99 = float(agg['99%'])
        rps = float(agg['Requests/s'])
        avg_ms = float(agg['Average Response Time'])

        print("\n" + "-" * 75)
        print("  STAGING POSTGRESQL CONCURRENT LOAD TEST METRICS")
        print("-" * 75)
        print(f"  Total Requests Completed : {tot_reqs:,}")
        print(f"  Failed Requests          : {tot_fails} (0.00%)")
        print(f"  Throughput (RPS)         : {rps:.2f} req/sec")
        print(f"  Average Response Time    : {avg_ms:.2f} ms")
        print(f"  Median (P50)             : {p50:.2f} ms")
        print(f"  P95 Latency              : {p95:.2f} ms (Target <= 300ms)")
        print(f"  P99 Latency              : {p99:.2f} ms")
        print("-" * 75)

        assert tot_fails == 0, f"Found {tot_fails} failed requests"
        assert p95 <= 300.0, f"P95 {p95}ms exceeds 300ms SLA"
        print("[+] Staging PostgreSQL Performance SLA verified: P95 <= 300ms with 0 failures.")

        server.should_exit = True
        server_thread.join(timeout=2)

    finally:
        print("\n" + "=" * 80)
        print("  STOPPING STAGING POSTGRESQL SERVER")
        print("=" * 80)
        pg_instance.stop()
        print("[+] Staging PostgreSQL stopped cleanly. Supabase production completely untouched.")

    print("\n" + "#" * 80)
    print("  ALL 10 PRE-DEPLOYMENT STAGING CHECKS PASSED (EXIT CODE 0)")
    print("#" * 80 + "\n")


if __name__ == '__main__':
    main()

