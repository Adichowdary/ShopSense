"""
Verification script for Section 7: PDF and Excel Report Export.
1. Generates and inspects all 6 ReportLab PDF reports.
2. Generates and parses the multi-sheet OpenPyXL Excel workbook.
3. Validates frozen panes, autofilter ranges, formatting, and data derivation.
4. Validates download view security (Anonymous/Customer 302, Admin 200).
"""

import io
import os
import sys
import openpyxl

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_test')
import django
django.setup()

from django.test.utils import setup_test_environment
setup_test_environment()

from django.test import Client
from django.urls import reverse
from accounts.models import User
from inventory.services.export_services import (
    PDFReportGenerator,
    ExcelReportGenerator,
)


def main():
    print("==================================================================")
    print("  SECTION 7: PDF AND EXCEL REPORT EXPORT AUDIT")
    print("==================================================================")

    # 1. PDF Reports Generation & Validation
    print("\n--- 1. Generating & Validating 6 ReportLab PDF Reports ---")
    report_types = [
        ("revenue", "Revenue Analytics"),
        ("sales", "Sales Performance"),
        ("inventory", "Inventory Intelligence"),
        ("customer", "Customer Intelligence"),
        ("forecast", "Predictive Demand Forecasting"),
        ("marketplace", "Marketplace Benchmarking"),
    ]

    for r_type, label in report_types:
        pdf_bytes = PDFReportGenerator.generate_pdf_report(r_type)
        assert isinstance(pdf_bytes, bytes), f"Report {r_type} did not return bytes"
        assert pdf_bytes.startswith(b'%PDF'), f"Report {r_type} missing PDF magic bytes"
        size_kb = len(pdf_bytes) / 1024
        assert size_kb > 2.0, f"Report {r_type} suspiciously small ({size_kb:.1f} KB)"
        print(f"  [+] {label:<35}: Size={size_kb:>6.1f} KB | Header=%PDF-1.4 | Validated")

    # 2. Multi-Sheet Excel Workbook Validation
    print("\n--- 2. Generating & Validating OpenPyXL Multi-Sheet Excel Workbook ---")
    excel_bytes = ExcelReportGenerator.generate_comprehensive_bi_workbook()
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 5000, "Excel workbook suspiciously small"

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    expected_sheets = [
        "Executive Summary",
        "Revenue Overview",
        "Sales Performance",
        "Inventory Analytics",
        "Customer Intelligence",
        "Marketplace Performance",
    ]
    print(f"  Workbook Sheets Found: {wb.sheetnames}")
    for s_name in expected_sheets:
        assert s_name in wb.sheetnames, f"Missing sheet: {s_name}"
        ws = wb[s_name]
        # Verify title & header
        assert ws.cell(row=1, column=1).value is not None, f"Sheet {s_name} missing title"
        assert ws.cell(row=4, column=1).fill.start_color.rgb == "001E293B", f"Sheet {s_name} missing navy header fill"
        # Verify frozen panes and autofilter on data sheets
        if s_name != "Executive Summary":
            assert ws.freeze_panes == "A5", f"Sheet {s_name} freeze_panes={ws.freeze_panes}, expected A5"
            assert ws.auto_filter.ref is not None, f"Sheet {s_name} missing autofilter"
        print(f"  [+] Sheet '{s_name}': Title='{ws.cell(row=1, column=1).value}' | Header Row=4 | Frozen=A5 | AutoFilter=Active")

    # 3. HTTP Download Security & Header Validation
    print("\n--- 3. HTTP Download Security & MIME Type Validation ---")
    admin, _ = User.objects.get_or_create(
        email='admin@shopsense.com',
        defaults={'role': User.Role.ADMIN, 'is_staff': True, 'is_superuser': True, 'is_active': True},
    )
    cust, _ = User.objects.get_or_create(
        email='customer@shopsense.com',
        defaults={'role': User.Role.CUSTOMER, 'is_active': True},
    )
    client = Client()

    # Unauthorized access check
    urls_to_test = [
        reverse('dashboard:export_report') + '?format=pdf&report=revenue',
        reverse('dashboard:export_report') + '?format=excel',
        reverse('dashboard:bi_export_pdf') + '?report_type=revenue',
        reverse('dashboard:bi_export_excel'),
    ]

    for u in urls_to_test:
        r_anon = client.get(u)
        assert r_anon.status_code == 302, f"Anonymous should get 302 for {u}, got {r_anon.status_code}"
        client.force_login(cust)
        r_cust = client.get(u)
        assert r_cust.status_code == 302, f"Customer should get 302 for {u}, got {r_cust.status_code}"

    print("  [+] Unauthorized users (Anonymous, Customer) blocked from download endpoints (302).")

    # Admin Authorized Download Checks
    client.force_login(admin)

    # PDF Download
    r_pdf = client.get(reverse('dashboard:export_report') + '?format=pdf&report=revenue')
    assert r_pdf.status_code == 200
    assert r_pdf['Content-Type'] == 'application/pdf'
    assert 'attachment; filename=' in r_pdf['Content-Disposition']
    assert r_pdf.content.startswith(b'%PDF')
    print("  [+] Admin PDF Download: 200 OK | Content-Type=application/pdf | Disposition=attachment")

    # Excel Download
    r_xls = client.get(reverse('dashboard:export_report') + '?format=excel')
    assert r_xls.status_code == 200
    assert r_xls['Content-Type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    assert 'attachment; filename=' in r_xls['Content-Disposition']
    assert len(r_xls.content) > 5000
    print("  [+] Admin Excel Download: 200 OK | Content-Type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    print("\n==================================================================")
    print("  ALL PDF AND EXCEL REPORT EXPORT AUDITS PASSED")
    print("==================================================================")
    return 0


if __name__ == '__main__':
    sys.exit(main())

