"""
Tests for the ShopSense Multi-Vendor Demo Data Generator.

Verifies:
- Creation of all 8 diverse vendor categories.
- Correct product-to-vendor and category relationships.
- Absolute inventory ledger consistency (zero reconciliation discrepancies).
- Valid order totals, line item relationships, and financial calculations.
- Idempotent repeated runs (no duplicate records, no stock inflation).
- Dry-run safety (no persistent database modifications).
- Safe cleanup of demo data while preserving non-demo application data.
- Full isolation from real external services (emails, payment gateways, shipping).
"""

from decimal import Decimal
import io
import pytest
from django.core.management import call_command
from django.core import mail
from django.db.models import Sum

from accounts.models import User
from catalog.models import Category, Inventory, Product, ProductImage
from inventory.models import StockMovement, Warehouse, WarehouseStock
from inventory.services import StockService
from orders.models import Address, Order, OrderItem, Payment
from vendors.models import VendorApplication, VendorProfile


@pytest.fixture
def admin_user(db):
    """Fixture to ensure an admin user is present for vendor approvals."""
    admin = User.objects.create_superuser(
        email='superadmin@example.com',
        password='AdminPassword123!',
        first_name='Admin',
        last_name='User',
    )
    return admin


@pytest.mark.django_db
class TestDemoDataSeeder:
    """Automated test suite for seed_demo_data command."""

    def test_seed_demo_data_all_vendor_types(self, admin_user):
        """Test successful creation and approval of all 8 vendor categories."""
        out = io.StringIO()
        call_command(
            'seed_demo_data',
            vendors=8,
            products_per_vendor=4,
            customers=6,
            orders=8,
            skip_analytics=True,
            stdout=out,
        )

        expected_vendor_ids = [
            'VNDDEMO0001', 'VNDDEMO0002', 'VNDDEMO0003', 'VNDDEMO0004',
            'VNDDEMO0005', 'VNDDEMO0006', 'VNDDEMO0007', 'VNDDEMO0008',
        ]
        expected_categories = [
            'electronics-gadgets', 'fashion-clothing', 'home-kitchen',
            'beauty-personal-care', 'sports-fitness', 'books-stationery',
            'grocery-essentials', 'toys-accessories',
        ]

        # Verify all 8 vendor profiles exist
        for vid in expected_vendor_ids:
            vp = VendorProfile.objects.filter(vendor_id=vid).first()
            assert vp is not None, f"VendorProfile {vid} should exist."
            assert vp.is_active is True
            assert vp.is_verified is True
            assert vp.user.role == User.Role.VENDOR
            assert vp.user.is_active is True
            assert vp.user.email.endswith('@shopsense.demo')

            # Verify associated approved application
            app = VendorApplication.objects.filter(vendor_id=vid).first()
            assert app is not None
            assert app.status == VendorApplication.Status.APPROVED
            assert app.reviewed_by == admin_user

        # Verify all 8 categories exist
        for cat_slug in expected_categories:
            assert Category.objects.filter(slug=cat_slug).exists()

    def test_product_to_vendor_relationships(self, admin_user):
        """Test products have valid vendor ownership, SKUs, and categories."""
        call_command(
            'seed_demo_data',
            vendors=4,
            products_per_vendor=5,
            customers=5,
            orders=4,
            skip_analytics=True,
        )

        demo_products = Product.objects.filter(sku__startswith='DEMO-')
        assert demo_products.count() == 20

        for prod in demo_products:
            assert prod.vendor.vendor_id.startswith('VNDDEMO')
            assert prod.category is not None
            assert prod.price > Decimal('0.00')
            assert prod.description != ''
            assert hasattr(prod, 'inventory')
            assert prod.inventory.low_stock_threshold >= 10

            # Verify product image is properly attached
            images = list(prod.images.all())
            assert len(images) >= 1
            assert images[0].image.name.startswith('products/demo_')

    def test_inventory_and_ledger_consistency(self, admin_user):
        """Test that warehouse stock matches append-only ledger movements with zero discrepancies."""
        call_command(
            'seed_demo_data',
            vendors=3,
            products_per_vendor=6,
            customers=5,
            orders=6,
            skip_analytics=True,
        )

        # 1. Run authoritative reconciliation service
        discrepancies = StockService.reconcile_inventory()
        assert len(discrepancies) == 0, f"Found unexpected discrepancies: {discrepancies}"

        # 2. Check each demo product's warehouse stocks against ledger sum
        for prod in Product.objects.filter(sku__startswith='DEMO-'):
            wstocks = list(WarehouseStock.objects.filter(product=prod))
            assert len(wstocks) > 0

            total_wh_available = 0
            for ws in wstocks:
                movements = StockMovement.objects.filter(product=prod, warehouse=ws.warehouse)
                ledger_sum = sum(m.quantity_change for m in movements)
                # Stock on-hand MUST equal exactly the ledger movement sum
                assert ws.quantity == ledger_sum
                total_wh_available += ws.available_quantity

            # Catalog aggregate inventory quantity MUST match total warehouse available
            assert prod.inventory.quantity == total_wh_available

        # 3. Check that diverse stock scenarios exist (healthy and out-of-stock)
        assert Product.objects.filter(sku__startswith='DEMO-', status=Product.Status.ACTIVE).exists()
        assert Product.objects.filter(sku__startswith='DEMO-', status=Product.Status.OUT_OF_STOCK).exists()

    def test_order_totals_and_financial_calculations(self, admin_user):
        """Test orders have correct financial totals, line items, and supported statuses."""
        call_command(
            'seed_demo_data',
            vendors=3,
            products_per_vendor=5,
            customers=5,
            orders=10,
            skip_analytics=True,
        )

        demo_orders = Order.objects.filter(order_number__startswith='DEMO-ORD-')
        assert demo_orders.count() == 10

        for order in demo_orders:
            items = list(order.items.all())
            assert len(items) >= 1

            calculated_subtotal = Decimal('0.00')
            for item in items:
                assert item.total_price == item.unit_price * item.quantity
                assert item.vendor == item.product.vendor
                assert item.product_sku == item.product.sku
                calculated_subtotal += item.total_price

            # Order subtotal matches item total
            assert order.subtotal == calculated_subtotal

            # Grand total matches subtotal + shipping + tax - discount
            expected_total = order.subtotal + order.shipping_cost + order.tax_amount - order.discount_amount
            assert order.total == expected_total

            # Verify associated payment record
            payment = Payment.objects.filter(order=order).first()
            assert payment is not None
            assert payment.amount == order.total
            assert payment.currency == 'INR'

            # Cancelled orders should have CANCELLED items
            if order.status == Order.Status.CANCELLED:
                for item in items:
                    assert item.status == OrderItem.Status.CANCELLED

    def test_repeated_seeding_without_duplicates_or_stock_inflation(self, admin_user):
        """Test running seed_demo_data repeatedly updates or skips without duplicating data or inflating stock."""
        # Run 1
        call_command(
            'seed_demo_data',
            vendors=2,
            products_per_vendor=4,
            customers=4,
            orders=4,
            skip_analytics=True,
        )

        v_count_1 = VendorProfile.objects.filter(vendor_id__startswith='VNDDEMO').count()
        p_count_1 = Product.objects.filter(sku__startswith='DEMO-').count()
        c_count_1 = User.objects.filter(email__endswith='@shopsense.demo', role=User.Role.CUSTOMER).count()
        o_count_1 = Order.objects.filter(order_number__startswith='DEMO-ORD-').count()
        mov_count_1 = StockMovement.objects.filter(product__sku__startswith='DEMO-').count()
        stock_units_1 = WarehouseStock.objects.filter(product__sku__startswith='DEMO-').aggregate(Sum('quantity'))['quantity__sum']

        # Run 2 with same arguments
        call_command(
            'seed_demo_data',
            vendors=2,
            products_per_vendor=4,
            customers=4,
            orders=4,
            skip_analytics=True,
        )

        v_count_2 = VendorProfile.objects.filter(vendor_id__startswith='VNDDEMO').count()
        p_count_2 = Product.objects.filter(sku__startswith='DEMO-').count()
        c_count_2 = User.objects.filter(email__endswith='@shopsense.demo', role=User.Role.CUSTOMER).count()
        o_count_2 = Order.objects.filter(order_number__startswith='DEMO-ORD-').count()
        mov_count_2 = StockMovement.objects.filter(product__sku__startswith='DEMO-').count()
        stock_units_2 = WarehouseStock.objects.filter(product__sku__startswith='DEMO-').aggregate(Sum('quantity'))['quantity__sum']

        # Verify no duplicate records created
        assert v_count_2 == v_count_1 == 2
        assert p_count_2 == p_count_1 == 8
        assert c_count_2 == c_count_1 == 4
        assert o_count_2 == o_count_1 == 4
        assert mov_count_2 == mov_count_1

        # Verify stock quantities did NOT inflate or double
        assert stock_units_2 == stock_units_1

        # Reconciliation remains 0
        discrepancies = StockService.reconcile_inventory()
        assert len(discrepancies) == 0

    def test_dry_run_behavior(self, admin_user):
        """Test dry-run mode simulates execution without writing any records to database."""
        user_before = User.objects.count()
        vendor_before = VendorProfile.objects.count()
        product_before = Product.objects.count()
        order_before = Order.objects.count()

        out = io.StringIO()
        call_command(
            'seed_demo_data',
            vendors=3,
            products_per_vendor=5,
            customers=5,
            orders=5,
            dry_run=True,
            skip_analytics=True,
            stdout=out,
        )

        output = out.getvalue()
        assert '[DRY RUN]' in output

        # Database state should be 100% identical
        assert User.objects.count() == user_before
        assert VendorProfile.objects.count() == vendor_before
        assert Product.objects.count() == product_before
        assert Order.objects.count() == order_before

    def test_preservation_of_existing_application_data_and_safe_cleanup(self, admin_user):
        """Test that seeder and cleanup strictly preserve ordinary, non-demo application data."""
        # 1. Create ordinary non-demo data
        real_vendor_user = User.objects.create_user(
            email='legitimate.vendor@customdomain.com',
            password='RealPassword123!',
            role=User.Role.VENDOR,
        )
        real_vendor = VendorProfile.objects.create(
            user=real_vendor_user,
            vendor_id='VNDREAL001',
            business_name='Real Vendor Store',
            contact_email=real_vendor_user.email,
        )
        real_cat = Category.objects.create(name='Real Category', slug='real-cat')
        real_prod = Product.objects.create(
            vendor=real_vendor,
            category=real_cat,
            name='Real Genuine Product',
            slug='real-genuine-product',
            sku='REAL-SKU-001',
            price=Decimal('500.00'),
            status=Product.Status.ACTIVE,
        )
        Inventory.objects.create(product=real_prod, quantity=100)
        wh = StockService.get_or_create_default_warehouse()
        WarehouseStock.objects.create(warehouse=wh, product=real_prod, quantity=100)
        StockMovement.objects.create(
            product=real_prod,
            warehouse=wh,
            quantity_change=100,
            movement_type=StockMovement.MovementType.PURCHASE,
            reason='Real inventory consignment',
            idempotency_key='real-inbound-key-001',
        )

        real_customer = User.objects.create_user(
            email='legitimate.customer@customdomain.com',
            password='RealCustomerPass123!',
            role=User.Role.CUSTOMER,
        )
        real_order = Order.objects.create(
            order_number='ORDREAL001',
            user=real_customer,
            email=real_customer.email,
            status=Order.Status.CONFIRMED,
            subtotal=Decimal('500.00'),
            total=Decimal('500.00'),
        )

        # 2. Run demo data generator
        call_command(
            'seed_demo_data',
            vendors=2,
            products_per_vendor=3,
            customers=3,
            orders=3,
            skip_analytics=True,
        )

        # Demo records exist
        assert Product.objects.filter(sku__startswith='DEMO-').exists()
        assert Order.objects.filter(order_number__startswith='DEMO-ORD-').exists()

        # Real records still exist
        assert VendorProfile.objects.filter(vendor_id='VNDREAL001').exists()
        assert Product.objects.filter(sku='REAL-SKU-001').exists()
        assert Order.objects.filter(order_number='ORDREAL001').exists()

        # 3. Run safe cleanup
        call_command('seed_demo_data', clear_demo_data=True)

        # Demo records are gone
        assert not Product.objects.filter(sku__startswith='DEMO-').exists()
        assert not Order.objects.filter(order_number__startswith='DEMO-ORD-').exists()
        assert not VendorProfile.objects.filter(vendor_id__startswith='VNDDEMO').exists()
        assert not User.objects.filter(email__endswith='@shopsense.demo').exists()

        # Real records are STILL preserved intact!
        assert VendorProfile.objects.filter(vendor_id='VNDREAL001').exists()
        assert Product.objects.filter(sku='REAL-SKU-001').exists()
        assert Order.objects.filter(order_number='ORDREAL001').exists()
        assert User.objects.filter(email='legitimate.vendor@customdomain.com').exists()
        assert User.objects.filter(email='legitimate.customer@customdomain.com').exists()

        # Real stock ledger is intact
        real_stock = WarehouseStock.objects.get(product=real_prod, warehouse=wh)
        assert real_stock.quantity == 100

    def test_isolation_from_real_services(self, admin_user):
        """Test that seeding executes without triggering real emails or payment webhooks."""
        mail.outbox.clear()

        call_command(
            'seed_demo_data',
            vendors=2,
            products_per_vendor=3,
            customers=4,
            orders=4,
            skip_analytics=True,
        )

        # Verify no customer emails sent
        assert len(mail.outbox) == 0

        # Verify payments recorded safely with supported methods and valid amounts
        for p in Payment.objects.filter(payment_id__startswith='PAY-DEMO-'):
            assert p.amount > Decimal('0.00')
            assert p.method in [m.value for m in Payment.Method]
            assert p.status in [s.value for s in Payment.Status]

    def test_dry_run_leaves_no_image_files_on_disk(self, admin_user, settings):
        """Test dry-run mode strictly prevents creating physical image files on disk."""
        from pathlib import Path
        media_products_dir = Path(settings.MEDIA_ROOT) / 'products'
        files_before = set(media_products_dir.glob('demo_*.png')) if media_products_dir.exists() else set()

        call_command(
            'seed_demo_data',
            vendors=2,
            products_per_vendor=3,
            customers=2,
            orders=2,
            dry_run=True,
            skip_analytics=True,
        )

        files_after = set(media_products_dir.glob('demo_*.png')) if media_products_dir.exists() else set()
        assert files_after == files_before, f"Dry-run created unexpected image files: {files_after - files_before}"

    def test_cleanup_removes_physical_image_files(self, admin_user, settings):
        """Test cleanup deletes physical demo image files from storage while preserving non-demo files."""
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile

        # Seed demo products with images
        call_command(
            'seed_demo_data',
            vendors=1,
            products_per_vendor=2,
            customers=2,
            orders=2,
            skip_analytics=True,
        )

        demo_images = list(ProductImage.objects.filter(product__sku__startswith='DEMO-'))
        assert len(demo_images) >= 2
        demo_image_names = [img.image.name for img in demo_images]
        for name in demo_image_names:
            assert default_storage.exists(name)

        # Create a non-demo legitimate product image in storage
        non_demo_file_name = 'products/legitimate_vendor_item.png'
        default_storage.save(non_demo_file_name, ContentFile(b'real product image bytes'))
        assert default_storage.exists(non_demo_file_name)

        # Execute cleanup
        call_command('seed_demo_data', clear_demo_data=True)

        # All demo image files MUST be deleted from storage
        for name in demo_image_names:
            assert not default_storage.exists(name), f"Demo image {name} was not deleted from storage"

        # Legitimate non-demo file MUST be strictly preserved
        assert default_storage.exists(non_demo_file_name), "Non-demo image file was mistakenly deleted"

        # Teardown non-demo test file
        default_storage.delete(non_demo_file_name)

    def test_argument_validation_bounds(self, admin_user):
        """Test command validates argument bounds and rejects invalid inputs."""
        from django.core.management.base import CommandError

        # Invalid vendors
        with pytest.raises(CommandError, match="Invalid --vendors"):
            call_command('seed_demo_data', vendors=0)

        with pytest.raises(CommandError, match="Invalid --vendors"):
            call_command('seed_demo_data', vendors=-5)

        # Invalid products-per-vendor
        with pytest.raises(CommandError, match="Invalid --products-per-vendor"):
            call_command('seed_demo_data', products_per_vendor=0)

        # Invalid customers
        with pytest.raises(CommandError, match="Invalid --customers"):
            call_command('seed_demo_data', customers=0)

        # Invalid orders
        with pytest.raises(CommandError, match="Invalid --orders"):
            call_command('seed_demo_data', orders=-1)

    def test_refuse_production_database_without_explicit_flag(self, admin_user, settings):
        """Test command unconditionally blocks running against a production database."""
        from django.core.management.base import CommandError

        settings.FORCE_PRODUCTION_CHECK = True
        settings.DEBUG = False

        # Should unconditionally block live run
        with pytest.raises(CommandError, match="DEMO SEEDER BLOCKED"):
            call_command('seed_demo_data', vendors=2, products_per_vendor=2)

        # Should unconditionally block cleanup
        with pytest.raises(CommandError, match="DEMO SEEDER BLOCKED"):
            call_command('seed_demo_data', clear_demo_data=True)

    def test_demo_account_passwords_are_prefixed(self, admin_user):
        """Test demo accounts have explicitly prefixed passwords that authenticate properly."""
        from django.contrib.auth import authenticate
        from inventory.management.commands.seed_demo_data import (
            DEMO_VENDOR_PASSWORD,
            DEMO_CUSTOMER_PASSWORD,
        )

        assert DEMO_VENDOR_PASSWORD.startswith('Demo')
        assert DEMO_CUSTOMER_PASSWORD.startswith('Demo')

        call_command(
            'seed_demo_data',
            vendors=1,
            products_per_vendor=2,
            customers=2,
            orders=1,
            skip_analytics=True,
        )

        vendor_user = User.objects.get(email='demo.vendor.electronics@shopsense.demo')
        assert vendor_user.check_password(DEMO_VENDOR_PASSWORD)
        assert not vendor_user.check_password('ProductionPassword123!')

        customer_user = User.objects.get(email='demo.customer01@shopsense.demo')
        assert customer_user.check_password(DEMO_CUSTOMER_PASSWORD)
        assert not customer_user.check_password('SecretPass123!')

    def test_cleanup_aborts_if_non_demo_product_attached_to_demo_vendor(self, admin_user):
        """Test cleanup aborts immediately if a non-demo product is linked to a demo vendor, preserving it."""
        from django.core.management.base import CommandError

        # 1. Seed demo vendor
        call_command(
            'seed_demo_data',
            vendors=1,
            products_per_vendor=2,
            customers=1,
            orders=1,
            skip_analytics=True,
        )

        demo_vendor = VendorProfile.objects.filter(vendor_id__startswith='VNDDEMO').first()
        assert demo_vendor is not None
        category = Category.objects.first()

        # 2. Attach a non-demo product to this demo vendor
        real_product = Product.objects.create(
            vendor=demo_vendor,
            category=category,
            name='Accidental Real Product Under Demo Vendor',
            slug='accidental-real-product',
            sku='REAL-ATTACHED-TO-DEMO-001',
            price=Decimal('1250.00'),
            status=Product.Status.ACTIVE,
        )
        assert Product.objects.filter(sku='REAL-ATTACHED-TO-DEMO-001').exists()

        # 3. Attempt cleanup -> Must raise CommandError and abort
        with pytest.raises(CommandError, match="CLEANUP ABORTED FOR SAFETY"):
            call_command('seed_demo_data', clear_demo_data=True)

        # 4. Regression verification: non-demo product and demo vendor remain 100% intact
        assert Product.objects.filter(sku='REAL-ATTACHED-TO-DEMO-001').exists(), (
            "Regression failure: non-demo product was deleted during aborted cleanup!"
        )
        assert VendorProfile.objects.filter(pk=demo_vendor.pk).exists(), (
            "Regression failure: demo vendor was deleted even though cleanup was supposed to abort!"
        )

        # Teardown: manually delete the test product so other tests start clean
        real_product.delete()
        call_command('seed_demo_data', clear_demo_data=True)

    def test_storage_cleanup_preserves_files_when_database_fails(self, admin_user, monkeypatch):
        """Test physical image files are preserved if database transaction rolls back during cleanup."""
        from django.core.files.storage import default_storage
        from django.core.management.base import CommandError

        # 1. Seed 1 vendor with 2 products (creating images in storage)
        call_command(
            'seed_demo_data',
            vendors=1,
            products_per_vendor=2,
            customers=1,
            orders=0,
            skip_analytics=True,
        )

        demo_images = list(ProductImage.objects.filter(product__sku__startswith='DEMO-'))
        assert len(demo_images) >= 2
        file_names = [img.image.name for img in demo_images]
        for fname in file_names:
            assert default_storage.exists(fname)

        # 2. Monkeypatch User.delete (called in step 9 of cleanup) to simulate a DB crash
        def failing_user_delete(*args, **kwargs):
            raise RuntimeError("Simulated database failure during customer cleanup")

        from accounts.models import User
        orig_filter = User.objects.filter

        def patched_filter(*args, **kwargs):
            qs = orig_filter(*args, **kwargs)
            if kwargs.get('email__endswith') == '@shopsense.demo':
                qs.delete = failing_user_delete
            return qs

        monkeypatch.setattr(User.objects, 'filter', patched_filter)

        # 3. Execute cleanup: should fail because of simulated DB crash
        with pytest.raises(Exception, match="Simulated database failure"):
            call_command('seed_demo_data', clear_demo_data=True)

        # 4. Storage cleanup safety verification: Because DB transaction rolled back,
        # NO physical image files should have been deleted!
        for fname in file_names:
            assert default_storage.exists(fname), (
                f"File {fname} was deleted despite database transaction failure!"
            )

        # Restore and teardown
        monkeypatch.undo()
        call_command('seed_demo_data', clear_demo_data=True)

    def test_storage_cleanup_handles_storage_failure_gracefully(self, admin_user, monkeypatch):
        """Test that storage unlinking errors during cleanup are logged and handled without crashing."""
        from django.core.files.storage import default_storage

        # 1. Seed demo data
        call_command(
            'seed_demo_data',
            vendors=1,
            products_per_vendor=2,
            customers=1,
            orders=0,
            skip_analytics=True,
        )

        demo_images = list(ProductImage.objects.filter(product__sku__startswith='DEMO-'))
        assert len(demo_images) >= 2
        file_names = [img.image.name for img in demo_images]
        for fname in file_names:
            assert default_storage.exists(fname)

        # 2. Monkeypatch default_storage.delete to simulate an OSError / PermissionError
        def failing_storage_delete(name):
            raise OSError(f"Permission denied unlinking {name}")

        monkeypatch.setattr(default_storage, 'delete', failing_storage_delete)

        # 3. Execute cleanup: should complete safely without raising an unhandled exception
        out = io.StringIO()
        call_command('seed_demo_data', clear_demo_data=True, stdout=out)

        # Output should report the failure warning
        output = out.getvalue()
        assert "Warning: Failed to delete image file" in output or "file unlinks failed" in output

        # Database records should nonetheless be successfully deleted
        assert not Product.objects.filter(sku__startswith='DEMO-').exists()
        assert not ProductImage.objects.filter(product__sku__startswith='DEMO-').exists()

        # Teardown physical files
        monkeypatch.undo()
        for fname in file_names:
            if default_storage.exists(fname):
                default_storage.delete(fname)

    def test_unapproved_database_target_protection(self, admin_user, monkeypatch, settings):
        """Test command defaults to refusing live seeding and cleanup unless database is approved."""
        from django.core.management.base import CommandError

        # Make sure DEBUG is True (development environment)
        settings.DEBUG = True
        settings.FORCE_PRODUCTION_CHECK = False

        # Simulate running outside pytest test runner without explicit approval
        monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
        monkeypatch.delenv('SHOPSENSE_DEMO_DATABASE_APPROVED', raising=False)
        if hasattr(settings, 'SHOPSENSE_DEMO_DATABASE_APPROVED'):
            delattr(settings, 'SHOPSENSE_DEMO_DATABASE_APPROVED')

        # 1. Live seeding MUST be refused
        with pytest.raises(CommandError, match="not explicitly approved for demo data operations"):
            call_command('seed_demo_data', vendors=1, products_per_vendor=1)

        # 2. Live cleanup MUST be refused
        with pytest.raises(CommandError, match="not explicitly approved for demo data operations"):
            call_command('seed_demo_data', clear_demo_data=True)

        # 3. Dry-run mode MUST be permitted even without explicit approval (simulation only)
        out = io.StringIO()
        call_command(
            'seed_demo_data',
            vendors=1,
            products_per_vendor=1,
            customers=1,
            orders=0,
            dry_run=True,
            skip_analytics=True,
            stdout=out,
        )
        assert '[DRY RUN]' in out.getvalue()

        # 4. When explicit approval is granted via env var, live seeding succeeds
        monkeypatch.setenv('SHOPSENSE_DEMO_DATABASE_APPROVED', 'True')
        call_command(
            'seed_demo_data',
            vendors=1,
            products_per_vendor=1,
            customers=1,
            orders=0,
            skip_analytics=True,
        )
        assert Product.objects.filter(sku__startswith='DEMO-').exists()

        # Clean up
        call_command('seed_demo_data', clear_demo_data=True)

    def test_production_environment_always_refused_even_with_approval(self, admin_user, monkeypatch, settings):
        """Test production environment (DEBUG=False) is unconditionally refused, even if approval is attempted."""
        from django.core.management.base import CommandError

        # Simulate production environment
        settings.DEBUG = False
        settings.FORCE_PRODUCTION_CHECK = True
        monkeypatch.setenv('SHOPSENSE_DEMO_DATABASE_APPROVED', 'True')

        with pytest.raises(CommandError, match="DEMO SEEDER BLOCKED"):
            call_command('seed_demo_data', vendors=1, products_per_vendor=1)

        with pytest.raises(CommandError, match="DEMO SEEDER BLOCKED"):
            call_command('seed_demo_data', clear_demo_data=True)

    def test_dry_run_reports_database_backend_without_credentials(self, admin_user):
        """Test dry-run output clearly reports database backend without exposing passwords or credentials."""
        out = io.StringIO()
        call_command(
            'seed_demo_data',
            vendors=1,
            products_per_vendor=1,
            customers=1,
            orders=0,
            dry_run=True,
            skip_analytics=True,
            stdout=out,
        )

        output = out.getvalue()
        # Verify reporting of database backend
        assert 'Database Target:' in output
        assert 'sqlite' in output.lower()
        assert '[DRY RUN]' in output

        # Verify absolutely no credential exposure
        assert 'password' not in output.lower()
        assert 'secret' not in output.lower()



