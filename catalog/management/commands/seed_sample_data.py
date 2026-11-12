"""
Management command to seed ShopSense with realistic sample data for testing/demo purposes.

This command creates:
- Vendor users with VendorProfile models
- Product categories (hierarchical)
- Products with realistic names, pricing, and inventory
- Customers with realistic Indian profiles
- Orders with order items and various statuses
- Payments linked to orders

Usage:
    python manage.py seed_sample_data

Options:
    --clear         Delete existing data before seeding
    --vendors N     Number of vendors to create (default: 8)
    --products N    Number of products per vendor (default: 6)
    --customers N   Number of customers to create (default: 15)
    --orders N      Number of orders to create (default: 30)
    --dry-run       Preview what would be created without saving

WARNING: This command is intended for development/staging environments only.
DO NOT run on production without explicit confirmation.
"""

import random
from decimal import Decimal
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction

from faker import Faker

from vendors.models import VendorApplication, VendorProfile
from catalog.models import Category, Product, ProductImage, Inventory
from accounts.models import User
from orders.models import Order, OrderItem, Payment


User = get_user_model()

# Indian data constants
INDIAN_CITIES = [
    ("Mumbai", "Maharashtra", "400001"),
    ("Delhi", "Delhi", "110001"),
    ("Bangalore", "Karnataka", "560001"),
    ("Hyderabad", "Telangana", "500001"),
    ("Chennai", "Tamil Nadu", "600001"),
    ("Kolkata", "West Bengal", "700001"),
    ("Pune", "Maharashtra", "411001"),
    ("Ahmedabad", "Gujarat", "380001"),
    ("Jaipur", "Rajasthan", "302001"),
    ("Surat", "Gujarat", "395001"),
]

BUSINESS_NAMES = [
    ("TechZone Electronics", "Electronics"),
    ("FashionHub", "Fashion"),
    ("HomeNest", "Home & Kitchen"),
    ("GlowBeauty", "Beauty & Personal Care"),
    ("FitZone Sports", "Sports & Fitness"),
    ("BookWorm", "Books & Stationery"),
    ("GreenGrocers", "Grocery"),
    ("PetCare India", "Pet Supplies"),
    ("Golden Furnishings", "Home & Kitchen"),
    ("UrbanThread", "Fashion"),
]

PRODUCT_DATA = {
    "Electronics": [
        ("Samsung Galaxy A54 5G", "Samsung", 24999, 35999),
        ("iPhone 15 Pro Max", "Apple", 134999, 159999),
        ("OnePlus Nord CE 3", "OnePlus", 26999, 31999),
        ("Redmi Note 13 Pro", "Xiaomi", 29999, 34999),
        ("Sony WH-1000XM5 Headphones", "Sony", 27990, 32990),
        ("boAt Airdopes 141 Earbuds", "boAt", 1499, 2499),
        ("Samsung Galaxy Tab S9", "Samsung", 69999, 84999),
        ("Canon EOS R50 Camera", "Canon", 74990, 89990),
        ("Logitech MX Master 3S Mouse", "Logitech", 7995, 9499),
        ("Asus ROG Zephyrus Laptop", "ASUS", 149999, 169999),
    ],
    "Fashion": [
        ("Classic Cotton T-Shirt", "Levi's", 1499, 1999),
        ("Denim Jeans", "Wrangler", 2999, 3999),
        ("Casual Shirt", "Van Heusen", 1799, 2499),
        ("Kurta Set", "Fabindia", 2499, 3499),
        ("Saree", "FabIndia", 3499, 5499),
        ("Leather Shoes", "Bata", 1999, 2999),
        ("Running Shoes", "Nike", 5999, 7999),
        ("Formal Shoes", "Clarks", 4999, 6999),
        ("Sunglasses", "Fastrack", 1499, 2499),
        ("Watch", "Titan", 3999, 6999),
    ],
    "Home & Kitchen": [
        ("Non-Stick Cookware Set", "Prestige", 2499, 3499),
        ("Mixer Grinder", "Philips", 4999, 7999),
        ("Electric Kettle", "Bajaj", 999, 1499),
        ("Bed Sheet Set", "Bombay Dyeing", 1299, 1999),
        ("Curtain Set", "HomeCentre", 1999, 3499),
        ("Dinner Set", "Cello", 1499, 2499),
        ("Wall Clock", "Ajanta", 999, 1999),
        ("Table Lamp", "Philips", 1499, 2499),
        ("Sofa Cover Set", "HomeCentre", 2499, 3999),
        ("Wall Clock", "Ajanta", 999, 1999),
    ],
    "Beauty & Personal Care": [
        "Face Wash",
        "Face Cream",
        "Shampoo",
        "Conditioner",
        "Lipstick",
        "Nail Polish",
        "Perfume",
        "Deodorant",
        "Body Lotion",
        "Face Mask",
    ],
    "Sports & Fitness": [
        "Cricket Bat",
        "Cricket Ball",
        "Football",
        "Basketball",
        "Yoga Mat",
        "Dumbbells",
        "Resistance Bands",
        "Skipping Rope",
        "Cricket Helmet",
        "Cricket Gloves",
    ],
    "Books & Stationery": [
        "Notebook Set",
        "Pen Set",
        "Notebook",
        "Pencil Set",
        "Eraser Set",
        "Sharpener Set",
        "Highlighter Set",
        "Notebook",
        "Pen Set",
        "Notebook",
    ],
    "Grocery": [
        "Basmati Rice (5kg)",
        "Wheat Flour (5kg)",
        "Sugar (1kg)",
        "Tea Leaves (250g)",
        "Cooking Oil (1L)",
        "Spices Set",
        "Tea Bags",
        "Coffee Powder (250g)",
        "Dry Fruits Pack",
        "Honey (500g)",
    ],
    "Pet Care": [
        "Dog Food (5kg)",
        "Cat Food (5kg)",
        "Dog Collar",
        "Cat Litter",
        "Dog Shampoo",
        "Cat Toy",
        "Dog Leash",
        "Pet Bed",
        "Cat Scratcher",
        "Pet Bowl Set",
    ],
}

PAYMENT_METHODS = ["CARD", "UPI", "NET_BANKING", "WALLET", "COD"]
PAYMENT_STATUSES = ["PENDING", "PROCESSING", "COMPLETED", "FAILED", "REFUNDED"]
ORDER_STATUSES = ["PENDING", "CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED", "CANCELLED", "REFUNDED"]
ORDER_STATUS_WEIGHTS = [0.05, 0.15, 0.20, 0.25, 0.30, 0.05]  # Pending, Confirmed, Processing, Shipped, Delivered, Cancelled


class Command(BaseCommand):
    help = "Seed ShopSense database with realistic sample data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--vendors",
            type=int,
            default=8,
            help="Number of vendors to create",
        )
        parser.add_argument(
            "--products-per-vendor",
            type=int,
            default=6,
            help="Number of products per vendor",
        )
        parser.add_argument(
            "--customers",
            type=int,
            default=15,
            help="Number of customers to create",
        )
        parser.add_argument(
            "--orders",
            type=int,
            default=30,
            help="Number of orders to create",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before seeding",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be created without saving",
        )

    def handle(self, *args, **options):
        self.fake = Faker("en_IN")
        self.vendors_count = options["vendors"]
        self.products_per_vendor = options["products_per_vendor"]
        self.customers_count = options["customers"]
        self.orders_count = options["orders"]
        self.dry_run = options["dry_run"]

        if options["clear"]:
            self.clear_data()

        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No data will be saved\n"))
            self.preview_counts()
            return

        with transaction.atomic():
            self.create_vendors()
            self.create_categories()
            self.create_products()
            self.create_customers()
            self.create_orders()

        self.stdout.write(self.style.SUCCESS("Successfully seeded sample data!"))
        self.print_summary()

    def clear_data(self):
        """Clear existing test data"""
        self.stdout.write("Clearing existing test data...")
        OrderItem.objects.all().delete()
        Order.objects.all().delete()
        Payment.objects.all().delete()
        Inventory.objects.all().delete()
        ProductImage.objects.all().delete()
        Product.objects.all().delete()
        Category.objects.all().delete()
        VendorProfile.objects.all().delete()
        User.objects.filter(role__in=[User.Role.VENDOR, User.Role.CUSTOMER]).delete()
        self.stdout.write("Cleared existing test data")

    def preview_counts(self):
        """Show what would be created"""
        self.stdout.write(f"Would create:")
        self.stdout.write(f"  - {self.vendors_count} vendors")
        self.stdout.write(f"  - ~{len(PRODUCT_DATA)} categories")
        self.stdout.write(f"  - {self.vendors_count * self.products_per_vendor} products")
        self.stdout.write(f"  - {self.customers_count} customers")
        self.stdout.write(f"  - {self.orders_count} orders")

    def create_vendors(self):
        """Create vendor users and vendor profiles"""
        self.stdout.write("Creating vendors...")

        for i, (business_name, category) in enumerate(
            BUSINESS_NAMES[: self.vendors_count]
        ):
            email = f"{business_name.lower().replace(' ', '')}@example.com"
            user = User.objects.create_user(
                email=email,
                password="VendorPass123!",
                first_name=business_name.split()[0],
                last_name="Vendor",
                role=User.Role.VENDOR,
                is_active=True,
                is_staff=False,
            )

            city_data = random.choice(INDIAN_CITIES)
            vendor = VendorProfile.objects.create(
                user=user,
                vendor_id=f"VND{str(i + 1).zfill(8)}",
                business_name=business_name,
                business_description=f"Premium {category.lower()} store in {city_data[0]}. Quality products at affordable prices.",
                contact_email=email,
                contact_phone=f"+91 {self.fake.numerify('##########')}",
                business_address=self.fake.street_address(),
                city=city_data[0],
                state=city_data[1],
                postal_code=city_data[2],
                country="India",
                tax_id=f"GST{self.fake.numerify('##########')}",
                website=f"https://www.{business_name.lower().replace(' ', '')}.com",
                is_active=True,
                is_verified=self.fake.boolean(chance_of_getting_true=70),
                commission_rate=Decimal(random.uniform(5.0, 15.0)),
            )
            self.stdout.write(f"  Created vendor: {vendor.business_name} ({vendor.vendor_id})")

    def create_categories(self):
        """Create product categories"""
        self.stdout.write("Creating categories...")

        categories_data = {
            "Electronics": [
                "Mobiles & Tablets",
                "Laptops & Computers",
                "Audio & Headphones",
                "Wearables",
                "Accessories",
            ],
            "Fashion": [
                "Men's Clothing",
                "Women's Clothing",
                "Footwear",
                "Accessories",
            ],
            "Home & Kitchen": [
                "Furniture",
                "Kitchen Appliances",
                "Home Decor",
                "Bedding",
            ],
            "Beauty & Personal Care": [
                "Skincare",
                "Haircare",
                "Makeup",
                "Fragrances",
            ],
            "Sports & Fitness": [
                "Sports Equipment",
                "Fitness Equipment",
                "Sports Apparel",
                "Sports Accessories",
            ],
            "Books & Stationery": [
                "Books",
                "Office Supplies",
                "Art Supplies",
            ],
            "Grocery": [
                "Grains & Pulses",
                "Spices",
                "Beverages",
                "Snacks",
                "Dry Fruits",
            ],
            "Pet Care": [
                "Dog Food",
                "Cat Food",
                "Pet Accessories",
                "Pet Toys",
                "Pet Grooming",
            ],
        }

        for parent_name, subcategories in categories_data.items():
            parent_category, _ = Category.objects.get_or_create(
                name=parent_name,
                defaults={
                    "slug": parent_name.lower().replace(" ", "-"),
                    "description": f"Shop for {parent_name.lower()} products at ShopSense",
                    "is_active": True,
                    "sort_order": len(Category.objects.all()),
                },
            )

            for sub_name in subcategories:
                Category.objects.get_or_create(
                    name=sub_name,
                    parent=parent_category,
                    defaults={
                        "slug": sub_name.lower().replace(" ", "-"),
                        "description": f"Shop for {sub_name.lower()} at ShopSense",
                        "is_active": True,
                        "sort_order": Category.objects.count(),
                    },
                )

        self.stdout.write(f"Created {Category.objects.count()} categories")

    def create_products(self):
        """Create products for each vendor"""
        self.stdout.write("Creating products...")

        vendors = list(VendorProfile.objects.all())
        categories = list(Category.objects.filter(parent__isnull=False))  # Subcategories only

        if not vendors:
            self.stdout.write(self.style.WARNING("No vendors found. Create vendors first."))
            return

        product_count = 0
        for vendor in vendors:
            vendor_categories = [
                c
                for c in categories
                if self.category_matches_vendor(c, vendor.business_name)
            ]
            if not vendor_categories:
                vendor_categories = categories

            for i in range(self.products_per_vendor):
                category = random.choice(vendor_categories)
                product_data = random.choice(PRODUCT_DATA.get(category.name, ["Generic Product"]))
                product_name = product_data if isinstance(product_data, str) else product_data[0]
                brand = (
                    product_data[1]
                    if isinstance(product_data, tuple)
                    else "Generic Brand"
                )
                price = (
                    random.randint(500, 50000)
                    if isinstance(product_data, str)
                    else product_data[2]
                )
                compare_price = None
                if random.random() < 0.4:
                    compare_price = price + random.randint(500, 5000)

                product = Product.objects.create(
                    vendor=vendor,
                    category=category,
                    name=product_name,
                    slug=f"{product_name.lower().replace(' ', '-')}-{vendor.vendor_id[-4:]}",
                    description=self.generate_product_description(product_name),
                    short_description=self.fake.text(max_chars=200),
                    sku=f"{vendor.vendor_id}-{product_name.upper().replace(' ', '')}-{i+1:03d}",
                    price=Decimal(str(price)),
                    compare_at_price=Decimal(str(compare_price)) if compare_price else None,
                    cost_price=Decimal(str(int(price * 0.7))),
                    status=random.choice(
                        ["ACTIVE", "ACTIVE", "ACTIVE", "INACTIVE", "OUT_OF_STOCK", "DRAFT"]
                    ),
                    is_featured=self.fake.boolean(chance_of_getting_true=20),
                    weight=Decimal(str(round(random.uniform(0.1, 5.0), 2))),
                    dimensions=f"{random.randint(10, 50)}x{random.randint(10, 50)}x{random.randint(5, 20)} cm",
                )

                # Create inventory
                Inventory.objects.create(
                    product=product,
                    quantity=random.randint(0, 100),
                    reserved_quantity=random.randint(0, 10),
                    low_stock_threshold=random.randint(5, 20),
                    track_quantity=True,
                    allow_backorder=self.fake.boolean(chance_of_getting_true=30),
                )

                product_count += 1

        self.stdout.write(f"Created {product_count} products")

    def category_matches_vendor(self, category, vendor_name):
        """Check if category matches vendor business type"""
        vendor_lower = vendor_name.lower()
        category_name = category.name.lower()
        category_parent = category.parent.name.lower() if category.parent else ""

        keyword_mapping = {
            "electronics": ["tech", "electronics", "computer", "mobile"],
            "fashion": ["fashion", "thread", "cloth", "garment", "apparel"],
            "home & kitchen": ["home", "kitchen", "nest", "furnish", "glass"],
            "beauty & personal care": ["glow", "beauty", "care", "cosmetic"],
            "sports & fitness": ["fit", "sport", "zone"],
            "books & stationery": ["book", "read", "paper", "station"],
            "grocery": ["grocery", "green", "fresh", "food"],
            "pet care": ["pet", "care", "animal"],
        }

        for key, keywords in keyword_mapping.items():
            if key in category_name.lower() or category_parent == key.lower():
                if any(keyword in vendor_lower for keyword in keywords):
                    return True
        return False

    def generate_product_description(self, product_name):
        """Generate a realistic product description"""
        templates = [
            "Premium {name} with excellent quality and performance. Perfect for daily use.",
            "High-quality {name} designed for comfort and durability. Best value for money.",
            "Premium quality {name} with modern design. Perfect for everyday use.",
            "Top-quality {name} built to last. Great value for your money.",
            "Premium {name} with superior quality and design.",
        ]
        return random.choice(templates).format(name=product_name)

    def create_customers(self):
        """Create customer users"""
        self.stdout.write("Creating customers...")

        for i in range(self.customers_count):
            first_name = self.fake.first_name()
            last_name = self.fake.last_name()
            email = f"{first_name.lower()}.{last_name.lower()}{i}@example.com"
            city_data = random.choice(INDIAN_CITIES)

            user = User.objects.create_user(
                email=email,
                password="CustomerPass123!",
                first_name=first_name,
                last_name=last_name,
                role=User.Role.CUSTOMER,
                is_active=True,
                is_staff=False,
                phone=f"+91 {self.fake.numerify('##########')}",
            )
            self.stdout.write(f"  Created customer: {user.get_full_name()} ({user.email})")

    def create_orders(self):
        """Create orders with items and payments"""
        self.stdout.write("Creating orders...")

        users = list(User.objects.filter(role=User.Role.CUSTOMER))
        products = list(Product.objects.filter(status="ACTIVE"))

        if not users or not products:
            self.stdout.write(self.style.WARNING("No users or products found for orders"))
            return

        for i in range(self.orders_count):
            user = random.choice(users)
            customer_products = random.sample(
                products, min(random.randint(1, 5), len(products))
            )

            # Calculate totals
            subtotal = Decimal("0")
            order_items_data = []
            for product in customer_products:
                quantity = random.randint(1, 5)
                total_price = product.price * quantity
                subtotal += total_price
                order_items_data.append((product, quantity, total_price))

            shipping_cost = Decimal(random.choice([0, 49, 99, 149]))
            tax_amount = Decimal(str(round(subtotal * 0.18, 2)))  # 18% GST
            discount_amount = Decimal(str(random.choice([0, 100, 250, 500])))
            total = subtotal + shipping_cost + tax_amount - discount_amount

            city_data = random.choice(INDIAN_CITIES)
            order_date = self.fake.date_time_between(
                start_date="-6m", end_date="now", tzinfo=timezone.get_current_timezone()
            )

            order = Order.objects.create(
                user=user,
                email=user.email,
                phone=f"+91 {self.fake.numerify('##########')}",
                status=random.choices(
                    ["PENDING", "CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED", "CANCELLED"],
                    weights=ORDER_STATUS_WEIGHTS,
                )[0],
                shipping_first_name=user.first_name,
                shipping_last_name=user.last_name,
                shipping_address=self.fake.street_address(),
                shipping_city=city_data[0],
                shipping_state=city_data[1],
                shipping_postal_code=city_data[2],
                shipping_country="India",
                billing_first_name=user.first_name,
                billing_last_name=user.last_name,
                billing_address=self.fake.street_address(),
                billing_city=city_data[0],
                billing_state=city_data[1],
                billing_postal_code=city_data[2],
                billing_country="India",
                subtotal=subtotal,
                shipping_cost=shipping_cost,
                tax_amount=tax_amount,
                discount_amount=discount_amount,
                total=total,
                created_at=order_date,
            )

            # Create order items
            for product, quantity, total_price in order_items_data:
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    vendor=product.vendor,
                    product_name=product.name,
                    product_sku=product.sku,
                    quantity=quantity,
                    unit_price=product.price,
                    total_price=total_price,
                )

            # Create payment
            payment_method = random.choices(
                PAYMENT_METHODS, weights=[0.25, 0.40, 0.20, 0.10, 0.05]
            )[0]
            payment_status = random.choices(
                ["PENDING", "PROCESSING", "COMPLETED", "FAILED", "REFUNDED"],
                weights=[0.10, 0.15, 0.60, 0.10, 0.05],
            )[0]

            # If order is cancelled, payment might be refunded
            if order.status == "CANCELLED":
                payment_status = random.choice(["REFUNDED", "FAILED"])

            Payment.objects.create(
                order=order,
                payment_id=f"PAY{random.randint(100000, 999999)}",
                method=payment_method,
                status=payment_status,
                amount=total,
                currency="INR",
                gateway_response={},
                created_at=order_date + timedelta(minutes=random.randint(1, 60)),
                completed_at=(
                    order_date + timedelta(minutes=random.randint(5, 30))
                    if payment_status == "COMPLETED"
                    else None
                ),
            )

        self.stdout.write(f"Created {self.orders_count} orders with items and payments")