"""
Tests for PDF & Excel Report Export Services and Endpoints (Module 6).
Validates:
1. ReportLab PDF Generation for all 6 reports (Header, NumberedCanvas footer, Table formatting).
2. OpenPyXL / Pandas Excel Multi-sheet Workbook Generation (Headers, Frozen panes, Autofilter).
3. Export view endpoints (Authentication, RBAC, HTTP headers, MIME types, Attachment filenames).
"""

import io
import pytest
from django.urls import reverse
from decimal import Decimal
import openpyxl

from accounts.models import User
from catalog.models import Category, Inventory, Product
from orders.models import Order, OrderItem
from vendors.models import VendorProfile
from inventory.services.export_services import (
    PDFReportGenerator,
    ExcelReportGenerator,
)


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        email='export_admin@example.com',
        password='TestPassword123!',
    )


@pytest.fixture
def customer_user(db):
    return User.objects.create_user(
        email='export_cust@example.com',
        password='TestPassword123!',
        role=User.Role.CUSTOMER,
    )


@pytest.fixture
def setup_export_data(db, admin_user, customer_user):
    vendor_user = User.objects.create_user(
        email='export_vendor@example.com',
        password='TestPassword123!',
        role=User.Role.VENDOR,
    )
    vendor = VendorProfile.objects.create(
        user=vendor_user,
        vendor_id='VND-EXP-001',
        business_name='Export Mega Store',
        contact_email=vendor_user.email,
        is_active=True,
    )
    cat = Category.objects.create(name='Electronics', slug='electronics')
    prod = Product.objects.create(
        vendor=vendor,
        category=cat,
        name='Export Pro Laptop',
        slug='export-pro-laptop',
        sku='EXP-LAP-100',
        price=Decimal('50000.00'),
        status=Product.Status.ACTIVE,
    )
    Inventory.objects.create(product=prod, quantity=25, low_stock_threshold=5)
    order = Order.objects.create(
        user=customer_user,
        order_number='ORD-EXP-2026',
        status=Order.Status.DELIVERED,
        subtotal=Decimal('50000.00'),
        total=Decimal('50000.00'),
    )
    OrderItem.objects.create(
        order=order,
        product=prod,
        vendor=vendor,
        product_name=prod.name,
        product_sku=prod.sku,
        quantity=1,
        unit_price=Decimal('50000.00'),
        total_price=Decimal('50000.00'),
        status=OrderItem.Status.DELIVERED,
    )
    return {'product': prod, 'order': order}


@pytest.mark.django_db
class TestPDFReportGenerator:
    """Test PDF generation for all 6 analytical reports."""

    def test_revenue_report_generation(self, setup_export_data):
        pdf_bytes = PDFReportGenerator.generate_revenue_report()
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b'%PDF')

    def test_sales_performance_report_generation(self, setup_export_data):
        pdf_bytes = PDFReportGenerator.generate_sales_performance_report()
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b'%PDF')

    def test_inventory_report_generation(self, setup_export_data):
        pdf_bytes = PDFReportGenerator.generate_inventory_report()
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b'%PDF')

    def test_customer_intelligence_report_generation(self, setup_export_data):
        pdf_bytes = PDFReportGenerator.generate_customer_intelligence_report()
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b'%PDF')

    def test_forecasting_report_generation(self, setup_export_data):
        pdf_bytes = PDFReportGenerator.generate_forecasting_report()
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b'%PDF')

    def test_marketplace_report_generation(self, setup_export_data):
        pdf_bytes = PDFReportGenerator.generate_marketplace_report()
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b'%PDF')

    def test_pdf_dispatcher_unknown_type_defaults(self, setup_export_data):
        pdf_bytes = PDFReportGenerator.generate_pdf_report('unknown_type')
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b'%PDF')


@pytest.mark.django_db
class TestExcelReportGenerator:
    """Test multi-sheet Excel workbook export."""

    def test_comprehensive_bi_workbook_generation(self, setup_export_data):
        excel_bytes = ExcelReportGenerator.generate_comprehensive_bi_workbook()
        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 2000

        # Load back with openpyxl to verify sheets & format
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
        sheet_names = wb.sheetnames
        assert "Executive Summary" in sheet_names
        assert "Revenue Overview" in sheet_names
        assert "Sales Performance" in sheet_names
        assert "Inventory Analytics" in sheet_names
        assert "Customer Intelligence" in sheet_names
        assert "Marketplace Performance" in sheet_names

        # Verify frozen panes and autofilter
        ws_rev = wb["Revenue Overview"]
        assert ws_rev.freeze_panes == "A5"
        assert ws_rev.auto_filter.ref is not None


@pytest.mark.django_db
class TestReportExportViews:
    """Test HTTP export views."""

    def test_export_pdf_requires_admin(self, client, customer_user):
        client.force_login(customer_user)
        url = reverse('dashboard:bi_export_pdf')
        response = client.get(url)
        assert response.status_code == 302
        assert '/accounts/login/' in response.url

    def test_export_excel_requires_admin(self, client, customer_user):
        client.force_login(customer_user)
        url = reverse('dashboard:bi_export_excel')
        response = client.get(url)
        assert response.status_code == 302
        assert '/accounts/login/' in response.url

    def test_export_pdf_success(self, client, admin_user, setup_export_data):
        client.force_login(admin_user)
        url = reverse('dashboard:bi_export_pdf') + '?report_type=revenue'
        response = client.get(url)

        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'
        assert 'attachment; filename=' in response['Content-Disposition']
        assert response.content.startswith(b'%PDF')

    def test_export_excel_success(self, client, admin_user, setup_export_data):
        client.force_login(admin_user)
        url = reverse('dashboard:bi_export_excel')
        response = client.get(url)

        assert response.status_code == 200
        assert response['Content-Type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        assert 'attachment; filename=' in response['Content-Disposition']
        assert len(response.content) > 1000
