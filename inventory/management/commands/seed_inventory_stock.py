"""
Management command to seed realistic stock, warehouses, products, and sales history.
Uses StockService to ensure atomic ledger tracking, zero discrepancies,
and realistic data for alerts, replenishment, forecasting, and turnover.
"""

from decimal import Decimal
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from vendors.models import VendorProfile
from catalog.models import Category, Product, Inventory
from inventory.models import Warehouse, WarehouseStock, StockMovement
from inventory.services import (
    StockService,
    AlertService,
    ReplenishmentService,
    TurnoverService,
    ForecastService,
    CustomerAnalyticsService,
    RecommendationService,
)
from orders.models import Order, OrderItem, Payment

User = get_user_model()


class Command(BaseCommand):
    help = 'Add realistic stock across warehouses, inbound shipments, and sales history.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Starting inventory stock enrichment...'))

        # 1. Ensure Warehouses exist
        wh_default = StockService.get_or_create_default_warehouse()
        wh_west, _ = Warehouse.objects.get_or_create(
            code='WH-MUMBAI',
            defaults={
                'name': 'West Coast Fulfillment Hub',
                'city': 'Mumbai',
                'state': 'Maharashtra',
                'country': 'India',
                'status': Warehouse.Status.ACTIVE,
                'is_default': False,
            },
        )
        wh_north, _ = Warehouse.objects.get_or_create(
            code='WH-DELHI',
            defaults={
                'name': 'Northern Logistics Center',
                'city': 'New Delhi',
                'state': 'Delhi',
                'country': 'India',
                'status': Warehouse.Status.ACTIVE,
                'is_default': False,
            },
        )
        self.stdout.write(self.style.SUCCESS('Warehouses verified (Bangalore Default, Mumbai, Delhi).'))

        # 2. Get Vendors
        vendor_nexus = VendorProfile.objects.filter(vendor_id='VND10000001').first()
        if not vendor_nexus:
            vendor_nexus = VendorProfile.objects.first()

        vendor_sample = VendorProfile.objects.filter(vendor_id='VND07854220').first()
        if not vendor_sample:
            vendor_sample = vendor_nexus

        # 3. Categories
        cat_electronics, _ = Category.objects.get_or_create(
            name='Electronics',
            defaults={'slug': 'electronics', 'description': 'Gadgets and personal audio'},
        )
        cat_computers, _ = Category.objects.get_or_create(
            name='Computers & Accessories',
            parent=cat_electronics,
            defaults={'slug': 'computers-accessories', 'description': 'Laptops, monitors, and peripherals'},
        )
        cat_office, _ = Category.objects.get_or_create(
            name='Office Furniture',
            defaults={'slug': 'office-furniture', 'description': 'Ergonomic chairs and desks'},
        )

        # 4. Products with diversified stock targets
        products_config = [
            # High stock, fast-moving
            {
                'vendor': vendor_nexus,
                'category': cat_electronics,
                'name': 'Sony WH-1000XM5 Wireless Headphones',
                'sku': 'SONY-WH1000XM5-BLK',
                'price': Decimal('29990.00'),
                'description': 'Industry-leading noise cancelling wireless headphones with 30-hour battery life.',
                'stock_distribution': {wh_default: 50, wh_west: 30, wh_north: 20},
                'low_stock_threshold': 15,
            },
            {
                'vendor': vendor_nexus,
                'category': cat_computers,
                'name': 'Apple MacBook Air M2 (13-inch)',
                'sku': 'APPL-MBA-M2-256',
                'price': Decimal('99900.00'),
                'description': 'Strikingly thin design with M2 chip, 8GB unified memory, 256GB SSD.',
                'stock_distribution': {wh_default: 25, wh_west: 15, wh_north: 10},
                'low_stock_threshold': 10,
            },
            {
                'vendor': vendor_nexus,
                'category': cat_computers,
                'name': 'Logitech MX Master 3S Wireless Mouse',
                'sku': 'LOGI-MXM3S-GRY',
                'price': Decimal('8995.00'),
                'description': 'Performance wireless mouse with quiet clicks, 8K DPI sensor, and MagSpeed scroll.',
                'stock_distribution': {wh_default: 40, wh_west: 20, wh_north: 15},
                'low_stock_threshold': 12,
            },
            # Low stock target (triggers LOW_STOCK alert & replenishment suggestion)
            {
                'vendor': vendor_nexus,
                'category': cat_computers,
                'name': 'Dell UltraSharp 27 4K Monitor (U2723QE)',
                'sku': 'DELL-U2723QE-4K',
                'price': Decimal('54999.00'),
                'description': 'Brilliant 4K UHD IPS Black monitor with USB-C Hub connectivity.',
                'stock_distribution': {wh_default: 4, wh_west: 2, wh_north: 1},
                'low_stock_threshold': 12,
            },
            # Out of stock target (triggers CRITICAL OUT_OF_STOCK alert)
            {
                'vendor': vendor_sample,
                'category': cat_office,
                'name': 'Herman Miller Aeron Ergonomic Chair',
                'sku': 'HM-AERON-SIZE-B',
                'price': Decimal('125000.00'),
                'description': 'Pinnacle ergonomic office chair with breathable Pellicle suspension.',
                'stock_distribution': {wh_default: 0, wh_west: 0, wh_north: 0},
                'low_stock_threshold': 5,
            },
            # Healthy stock furniture
            {
                'vendor': vendor_sample,
                'category': cat_office,
                'name': 'Smart Standing Desk Pro (Electric)',
                'sku': 'DESK-STAND-PRO-OAK',
                'price': Decimal('34999.00'),
                'description': 'Dual-motor height adjustable motorized standing desk with solid oak top.',
                'stock_distribution': {wh_default: 18, wh_west: 8, wh_north: 6},
                'low_stock_threshold': 8,
            },
        ]

        products_created = 0
        stock_units_added = 0

        for cfg in products_config:
            product, created = Product.objects.get_or_create(
                sku=cfg['sku'],
                defaults={
                    'vendor': cfg['vendor'],
                    'category': cfg['category'],
                    'name': cfg['name'],
                    'slug': cfg['sku'].lower().replace('_', '-'),
                    'price': cfg['price'],
                    'description': cfg['description'],
                    'status': Product.Status.ACTIVE if sum(cfg['stock_distribution'].values()) > 0 else Product.Status.OUT_OF_STOCK,
                },
            )
            if created:
                products_created += 1

            # Inbound shipments via StockService
            for wh, target_qty in cfg['stock_distribution'].items():
                curr_stock = WarehouseStock.objects.filter(warehouse=wh, product=product).first()
                curr_qty = curr_stock.quantity if curr_stock else 0
                delta = target_qty - curr_qty
                if delta > 0:
                    StockService.record_stock_movement(
                        product=product,
                        warehouse=wh,
                        quantity_change=delta,
                        movement_type=StockMovement.MovementType.PURCHASE,
                        reason="Inbound vendor stock shipment",
                        idempotency_key=f"seed-inbound-{wh.code}-{product.sku}-batch2",
                    )
                    stock_units_added += delta

            # Update threshold on catalog Inventory
            if hasattr(product, 'inventory'):
                product.inventory.low_stock_threshold = cfg['low_stock_threshold']
                product.inventory.save(update_fields=['low_stock_threshold'])

        self.stdout.write(self.style.SUCCESS(
            f'Stock inbound completed: {products_created} new products, +{stock_units_added} total warehouse units added.'
        ))

        # 5. Seed historical qualifying sales over the past 30 days
        self.stdout.write(self.style.NOTICE('Seeding historical orders for demand forecasting and customer RFM...'))
        customers_data = [
            ('arjun.sharma@example.com', 'Arjun', 'Sharma'),
            ('priya.patel@example.com', 'Priya', 'Patel'),
            ('rohit.verma@example.com', 'Rohit', 'Verma'),
            ('ananya.iyer@example.com', 'Ananya', 'Iyer'),
            ('vikram.singh@example.com', 'Vikram', 'Singh'),
        ]

        customer_users = []
        for email, first, last in customers_data:
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'role': User.Role.CUSTOMER,
                    'is_active': True,
                },
            )
            if not user.password:
                user.set_password('ShopSense2026!')
                user.save()
            customer_users.append(user)

        now = timezone.now()
        active_prods = list(Product.objects.filter(status=Product.Status.ACTIVE))

        # Create 12 historical qualifying orders spread chronologically across last 28 days
        orders_seeded = 0
        for i in range(12):
            days_ago = (i * 2) + 1
            order_time = now - timedelta(days=days_ago, hours=(i % 5))
            customer = customer_users[i % len(customer_users)]
            prod = active_prods[i % len(active_prods)]
            qty = (i % 3) + 1

            order_num = f"ORD-{order_time:%Y%m%d}-{100 + i}"
            if not Order.objects.filter(order_number=order_num).exists():
                order = Order.objects.create(
                    order_number=order_num,
                    user=customer,
                    email=customer.email,
                    phone="+919876543210",
                    status=Order.Status.DELIVERED,
                    shipping_first_name=customer.first_name,
                    shipping_last_name=customer.last_name,
                    shipping_address="102 MG Road",
                    shipping_city="Bangalore",
                    shipping_state="Karnataka",
                    shipping_postal_code="560001",
                    shipping_country="India",
                    subtotal=prod.price * qty,
                    shipping_cost=Decimal('0.00'),
                    tax_amount=Decimal('0.00'),
                    total=prod.price * qty,
                    created_at=order_time,
                    confirmed_at=order_time,
                    delivered_at=order_time + timedelta(days=2),
                )
                OrderItem.objects.create(
                    order=order,
                    product=prod,
                    vendor=prod.vendor,
                    product_name=prod.name,
                    product_sku=prod.sku,
                    quantity=qty,
                    unit_price=prod.price,
                    total_price=prod.price * qty,
                    status=OrderItem.Status.DELIVERED,
                )
                Payment.objects.create(
                    order=order,
                    payment_id=f"PAY-{order_num}",
                    method=Payment.Method.UPI,
                    status=Payment.Status.COMPLETED,
                    amount=order.total,
                    created_at=order_time,
                )
                orders_seeded += 1

        self.stdout.write(self.style.SUCCESS(f'Seeded {orders_seeded} historical qualifying orders.'))

        # 6. Reconcile, evaluate, and refresh analytics
        self.stdout.write(self.style.NOTICE('Synchronizing stock reconciliation and running analytics refresh...'))
        discrepancies = StockService.reconcile_inventory()
        if discrepancies:
            self.stdout.write(self.style.WARNING(f'Discrepancies found: {len(discrepancies)}'))
        else:
            self.stdout.write(self.style.SUCCESS('Reconciliation clean: 0 discrepancies.'))

        alerts_count = AlertService.generate_all_alerts()
        self.stdout.write(self.style.SUCCESS(f'Generated {alerts_count} stock alerts.'))

        reorders_count = ReplenishmentService.generate_all_suggestions()
        self.stdout.write(self.style.SUCCESS(f'Generated {reorders_count} replenishment suggestions.'))

        forecasts_count = ForecastService.train_all_forecasts()
        self.stdout.write(self.style.SUCCESS(f'Trained {forecasts_count} demand forecast models.'))

        seg_results = CustomerAnalyticsService.segment_customers()
        self.stdout.write(self.style.SUCCESS(
            f"Segmented {seg_results.get('total_customers')} customers (Method: {seg_results.get('clustering_method')})."
        ))

        recs_count = RecommendationService.refresh_recommendation_candidates()
        self.stdout.write(self.style.SUCCESS(f'Refreshed {recs_count} recommendation candidates.'))

        self.stdout.write(self.style.SUCCESS('Inventory stock enrichment completed successfully!'))
