"""
Longer Concurrent Locust Load Testing Benchmark against live Uvicorn ASGI server.
Parameters:
- Users: 20 concurrent
- Spawn rate: 5 users/sec
- Duration: 25 seconds
- Target: P95 <= 300ms, 0 failures.
"""

import os
import sys
import time
import threading
import subprocess
import csv
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_test')
import django
django.setup()

import uvicorn
from api.main import app
from accounts.models import User


def ensure_test_accounts():
    admin, _ = User.objects.get_or_create(
        email='admin@shopsense.com',
        defaults={'role': User.Role.ADMIN, 'is_staff': True, 'is_superuser': True, 'is_active': True},
    )
    if not admin.is_staff or not admin.is_superuser:
        admin.role = User.Role.ADMIN
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()


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
        # Wait for server health
        start_wait = time.time()
        healthy = False
        while time.time() - start_wait < 15:
            try:
                with urllib.request.urlopen(f"{base_url}/api/health", timeout=1) as resp:
                    if resp.getcode() == 200:
                        healthy = True
                        break
            except Exception:
                time.sleep(0.5)

        if not healthy:
            print("[!] Error: Live Uvicorn server failed to respond.")
            return 1

        print("[+] Live Uvicorn server is HEALTHY.")
        os.makedirs("scratch", exist_ok=True)
        csv_prefix = "scratch/locust_long"

        users = 20
        spawn_rate = 5
        duration = "25s"

        locust_cmd = [
            sys.executable,
            "-m",
            "locust",
            "-f",
            "locustfile.py",
            "--host",
            base_url,
            "--users",
            str(users),
            "--spawn-rate",
            str(spawn_rate),
            "--run-time",
            duration,
            "--headless",
            f"--csv={csv_prefix}",
        ]

        print(f"[*] Executing extended Locust load test: {users} concurrent users, spawn rate {spawn_rate}, duration {duration}...")
        subprocess.run(locust_cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)

        stats_csv = os.path.join(PROJECT_ROOT, f"{csv_prefix}_stats.csv")
        if not os.path.exists(stats_csv):
            print("[!] Stats CSV not found!")
            return 1

        with open(stats_csv, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        print("\n" + "=" * 80)
        print("  EXTENDED LOCUST CONCURRENT LOAD TEST RESULTS (LIVE ASGI SERVER)")
        print("=" * 80)
        print(f"{'ENDPOINT':<45} | {'REQS':<6} | {'FAIL':<5} | {'AVG(ms)':<8} | {'P50':<5} | {'P95':<5} | {'P99':<5}")
        print("-" * 80)

        agg = None
        for r in rows:
            name = r.get('Name', '')
            reqs = int(r.get('Request Count', 0))
            fails = int(r.get('Failure Count', 0))
            avg_ms = float(r.get('Average Response Time', 0.0))
            p50 = float(r.get('50%', 0.0))
            p95 = float(r.get('95%', 0.0))
            p99 = float(r.get('99%', 0.0))

            if name == 'Aggregated':
                agg = r
            else:
                print(f"{name:<45} | {reqs:<6} | {fails:<5} | {avg_ms:<8.2f} | {p50:<5.1f} | {p95:<5.1f} | {p99:<5.1f}")

        print("=" * 80)
        if agg:
            tot_reqs = int(agg.get('Request Count', 0))
            tot_fails = int(agg.get('Failure Count', 0))
            tot_avg = float(agg.get('Average Response Time', 0.0))
            tot_p50 = float(agg.get('50%', 0.0))
            tot_p95 = float(agg.get('95%', 0.0))
            tot_p99 = float(agg.get('99%', 0.0))
            tot_rps = float(agg.get('Requests/s', 0.0))

            print(f"AGGREGATED SUMMARY:")
            print(f"  Concurrent Users  : {users}")
            print(f"  Duration          : {duration}")
            print(f"  Total Requests    : {tot_reqs:,}")
            print(f"  Failed Requests   : {tot_fails} ({tot_fails / max(1, tot_reqs) * 100:.2f}%)")
            print(f"  Throughput (RPS)  : {tot_rps:.2f} req/sec")
            print(f"  Average Latency   : {tot_avg:.2f} ms")
            print(f"  Median (P50)      : {tot_p50:.2f} ms")
            print(f"  P95 Latency       : {tot_p95:.2f} ms (Target <= 300ms)")
            print(f"  P99 Latency       : {tot_p99:.2f} ms")
            print("=" * 80)

            assert tot_fails == 0, f"Found {tot_fails} failed requests"
            assert tot_p95 <= 300.0, f"P95 {tot_p95}ms exceeds 300ms SLA"
            print("[+] Performance SLA verified: P95 <= 300ms with 0 failures under extended load.")
            return 0
        return 1

    finally:
        print("\n[*] Stopping live Uvicorn server...")
        server.should_exit = True
        server_thread.join(timeout=2)
        print("[+] Live server stopped cleanly.")


if __name__ == '__main__':
    sys.exit(main())

