"""
Django Management Command: import_demo_marketplace_data

Safely imports marketplace demo vendors, products, categories, and inventory
from CSV files into ShopSense while strictly preserving data integrity,
preventing duplicate entries, and enforcing role-based access control.

Usage:
    python manage.py import_demo_marketplace_data [options]

Options:
    --vendors-file PATH     Path to vendors CSV (default: shopsense_demo_vendors.csv)
    --products-file PATH    Path to products CSV (default: shopsense_demo_products.csv)
    --dry-run               Simulate import with validation and roll back all changes
    --skip-analytics        Skip post-import analytics refreshes
    --force                 Allow live execution on approved local/staging environments
"""

import csv
from decimal import Decimal, InvalidOperation
import io
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from PIL import Image, ImageDraw
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import User
from catalog.models import Category, Inventory, Product, ProductImage
from inventory.models import StockMovement, Warehouse, WarehouseStock
from inventory.services import StockService
from vendors.models import AuditLog, VendorApplication, VendorProfile

User = get_user_model()
logger = logging.getLogger(__name__)

# Dedicated markers for safe identification and isolation
DEMO_EMAIL_DOMAIN = 'shopsense.demo'
DEMO_VENDOR_ID_PREFIX = 'VNDDEMO'
DEMO_SKU_PREFIX = 'DEMO-'
DEMO_VENDOR_PASSWORD = 'DemoVendor2026!'

# Canonical header mappings (normalized alphanumeric lowercase)
VENDOR_HEADER_MAP = {
    'vendorcode': 'vendor_code',
    'vendorid': 'vendor_code',
    'vendor': 'vendor_code',
    'code': 'vendor_code',
    'id': 'vendor_code',
    'businessname': 'business_name',
    'companyname': 'business_name',
    'vendorname': 'business_name',
    'name': 'business_name',
    'contactemail': 'contact_email',
    'email': 'contact_email',
    'vendoremail': 'contact_email',
    'contactphone': 'contact_phone',
    'phone': 'contact_phone',
    'phonenumber': 'contact_phone',
    'businessaddress': 'business_address',
    'address': 'business_address',
    'streetaddress': 'business_address',
    'city': 'city',
    'state': 'state',
    'postalcode': 'postal_code',
    'zipcode': 'postal_code',
    'pincode': 'postal_code',
    'zip': 'postal_code',
    'country': 'country',
    'taxid': 'tax_id',
    'gstin': 'tax_id',
    'pan': 'tax_id',
    'website': 'website',
    'url': 'website',
    'commissionrate': 'commission_rate',
    'commission': 'commission_rate',
    'businessdescription': 'business_description',
    'description': 'business_description',
    'firstname': 'first_name',
    'lastname': 'last_name',
}

PRODUCT_HEADER_MAP = {
    'sku': 'sku',
    'productsku': 'sku',
    'itemcode': 'sku',
    'code': 'sku',
    'vendorcode': 'vendor_code',
    'vendorid': 'vendor_code',
    'vendor': 'vendor_code',
    'name': 'name',
    'productname': 'name',
    'title': 'name',
    'category': 'category',
    'categoryname': 'category',
    'categoryslug': 'category',
    'price': 'price',
    'unitprice': 'price',
    'sellingprice': 'price',
    'compareatprice': 'compare_at_price',
    'mrp': 'compare_at_price',
    'originalprice': 'compare_at_price',
    'costprice': 'cost_price',
    'cost': 'cost_price',
    'quantity': 'quantity',
    'stock': 'quantity',
    'inventoryquantity': 'quantity',
    'inventory': 'quantity',
    'qty': 'quantity',
    'lowstockthreshold': 'low_stock_threshold',
    'alertthreshold': 'low_stock_threshold',
    'reorderpoint': 'low_stock_threshold',
    'description': 'description',
    'productdescription': 'description',
    'longdescription': 'description',
    'shortdescription': 'short_description',
    'summary': 'short_description',
    'weight': 'weight',
    'dimensions': 'dimensions',
    'status': 'status',
    'isfeatured': 'is_featured',
    'featured': 'is_featured',
}


def normalize_header(header: str) -> str:
    """Normalize a CSV header string to lowercase alphanumeric characters."""
    return re.sub(r'[^a-z0-9]', '', header.strip().lower())


def get_sanitized_db_info() -> Dict[str, str]:
    """Extract database connection metadata with credentials securely redacted."""
    from django.db import connection
    db_dict = connection.settings_dict
    engine = db_dict.get('ENGINE', 'unknown').split('.')[-1]
    raw_host = db_dict.get('HOST', 'localhost') or 'localhost'
    raw_port = str(db_dict.get('PORT', '')) or 'default'
    raw_name = str(db_dict.get('NAME', 'unknown'))

    host_clean = re.sub(r'//[^@]+@', '//', raw_host)
    if '@' in host_clean:
        host_clean = host_clean.split('@')[-1]

    return {
        'engine': engine,
        'host': host_clean,
        'port': raw_port,
        'name': raw_name,
    }


def is_production_environment() -> bool:
    """Determine whether the current process is running in a production environment."""
    if getattr(settings, 'FORCE_PRODUCTION_CHECK', False):
        return True
    if os.environ.get('PYTEST_CURRENT_TEST') or ('pytest' in sys.modules and 'test' in sys.argv):
        return False
    return not getattr(settings, 'DEBUG', False)


def is_database_approved(db_info: Dict[str, str], force: bool = False) -> Tuple[bool, str]:
    """Verify that the active database target is safe and approved for demo operations."""
    if os.environ.get('PYTEST_CURRENT_TEST') or ('pytest' in sys.modules and 'test' in sys.argv):
        return True, "Automated test environment detected."

    # Prevent accidental execution against remote production databases (e.g. Supabase pooler)
    if 'supabase' in db_info['host'].lower() and not getattr(settings, 'ALLOW_SUPABASE_DEMO_IMPORT', False):
        return False, (
            f"BLOCKED: Attempting to run demo import against production database host '{db_info['host']}'. "
            "Demo data import is strictly prohibited on production Supabase infrastructure."
        )

    env_approval = os.environ.get('SHOPSENSE_DEMO_DATABASE_APPROVED', '').strip().lower()
    setting_approval = getattr(settings, 'SHOPSENSE_DEMO_DATABASE_APPROVED', False)
    if env_approval in ('true', '1', 'yes') or setting_approval is True or force:
        return True, "Explicit authorization granted."

    # SQLite and local staging DBs are safe for local development
    if 'sqlite' in db_info['engine'].lower() or db_info['host'] in ('localhost', '127.0.0.1'):
        return True, "Local development/staging database detected."

    return False, (
        f"Database target '{db_info['engine']}://{db_info['host']}/{db_info['name']}' "
        "is not explicitly approved for demo data operations. "
        "Use --force or set SHOPSENSE_DEMO_DATABASE_APPROVED=True to execute."
    )


def generate_demo_product_image(product_name: str, category_name: str) -> ContentFile:
    """Generate a lightweight, verified placeholder PNG for the product."""
    color_palette = [
        (37, 99, 235),   # Blue
        (16, 185, 129),  # Green
        (217, 119, 6),   # Amber
        (124, 58, 237),  # Purple
        (236, 72, 153),  # Pink
        (14, 165, 233),  # Sky
    ]
    color = color_palette[abs(hash(category_name)) % len(color_palette)]

    img = Image.new('RGB', (400, 400), color=color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 16, 384, 384], outline=(255, 255, 255), width=3)
    draw.ellipse([140, 140, 260, 260], fill=(255, 255, 255))

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    filename = f"demo_import_{slugify(product_name)[:25]}.png"
    return ContentFile(buffer.getvalue(), name=filename)


class Command(BaseCommand):
    help = (
        'Safe, idempotent CSV importer for ShopSense demo marketplace data. '
        'Imports vendors, products, categories, and inventory stock balances with '
        'strict RBAC enforcement and transactional rollbacks.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--vendors-file',
            type=str,
            default='shopsense_demo_vendors.csv',
            help='Path to the vendors CSV file (defaults to shopsense_demo_vendors.csv)',
        )
        parser.add_argument(
            '--products-file',
            type=str,
            default='shopsense_demo_products.csv',
            help='Path to the products CSV file (defaults to shopsense_demo_products.csv)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Validate and simulate the import without committing changes to the database',
        )
        parser.add_argument(
            '--skip-analytics',
            action='store_true',
            default=False,
            help='Skip post-import analytics model updates',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            default=False,
            help='Force execution on local/staging database even if approval env var is not set',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        vendors_path = options['vendors_file']
        products_path = options['products_file']

        db_info = get_sanitized_db_info()

        # 1. Production safety check
        if is_production_environment():
            raise CommandError(
                f"IMPORT BLOCKED: Running demo data import against production (DEBUG=False, engine={db_info['engine']}) "
                "is strictly prohibited to protect live marketplace integrity."
            )

        # 2. Database authorization check (for live runs)
        if not dry_run:
            approved, reason = is_database_approved(db_info, force=force)
            if not approved:
                raise CommandError(f"IMPORT BLOCKED: {reason}")

        self.stdout.write(self.style.NOTICE(
            f"Database Target: {db_info['engine']} | Host={db_info['host']} | DB={db_info['name']}"
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "=== [DRY RUN] Mode Active: All rows will be validated, changes simulated and rolled back. ==="
            ))
        else:
            self.stdout.write(self.style.NOTICE(
                "=== Live Execution Mode: Validated rows will be committed atomically. ==="
            ))

        # 3. Read and map CSV files
        raw_vendors = self.read_and_map_csv(vendors_path, VENDOR_HEADER_MAP, 'vendors')
        raw_products = self.read_and_map_csv(products_path, PRODUCT_HEADER_MAP, 'products')

        self.stdout.write(self.style.SUCCESS(
            f"Loaded {len(raw_vendors)} vendor row(s) from '{vendors_path}' and "
            f"{len(raw_products)} product row(s) from '{products_path}'."
        ))

        # 4. Strict Pre-Commit Validation
        validation_errors = self.validate_dataset(raw_vendors, raw_products)
        if validation_errors:
            self.stdout.write(self.style.ERROR("\nDATA VALIDATION FAILED! The following issues were found:"))
            for err in validation_errors:
                self.stdout.write(self.style.ERROR(f"  - {err}"))
            errors_detail = "\n".join(f"  - {err}" for err in validation_errors)
            raise CommandError(
                f"Aborting import due to {len(validation_errors)} validation error(s):\n{errors_detail}\n"
                "No database changes were made."
            )

        # 5. Execute Import within an atomic transaction
        try:
            with transaction.atomic():
                summary = self.execute_import(
                    vendors_data=raw_vendors,
                    products_data=raw_products,
                    dry_run=dry_run,
                    skip_analytics=options['skip_analytics'],
                )

                if dry_run:
                    transaction.set_rollback(True)
                    self.stdout.write(self.style.WARNING(
                        "\n[DRY RUN] All validation checks passed. Database transaction successfully rolled back."
                    ))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        "\n=== Demo Marketplace Data Imported and Committed Successfully! ==="
                    ))

            self.print_summary(summary, dry_run=dry_run, db_info=db_info)

        except Exception as e:
            logger.exception("Error executing demo marketplace import")
            raise CommandError(f"Import failed during database execution: {e}")

    def read_and_map_csv(
        self,
        file_path: str,
        header_map: Dict[str, str],
        file_type: str,
    ) -> List[Dict[str, Any]]:
        """Read CSV file and map headers flexibly to canonical model fields."""
        if not os.path.exists(file_path):
            raise CommandError(f"File not found: '{file_path}'. Please provide a valid path for {file_type} CSV.")

        mapped_rows = []
        with open(file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            try:
                raw_headers = next(reader)
            except StopIteration:
                raise CommandError(f"File '{file_path}' is empty.")

            # Build index-to-canonical mapping
            col_mapping: Dict[int, str] = {}
            for idx, raw_h in enumerate(raw_headers):
                normalized = normalize_header(raw_h)
                if normalized in header_map:
                    col_mapping[idx] = header_map[normalized]

            # Verify required columns exist in header
            if file_type == 'vendors':
                required_cols = {'vendor_code', 'business_name', 'contact_email'}
            else:
                required_cols = {'sku', 'vendor_code', 'name', 'category', 'price'}

            mapped_cols = set(col_mapping.values())
            missing_cols = required_cols - mapped_cols
            if missing_cols:
                raise CommandError(
                    f"CSV header in '{file_path}' is missing required column(s): {sorted(missing_cols)}. "
                    f"Found mapped columns: {sorted(mapped_cols)}"
                )

            for line_no, row in enumerate(reader, start=2):
                if not row or all(c.strip() == '' for c in row):
                    continue  # skip blank lines

                mapped_row: Dict[str, Any] = {'_line_number': line_no}
                for idx, val in enumerate(row):
                    if idx in col_mapping:
                        field_name = col_mapping[idx]
                        mapped_row[field_name] = val.strip()

                mapped_rows.append(mapped_row)

        if not mapped_rows:
            raise CommandError(f"File '{file_path}' contains headers but zero data rows.")

        return mapped_rows

    def validate_dataset(
        self,
        vendors_data: List[Dict[str, Any]],
        products_data: List[Dict[str, Any]],
    ) -> List[str]:
        """Validate all rows and cross-file foreign key references before touching the database."""
        errors: List[str] = []

        known_vendor_codes: Set[str] = set()
        seen_vendor_codes_in_file: Set[str] = set()
        seen_emails_in_file: Set[str] = set()

        # Pre-load existing database vendor codes and emails
        existing_vendor_codes = set(VendorProfile.objects.values_list('vendor_id', flat=True))
        known_vendor_codes.update(existing_vendor_codes)

        # 1. Validate Vendors
        for v in vendors_data:
            line = v['_line_number']
            code = v.get('vendor_code', '')
            name = v.get('business_name', '')
            email = v.get('contact_email', '').lower()

            if not code:
                errors.append(f"Vendors CSV (Line {line}): vendor_code cannot be empty.")
            elif code in seen_vendor_codes_in_file:
                errors.append(f"Vendors CSV (Line {line}): Duplicate vendor_code '{code}' in CSV file.")
            else:
                seen_vendor_codes_in_file.add(code)
                known_vendor_codes.add(code)

            if not name:
                errors.append(f"Vendors CSV (Line {line}): business_name cannot be empty.")

            if not email:
                errors.append(f"Vendors CSV (Line {line}): contact_email cannot be empty.")
            else:
                try:
                    validate_email(email)
                except ValidationError:
                    errors.append(f"Vendors CSV (Line {line}): Invalid email format '{email}'.")

                if email in seen_emails_in_file:
                    errors.append(f"Vendors CSV (Line {line}): Duplicate contact_email '{email}' in CSV file.")
                seen_emails_in_file.add(email)

                # Real-user protection: Check if user exists as a real non-demo user
                existing_user = User.objects.filter(email=email).first()
                if existing_user:
                    # User is considered real if not a demo account
                    is_demo = (
                        email.endswith(f"@{DEMO_EMAIL_DOMAIN}") or
                        existing_user.role == User.Role.VENDOR and hasattr(existing_user, 'vendor_profile') and
                        existing_user.vendor_profile.vendor_id.startswith(DEMO_VENDOR_ID_PREFIX)
                    )
                    if not is_demo:
                        errors.append(
                            f"Vendors CSV (Line {line}): Protection violation! Email '{email}' belongs to an "
                            "existing real user. Demo import will never overwrite real users."
                        )

            # Commission rate validation
            comm_raw = v.get('commission_rate', '10.00')
            if comm_raw:
                try:
                    comm = Decimal(comm_raw)
                    if comm < 0 or comm > 100:
                        errors.append(f"Vendors CSV (Line {line}): commission_rate '{comm_raw}' must be between 0 and 100.")
                except (InvalidOperation, TypeError):
                    errors.append(f"Vendors CSV (Line {line}): Invalid commission_rate '{comm_raw}'. Must be numeric.")

        # 2. Validate Products
        seen_skus_in_file: Set[str] = set()

        for p in products_data:
            line = p['_line_number']
            sku = p.get('sku', '')
            vcode = p.get('vendor_code', '')
            pname = p.get('name', '')
            cat = p.get('category', '')
            price_raw = p.get('price', '')

            if not sku:
                errors.append(f"Products CSV (Line {line}): SKU cannot be empty.")
            elif sku in seen_skus_in_file:
                errors.append(f"Products CSV (Line {line}): Duplicate SKU '{sku}' in CSV file.")
            seen_skus_in_file.add(sku)

            # Foreign-key reference to vendor
            if not vcode:
                errors.append(f"Products CSV (Line {line}): vendor_code cannot be empty.")
            elif vcode not in known_vendor_codes:
                errors.append(
                    f"Products CSV (Line {line}): Foreign key violation! vendor_code '{vcode}' "
                    "does not exist in database and is not defined in the vendors CSV."
                )

            if not pname:
                errors.append(f"Products CSV (Line {line}): Product name cannot be empty.")

            if not cat:
                errors.append(f"Products CSV (Line {line}): Category cannot be empty.")

            # Price validation
            if not price_raw:
                errors.append(f"Products CSV (Line {line}): Price cannot be empty.")
            else:
                try:
                    price = Decimal(price_raw)
                    if price <= 0:
                        errors.append(f"Products CSV (Line {line}): Price '{price_raw}' must be greater than 0.")
                except (InvalidOperation, TypeError):
                    errors.append(f"Products CSV (Line {line}): Invalid price format '{price_raw}'. Must be numeric.")

            # Compare at price validation
            cmp_raw = p.get('compare_at_price', '')
            if cmp_raw:
                try:
                    cmp_price = Decimal(cmp_raw)
                    if cmp_price < 0:
                        errors.append(f"Products CSV (Line {line}): compare_at_price '{cmp_raw}' cannot be negative.")
                except (InvalidOperation, TypeError):
                    errors.append(f"Products CSV (Line {line}): Invalid compare_at_price '{cmp_raw}'.")

            # Cost price validation
            cost_raw = p.get('cost_price', '')
            if cost_raw:
                try:
                    cost_price = Decimal(cost_raw)
                    if cost_price < 0:
                        errors.append(f"Products CSV (Line {line}): cost_price '{cost_raw}' cannot be negative.")
                except (InvalidOperation, TypeError):
                    errors.append(f"Products CSV (Line {line}): Invalid cost_price '{cost_raw}'.")

            # Quantity validation
            qty_raw = p.get('quantity', '0')
            if qty_raw:
                try:
                    qty = int(qty_raw)
                    if qty < 0:
                        errors.append(f"Products CSV (Line {line}): quantity '{qty_raw}' cannot be negative.")
                except ValueError:
                    errors.append(f"Products CSV (Line {line}): Invalid quantity '{qty_raw}'. Must be an integer.")

            # Real product protection: If SKU exists in database and is not demo
            existing_prod = Product.objects.filter(sku=sku).first()
            if existing_prod:
                is_demo_prod = (
                    sku.startswith(DEMO_SKU_PREFIX) or
                    existing_prod.vendor.vendor_id.startswith(DEMO_VENDOR_ID_PREFIX)
                )
                if not is_demo_prod:
                    errors.append(
                        f"Products CSV (Line {line}): Protection violation! SKU '{sku}' belongs to an existing "
                        "real product. Demo import will never overwrite real products."
                    )

        return errors

    def execute_import(
        self,
        vendors_data: List[Dict[str, Any]],
        products_data: List[Dict[str, Any]],
        dry_run: bool = False,
        skip_analytics: bool = False,
    ) -> Dict[str, Any]:
        """Execute atomic creation of vendors, categories, products, images, and inventory movements."""
        summary = {
            'vendors_total': len(vendors_data),
            'vendors_created': 0,
            'vendors_reused': 0,
            'products_total': len(products_data),
            'products_created': 0,
            'products_reused': 0,
            'categories_created': 0,
            'categories_reused': 0,
            'inventory_units_inbounded': 0,
            'total_catalog_value': Decimal('0.00'),
            'discrepancies': 0,
        }

        # 1. Warehouse Setup
        wh_default = StockService.get_or_create_default_warehouse()
        admin_user = User.objects.filter(role=User.Role.ADMIN).first()

        # 2. Import Vendors
        vendor_profiles_map: Dict[str, VendorProfile] = {}

        for v in vendors_data:
            code = v['vendor_code']
            email = v['contact_email'].lower()
            name = v['business_name']

            existing_profile = VendorProfile.objects.filter(vendor_id=code).first()
            if existing_profile:
                vendor_profiles_map[code] = existing_profile
                summary['vendors_reused'] += 1
                continue

            # Ensure Vendor User exists with VENDOR role
            first_name = v.get('first_name') or (name.split()[0] if name else 'Vendor')
            last_name = v.get('last_name') or 'Demo'

            user, user_created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'role': User.Role.VENDOR,
                    'phone': v.get('contact_phone', ''),
                    'is_active': True,
                },
            )
            if user_created:
                user.set_password(DEMO_VENDOR_PASSWORD)
                user.save()
            else:
                if user.role != User.Role.VENDOR:
                    user.role = User.Role.VENDOR
                    user.is_active = True
                    user.save(update_fields=['role', 'is_active'])

            # Create or update VendorApplication for workflow consistency
            app, _ = VendorApplication.objects.get_or_create(
                contact_email=email,
                defaults={
                    'business_name': name,
                    'business_description': v.get('business_description', ''),
                    'contact_phone': v.get('contact_phone', ''),
                    'business_address': v.get('business_address', ''),
                    'city': v.get('city', ''),
                    'state': v.get('state', ''),
                    'postal_code': v.get('postal_code', ''),
                    'country': v.get('country', 'India'),
                    'tax_id': v.get('tax_id', ''),
                    'website': v.get('website', ''),
                    'vendor_id': code,
                    'status': VendorApplication.Status.APPROVED,
                    'reviewed_by': admin_user,
                    'reviewed_at': timezone.now(),
                    'admin_notes': 'Auto-approved via demo marketplace CSV import',
                },
            )

            # Create VendorProfile
            comm_rate = Decimal(v.get('commission_rate', '10.00'))
            profile = VendorProfile.objects.create(
                user=user,
                vendor_id=code,
                business_name=name,
                business_description=v.get('business_description', ''),
                contact_email=email,
                contact_phone=v.get('contact_phone', ''),
                business_address=v.get('business_address', ''),
                city=v.get('city', ''),
                state=v.get('state', ''),
                postal_code=v.get('postal_code', ''),
                country=v.get('country', 'India'),
                tax_id=v.get('tax_id', ''),
                website=v.get('website', ''),
                commission_rate=comm_rate,
                is_active=True,
                is_verified=True,
            )

            # Audit log for RBAC transparency
            AuditLog.objects.create(
                user=admin_user,
                action=AuditLog.ActionType.VENDOR_APPROVED,
                target_user=user,
                target_vendor=profile,
                details={'vendor_id': code, 'source': 'CSV import_demo_marketplace_data'},
            )

            vendor_profiles_map[code] = profile
            summary['vendors_created'] += 1

        # Also load any pre-existing database vendors referenced in products
        for p in products_data:
            vcode = p['vendor_code']
            if vcode not in vendor_profiles_map:
                prof = VendorProfile.objects.filter(vendor_id=vcode).first()
                if prof:
                    vendor_profiles_map[vcode] = prof

        # 3. Import Categories
        categories_map: Dict[str, Category] = {}
        unique_categories = {p['category'] for p in products_data}

        for cat_name in unique_categories:
            slug = slugify(cat_name)
            cat_obj, created = Category.objects.get_or_create(
                slug=slug,
                defaults={
                    'name': cat_name,
                    'description': f"Marketplace category for {cat_name}.",
                    'is_active': True,
                },
            )
            categories_map[cat_name] = cat_obj
            if created:
                summary['categories_created'] += 1
            else:
                summary['categories_reused'] += 1

        # 4. Import Products and Inventory
        for p in products_data:
            sku = p['sku']
            existing_prod = Product.objects.filter(sku=sku).first()
            if existing_prod:
                summary['products_reused'] += 1
                continue

            vendor = vendor_profiles_map[p['vendor_code']]
            category = categories_map[p['category']]
            name = p['name']
            price = Decimal(p['price'])

            cmp_price = Decimal(p['compare_at_price']) if p.get('compare_at_price') else None
            cost_price = Decimal(p['cost_price']) if p.get('cost_price') else None
            weight = Decimal(p['weight']) if p.get('weight') else None
            status_val = p.get('status', Product.Status.ACTIVE).upper()
            if status_val not in Product.Status.values:
                status_val = Product.Status.ACTIVE
            is_feat = str(p.get('is_featured', 'False')).strip().lower() in ('true', '1', 'yes')

            desc = p.get('description') or f"High quality demo product: {name}."
            short_desc = p.get('short_description') or desc[:150]

            product = Product.objects.create(
                vendor=vendor,
                category=category,
                name=name,
                slug=f"{slugify(name)[:50]}-{sku.lower()}",
                sku=sku,
                description=desc,
                short_description=short_desc,
                price=price,
                compare_at_price=cmp_price,
                cost_price=cost_price,
                weight=weight,
                dimensions=p.get('dimensions', ''),
                status=status_val,
                is_featured=is_feat,
            )

            # Generate placeholder product image (only when not dry-running)
            if not dry_run:
                try:
                    img_file = generate_demo_product_image(product.name, category.name)
                    ProductImage.objects.create(
                        product=product,
                        image=img_file,
                        alt_text=product.name,
                        is_primary=True,
                        sort_order=0,
                    )
                except Exception as img_err:
                    logger.warning(f"Could not generate placeholder image for {product.sku}: {img_err}")

            # Inventory Inbound Movement
            qty = int(p.get('quantity', '0'))
            low_thresh = int(p.get('low_stock_threshold', '10'))

            if qty > 0:
                inbound_key = f"demo-import-{wh_default.code}-{product.sku}"
                StockService.record_stock_movement(
                    product=product,
                    warehouse=wh_default,
                    quantity_change=qty,
                    movement_type=StockMovement.MovementType.PURCHASE,
                    reason="Initial consignment from demo CSV marketplace import",
                    idempotency_key=inbound_key,
                    performed_by=admin_user,
                )
                summary['inventory_units_inbounded'] += qty
            else:
                WarehouseStock.objects.get_or_create(
                    warehouse=wh_default,
                    product=product,
                    defaults={'quantity': 0, 'reserved_quantity': 0, 'damaged_quantity': 0},
                )
                StockService.sync_catalog_inventory(product)

            # Configure catalog Inventory threshold
            inv, _ = Inventory.objects.get_or_create(
                product=product,
                defaults={'low_stock_threshold': low_thresh, 'quantity': qty},
            )
            if inv.low_stock_threshold != low_thresh:
                inv.low_stock_threshold = low_thresh
                inv.save(update_fields=['low_stock_threshold'])

            summary['products_created'] += 1
            summary['total_catalog_value'] += (price * qty)

        # 5. Ledger Reconciliation Verification
        discrepancies = StockService.reconcile_inventory()
        summary['discrepancies'] = len(discrepancies)

        # 6. Analytics Refresh (optional, non-dry-run)
        if not dry_run and not skip_analytics:
            try:
                from inventory.services import AlertService, ReplenishmentService
                AlertService.generate_all_alerts()
                ReplenishmentService.generate_all_suggestions()
            except Exception as an_err:
                logger.warning(f"Post-import analytics refresh encountered an error: {an_err}")

        return summary

    def print_summary(
        self,
        summary: Dict[str, Any],
        dry_run: bool = False,
        db_info: Optional[Dict[str, str]] = None,
    ):
        """Format and print structured execution metrics."""
        mode_str = "DRY RUN (Simulation - Rolled Back)" if dry_run else "LIVE (Committed)"
        backend_str = f"{db_info['engine']} ({db_info['host']})" if db_info else "unknown"

        self.stdout.write("\n" + "=" * 68)
        self.stdout.write("  SHOPSENSE DEMO MARKETPLACE IMPORT SUMMARY")
        self.stdout.write("=" * 68)
        self.stdout.write(f"  Target Database:             {backend_str}")
        self.stdout.write(f"  Execution Mode:              {mode_str}")
        self.stdout.write(f"  Vendors Processed:           {summary['vendors_total']} ({summary['vendors_created']} created, {summary['vendors_reused']} reused)")
        self.stdout.write(f"  Categories Processed:        {summary['categories_created']} created, {summary['categories_reused']} reused")
        self.stdout.write(f"  Products Processed:          {summary['products_total']} ({summary['products_created']} created, {summary['products_reused']} reused)")
        self.stdout.write(f"  Warehouse Units Inbounded:   {summary['inventory_units_inbounded']}")
        self.stdout.write(f"  Catalog Stock Value Added:   ₹{summary['total_catalog_value']:,.2f}")
        self.stdout.write(f"  Ledger Discrepancies:        {summary['discrepancies']}")
        self.stdout.write("=" * 68 + "\n")
