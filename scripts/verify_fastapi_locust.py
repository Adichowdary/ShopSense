"""
Automated verification script for FastAPI & Locust Load Testing (Module 10).
1. Ensures test database contains an active Admin and Customer account.
2. Starts the live Uvicorn ASGI server hosting `api.main:app` in a managed background thread.
3. Performs live HTTP tests validating 401, 403, and 200 responses across all endpoints.
4. Executes Locust load test with concurrent users and records real HTTP latency percentiles.
5. Shuts down server cleanly and displays the audit results.
"""

import os
import sys
import time
import threading
import subprocess
import json
import urllib.request
import urllib.error

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Ensure Django settings are configured for test SQLite
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_test')
import django
django.setup()

import uvicorn
from api.main import app
from accounts.models import User
from vendors.models import VendorProfile


def ensure_test_accounts():
    """Ensure admin and customer exist for HTTP tests."""
    admin, _ = User.objects.get_or_create(
        email='admin@shopsense.com',
        defaults={'role': User.Role.ADMIN, 'is_staff': True, 'is_superuser': True, 'is_active': True},
    )
    if not admin.is_staff or not admin.is_superuser:
        admin.role = User.Role.ADMIN
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()

    cust, _ = User.objects.get_or_create(
        email='customer@shopsense.com',
        defaults={'role': User.Role.CUSTOMER, 'is_active': True},
    )


def test_http_endpoint(url, headers=None):
    """Perform a real HTTP request and assert status code."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.getcode()
            body = resp.read().decode('utf-8')
            return status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')


def main():
    ensure_test_accounts()

    port = 8009
    base_url = f"http://127.0.0.1:{port}"

    print(f"[*] Starting live Uvicorn server on {base_url} in managed thread...")
    server_config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(server_config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    try:
        # Wait for server to boot
        max_wait = 15
        start_wait = time.time()
        healthy = False

        while time.time() - start_wait < max_wait:
            try:
                with urllib.request.urlopen(f"{base_url}/api/health", timeout=1) as resp:
                    if resp.getcode() == 200:
                        healthy = True
                        break
            except Exception:
                time.sleep(0.5)

        if not healthy:
            print("[!] Error: Live Uvicorn server failed to become healthy within 15 seconds.")
            return 1

        print("[+] Live Uvicorn server is HEALTHY and listening.")

        # --- Phase 1: Real HTTP Endpoint Verification ---
        print("\n--- PHASE 1: HTTP Endpoint & RBAC Verification ---")
        admin_headers = {
            "Authorization": "Bearer admin@shopsense.com",
            "X-User-Email": "admin@shopsense.com",
            "Accept": "application/json",
        }
        cust_headers = {
            "Authorization": "Bearer customer@shopsense.com",
            "X-User-Email": "customer@shopsense.com",
            "Accept": "application/json",
        }

        # 1. Unauthenticated request -> expect 401
        status, _ = test_http_endpoint(f"{base_url}/api/v1/analytics/revenue/daily")
        print(f"  GET /revenue/daily (Anonymous): Status {status} (Expected 401) -> {'PASS' if status == 401 else 'FAIL'}")
        assert status == 401, f"Expected 401, got {status}"

        # 2. Customer user on admin revenue endpoint -> expect 403
        status, _ = test_http_endpoint(f"{base_url}/api/v1/analytics/revenue/daily", headers=cust_headers)
        print(f"  GET /revenue/daily (Customer):  Status {status} (Expected 403) -> {'PASS' if status == 403 else 'FAIL'}")
        assert status == 403, f"Expected 403, got {status}"

        # 3. Admin requests across all 6 analytical endpoints -> expect 200
        endpoints = [
            ("/api/v1/analytics/revenue/daily?days=30", "Revenue Daily"),
            ("/api/v1/analytics/revenue/monthly?months_in_days=180", "Revenue Monthly"),
            ("/api/v1/analytics/vendor/summary", "Vendor Summary"),
            ("/api/v1/analytics/forecast/demand", "Forecast Demand"),
            ("/api/v1/analytics/customers/segments", "Customer Segments"),
            ("/api/v1/analytics/recommendations/popular?limit=5", "Popular Recommendations"),
            ("/api/v1/analytics/benchmarking/marketplace", "Marketplace Benchmarking"),
        ]

        for path, name in endpoints:
            status, body = test_http_endpoint(f"{base_url}{path}", headers=admin_headers)
            print(f"  GET {name:<25}: Status {status} (Expected 200) -> {'PASS' if status == 200 else 'FAIL'}")
            assert status == 200, f"Expected 200 for {name}, got {status}: {body}"

        # --- Phase 2: Live Locust Load Testing ---
        print("\n--- PHASE 2: Real Locust Concurrent Load Testing ---")
        os.makedirs("scratch", exist_ok=True)
        csv_prefix = "scratch/locust_audit"

        locust_cmd = [
            sys.executable,
            "-m",
            "locust",
            "-f",
            "locustfile.py",
            "--host",
            base_url,
            "--users",
            "15",
            "--spawn-rate",
            "5",
            "--run-time",
            "10s",
            "--headless",
            f"--csv={csv_prefix}",
        ]

        print(f"[*] Executing Locust load test: 15 concurrent users, spawn rate 5, duration 10s...")
        loc_res = subprocess.run(locust_cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)

        # Parse CSV stats
        stats_csv = os.path.join(PROJECT_ROOT, f"{csv_prefix}_stats.csv")
        if os.path.exists(stats_csv):
            import csv
            with open(stats_csv, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                agg_row = [r for r in rows if r.get('Name') == 'Aggregated']
                if agg_row:
                    agg = agg_row[0]
                    total_reqs = int(agg.get('Request Count', 0))
                    failures = int(agg.get('Failure Count', 0))
                    median_ms = float(agg.get('50%', 0.0))
                    p95_ms = float(agg.get('95%', 0.0))
                    p99_ms = float(agg.get('99%', 0.0))
                    avg_ms = float(agg.get('Average Response Time', 0.0))
                    rps = float(agg.get('Requests/s', 0.0))
                    fail_ratio = (failures / max(1, total_reqs)) * 100.0

                    print("\n==================================================================")
                    print("  REAL LOCUST HTTP LOAD TEST RESULTS (LIVE ASGI SERVER)")
                    print("==================================================================")
                    print(f"  Total HTTP Requests Completed: {total_reqs:,}")
                    print(f"  Failed Requests:               {failures} ({fail_ratio:.2f}%)")
                    print(f"  Throughput (RPS):              {rps:.2f} req/sec")
                    print(f"  Average Response Time:         {avg_ms:.2f} ms")
                    print(f"  Median (50th Percentile):      {median_ms:.2f} ms")
                    print(f"  P95 Response Time:             {p95_ms:.2f} ms (Target: <= 300ms)")
                    print(f"  P99 Response Time:             {p99_ms:.2f} ms")
                    print("==================================================================")

                    if p95_ms <= 300.0 and fail_ratio == 0.0:
                        print(f"[+] SUCCESS: P95 is {p95_ms:.2f}ms <= 300ms with 0% failure rate!")
                        return 0
                    else:
                        print(f"[!] Target criteria failed (P95={p95_ms}ms, failures={failures})")
                        return 1
        else:
            print("[!] Locust stats CSV not found. Raw output:\n", loc_res.stdout, loc_res.stderr)
            return 1

        return 0

    finally:
        print("\n[*] Stopping live Uvicorn server...")
        server.should_exit = True
        server_thread.join(timeout=2)
        print("[+] Live Uvicorn server stopped cleanly.")


if __name__ == '__main__':
    sys.exit(main())
