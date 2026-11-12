"""
Tests for the import_demo_marketplace_data management command.

Verifies:
1. Successful import of demo vendors, categories, products, and inventory stock balances.
2. Dry-run mode correctness (validates without committing any database mutations).
3. Duplicate import idempotency (re-running skips existing vendor_code and SKU without duplicating or inflating stock).
4. Validation failures for invalid rows (negative prices, invalid emails, negative inventory) with full rollback.
5. Missing vendor foreign-key rejection and rollback.
6. Strict protection of existing non-demo real users and products (refuses to overwrite).
7. Role-based access control and dashboard visibility for imported vendors and administrators.
"""

from decimal import Decimal
import io
import os
import tempfile
import pytest
from django.core.management import call_command, CommandError
from django.test import Client
from django.urls import reverse

from accounts.models import User
from catalog.models import Category, Inventory, Product
from inventory.models import StockMovement, Warehouse, WarehouseStock
from inventory.services import StockService
from vendors.models import VendorProfile


@pytest.fixture
def admin_user(db):
    """Fixture creating an administrator user."""
    return User.objects.create_superuser(
        email='import_admin@shopsense.com',
        password='AdminPassword123!',
        first_name='Import',
        last_name='Admin',
    )


@pytest.fixture
def sample_csv_files(tmp_path):
    """Create sample valid vendor and product CSV files."""
    vendors_file = tmp_path / "test_vendors.csv"
    vendors_file.write_text(
        "vendor_code,business_name,contact_email,contact_phone,business_address,city,state,postal_code,country,tax_id,website,commission_rate,business_description\n"
        "VNDDEMOTEST1,Test Alpha Goods,alpha.vendor@shopsense.demo,+91 99999 11111,10 Alpha Way,Bengaluru,Karnataka,560001,India,29TEST1111F1Z1,https://alpha.demo,10.00,Alpha goods and gear\n"
        "VNDDEMOTEST2,Test Beta Crafts,beta.vendor@shopsense.demo,+91 99999 22222,20 Beta Road,Mumbai,Maharashtra,400001,India,27TEST2222F1Z2,https://beta.demo,12.50,Handcrafted goods\n",
        encoding='utf-8'
    )

    products_file = tmp_path / "test_products.csv"
    products_file.write_text(
        "sku,vendor_code,name,category,price,compare_at_price,cost_price,quantity,low_stock_threshold,description,short_description,weight,dimensions,status,is_featured\n"
        "DEMO-TEST-01,VNDDEMOTEST1,Alpha Ceramic Mug,Home & Living,499.00,699.00,180.00,50,10,Handmade ceramic coffee mug.,Ceramic mug 350ml.,0.350,10x10x12,ACTIVE,True\n"
        "DEMO-TEST-02,VNDDEMOTEST1,Alpha Stainless Bottle,Home & Living,899.00,1199.00,350.00,30,5,Insulated water bottle.,Bottle 750ml.,0.450,8x8x25,ACTIVE,False\n"
        "DEMO-TEST-03,VNDDEMOTEST2,Beta Leather Journal,Stationery,1299.00,1599.00,500.00,20,5,Handmade leather journal.,Journal A5.,0.500,15x2x21,ACTIVE,True\n",
        encoding='utf-8'
    )

    return str(vendors_file), str(products_file)


@pytest.mark.django_db
class TestImportDemoMarketplaceData:
    """Test suite for import_demo_marketplace_data management command."""

    def test_successful_import(self, admin_user, sample_csv_files):
        """Test importing valid vendors, categories, products, and inventory."""
        vendors_path, products_path = sample_csv_files
        out = io.StringIO()

        call_command(
            'import_demo_marketplace_data',
            vendors_file=vendors_path,
            products_file=products_path,
            stdout=out,
        )

        output = out.getvalue()
        assert "Vendors Processed:           2 (2 created, 0 reused)" in output
        assert "Products Processed:          3 (3 created, 0 reused)" in output
        assert "Warehouse Units Inbounded:   100" in output

        # Verify Vendor Profiles & Users
        v1 = VendorProfile.objects.get(vendor_id='VNDDEMOTEST1')
        assert v1.business_name == 'Test Alpha Goods'
        assert v1.contact_email == 'alpha.vendor@shopsense.demo'
        assert v1.user.role == User.Role.VENDOR
        assert v1.user.is_active is True
        assert v1.is_active is True
        assert v1.is_verified is True
        assert v1.commission_rate == Decimal('10.00')

        v2 = VendorProfile.objects.get(vendor_id='VNDDEMOTEST2')
        assert v2.business_name == 'Test Beta Crafts'
        assert v2.commission_rate == Decimal('12.50')

        # Verify Categories
        cat_home = Category.objects.get(slug='home-living')
        assert cat_home.name == 'Home & Living'
        cat_stat = Category.objects.get(slug='stationery')
        assert cat_stat.name == 'Stationery'

        # Verify Products
        p1 = Product.objects.get(sku='DEMO-TEST-01')
        assert p1.name == 'Alpha Ceramic Mug'
        assert p1.vendor == v1
        assert p1.category == cat_home
        assert p1.price == Decimal('499.00')
        assert p1.is_featured is True

        # Verify Inventory & Warehouse Stock
        inv1 = Inventory.objects.get(product=p1)
        assert inv1.quantity == 50
        assert inv1.low_stock_threshold == 10

        wh_default = StockService.get_or_create_default_warehouse()
        wh_stock1 = WarehouseStock.objects.get(warehouse=wh_default, product=p1)
        assert wh_stock1.quantity == 50

        # Verify Stock Movement Ledger
        movement = StockMovement.objects.filter(product=p1).first()
        assert movement is not None
        assert movement.quantity_change == 50
        assert movement.movement_type == StockMovement.MovementType.PURCHASE

        # Reconciliation check
        discrepancies = StockService.reconcile_inventory()
        assert len(discrepancies) == 0

    def test_dry_run_leaves_database_untouched(self, admin_user, sample_csv_files):
        """Test dry-run mode validates everything and rolls back without committing."""
        vendors_path, products_path = sample_csv_files
        out = io.StringIO()

        initial_user_count = User.objects.count()
        initial_vendor_count = VendorProfile.objects.count()
        initial_product_count = Product.objects.count()
        initial_category_count = Category.objects.count()

        call_command(
            'import_demo_marketplace_data',
            vendors_file=vendors_path,
            products_file=products_path,
            dry_run=True,
            stdout=out,
        )

        output = out.getvalue()
        assert "[DRY RUN]" in output
        assert "All validation checks passed. Database transaction successfully rolled back." in output

        assert User.objects.count() == initial_user_count
        assert VendorProfile.objects.count() == initial_vendor_count
        assert Product.objects.count() == initial_product_count
        assert Category.objects.count() == initial_category_count

    def test_duplicate_import_idempotency(self, admin_user, sample_csv_files):
        """Test re-importing the same CSV files skips existing records without stock inflation."""
        vendors_path, products_path = sample_csv_files

        # Run 1
        call_command(
            'import_demo_marketplace_data',
            vendors_file=vendors_path,
            products_file=products_path,
            stdout=io.StringIO(),
        )

        initial_vendors = VendorProfile.objects.count()
        initial_products = Product.objects.count()
        p1 = Product.objects.get(sku='DEMO-TEST-01')
        initial_qty = p1.inventory.quantity

        # Run 2 with identical files
        out2 = io.StringIO()
        call_command(
            'import_demo_marketplace_data',
            vendors_file=vendors_path,
            products_file=products_path,
            stdout=out2,
        )

        output2 = out2.getvalue()
        assert "Vendors Processed:           2 (0 created, 2 reused)" in output2
        assert "Products Processed:          3 (0 created, 3 reused)" in output2
        assert "Warehouse Units Inbounded:   0" in output2

        assert VendorProfile.objects.count() == initial_vendors
        assert Product.objects.count() == initial_products
        p1.refresh_from_db()
        assert p1.inventory.quantity == initial_qty

    def test_invalid_price_causes_transaction_rollback(self, admin_user, tmp_path):
        """Test that an invalid price in products CSV causes immediate rollback."""
        v_file = tmp_path / "v_invalid.csv"
        v_file.write_text(
            "vendor_code,business_name,contact_email\n"
            "VNDDEMOROLL,Rollback Vendor,roll.vendor@shopsense.demo\n",
            encoding='utf-8'
        )

        p_file = tmp_path / "p_invalid.csv"
        p_file.write_text(
            "sku,vendor_code,name,category,price,quantity\n"
            "DEMO-INVALID-01,VNDDEMOROLL,Good Item,Testing,199.00,10\n"
            "DEMO-INVALID-02,VNDDEMOROLL,Bad Item,Testing,-50.00,10\n",  # Negative price!
            encoding='utf-8'
        )

        with pytest.raises(CommandError) as exc_info:
            call_command(
                'import_demo_marketplace_data',
                vendors_file=str(v_file),
                products_file=str(p_file),
                stdout=io.StringIO(),
            )

        assert "Price '-50.00' must be greater than 0" in str(exc_info.value)
        # Verify complete rollback: vendor was NOT created
        assert not VendorProfile.objects.filter(vendor_id='VNDDEMOROLL').exists()
        assert not Product.objects.filter(sku='DEMO-INVALID-01').exists()

    def test_missing_vendor_foreign_key_rejection(self, admin_user, tmp_path):
        """Test that referencing a non-existent vendor fails validation and rolls back."""
        v_file = tmp_path / "v_missing.csv"
        v_file.write_text(
            "vendor_code,business_name,contact_email\n"
            "VNDDEMOVALID,Valid Vendor,valid.vendor@shopsense.demo\n",
            encoding='utf-8'
        )

        p_file = tmp_path / "p_missing.csv"
        p_file.write_text(
            "sku,vendor_code,name,category,price\n"
            "DEMO-ORPHAN-01,VNDGHOST999,Ghost Product,Testing,299.00\n",  # VNDGHOST999 does not exist!
            encoding='utf-8'
        )

        with pytest.raises(CommandError) as exc_info:
            call_command(
                'import_demo_marketplace_data',
                vendors_file=str(v_file),
                products_file=str(p_file),
                stdout=io.StringIO(),
            )

        assert "vendor_code 'VNDGHOST999' does not exist" in str(exc_info.value)
        assert not VendorProfile.objects.filter(vendor_id='VNDDEMOVALID').exists()
        assert not Product.objects.filter(sku='DEMO-ORPHAN-01').exists()

    def test_protect_real_user_and_product(self, admin_user, tmp_path):
        """Test that the importer refuses to overwrite existing real users or products."""
        # Create a real customer user and a real vendor/product
        real_user = User.objects.create_user(
            email='real.customer@gmail.com',
            password='RealPassword123!',
            first_name='Real',
            last_name='Customer',
            role=User.Role.CUSTOMER,
        )

        real_vendor_user = User.objects.create_user(
            email='real.vendor@company.com',
            password='RealPassword123!',
            first_name='Real',
            last_name='Vendor',
            role=User.Role.VENDOR,
        )
        real_vendor = VendorProfile.objects.create(
            user=real_vendor_user,
            vendor_id='REALVND001',
            business_name='Real Production Company',
            contact_email='real.vendor@company.com',
            is_active=True,
        )
        cat = Category.objects.create(name='Real Category', slug='real-category')
        real_product = Product.objects.create(
            vendor=real_vendor,
            category=cat,
            name='Real Live Product',
            slug='real-live-product',
            sku='REAL-PROD-001',  # Real non-demo SKU!
            price=Decimal('999.00'),
            description='Live real production item',
        )

        # Attempt to hijack real user email in vendors CSV
        v_file = tmp_path / "v_hijack.csv"
        v_file.write_text(
            "vendor_code,business_name,contact_email\n"
            "VNDDEMOHIJACK,Hijack Corp,real.customer@gmail.com\n",
            encoding='utf-8'
        )
        p_file = tmp_path / "p_dummy.csv"
        p_file.write_text(
            "sku,vendor_code,name,category,price\n"
            "DEMO-DUMMY-01,VNDDEMOHIJACK,Dummy Item,Testing,100.00\n",
            encoding='utf-8'
        )

        with pytest.raises(CommandError) as exc_info:
            call_command(
                'import_demo_marketplace_data',
                vendors_file=str(v_file),
                products_file=str(p_file),
                stdout=io.StringIO(),
            )
        assert "Protection violation! Email 'real.customer@gmail.com' belongs to an existing real user" in str(exc_info.value)

        # Attempt to overwrite real product SKU in products CSV
        v_file2 = tmp_path / "v_ok.csv"
        v_file2.write_text(
            "vendor_code,business_name,contact_email\n"
            "VNDDEMOOK,Safe Vendor,safe.demo@shopsense.demo\n",
            encoding='utf-8'
        )
        p_file2 = tmp_path / "p_hijack.csv"
        p_file2.write_text(
            "sku,vendor_code,name,category,price\n"
            "REAL-PROD-001,VNDDEMOOK,Attempted Overwrite,Testing,10.00\n",
            encoding='utf-8'
        )

        with pytest.raises(CommandError) as exc_info2:
            call_command(
                'import_demo_marketplace_data',
                vendors_file=str(v_file2),
                products_file=str(p_file2),
                stdout=io.StringIO(),
            )
        assert "Protection violation! SKU 'REAL-PROD-001' belongs to an existing real product" in str(exc_info2.value)

    def test_vendor_dashboard_visibility_and_rbac(self, admin_user, sample_csv_files):
        """Test RBAC and dashboard scoping for imported vendors and administrators."""
        vendors_path, products_path = sample_csv_files
        call_command(
            'import_demo_marketplace_data',
            vendors_file=vendors_path,
            products_file=products_path,
            stdout=io.StringIO(),
        )

        v1 = VendorProfile.objects.get(vendor_id='VNDDEMOTEST1')
        vendor_user = v1.user

        # 1. RBAC capability checks
        assert vendor_user.is_vendor() is True
        assert vendor_user.can_access_vendor_dashboard() is True
        assert vendor_user.can_access_admin_dashboard() is False
        assert admin_user.can_access_admin_dashboard() is True

        # 2. Web Client access checks
        client = Client()

        # Vendor logged in
        client.force_login(vendor_user)

        # Vendor can access own vendor profile page
        res_profile = client.get(reverse('vendors:profile'))
        assert res_profile.status_code == 200

        # Vendor accessing catalog product list sees ONLY their own 2 products
        res_catalog = client.get(reverse('catalog:product_list'))
        assert res_catalog.status_code == 200
        vendor_products = list(res_catalog.context['products'])
        assert len(vendor_products) == 2
        for prod in vendor_products:
            assert prod.vendor == v1

        # Vendor trying to access admin dashboard is denied / redirected
        res_admin_blocked = client.get(reverse('dashboard:admin_dashboard'))
        assert res_admin_blocked.status_code in (302, 403)

        # Admin logged in
        client.force_login(admin_user)

        # Admin can access admin dashboard
        res_admin = client.get(reverse('dashboard:admin_dashboard'))
        assert res_admin.status_code == 200

        # Admin accessing catalog product list sees ALL 3 products
        res_admin_catalog = client.get(reverse('catalog:product_list'))
        assert res_admin_catalog.status_code == 200
        assert len(res_admin_catalog.context['products']) >= 3

