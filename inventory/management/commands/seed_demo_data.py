"""
ShopSense Multi-Vendor Demo Data Generator.

Provides safe, repeatable, deterministic seeding of realistic marketplace data
across diverse vendor categories, products, inventory ledgers, customers, and orders.
"""

from datetime import timedelta
from decimal import Decimal
import io
import logging
import os
import re
import sys
from typing import Dict, Any, List, Optional, Tuple

from PIL import Image, ImageDraw
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import User
from catalog.models import Category, Inventory, Product, ProductImage
from inventory.models import (
    CustomerSegmentAssignment,
    ForecastModel,
    ForecastPrediction,
    LowStockAlert,
    RecommendationCandidate,
    ReplenishmentRequest,
    StockMovement,
    Warehouse,
    WarehouseStock,
)
from inventory.services import (
    AlertService,
    CustomerAnalyticsService,
    ForecastService,
    RecommendationService,
    ReplenishmentService,
    StockService,
)
from orders.models import Address, Order, OrderItem, Payment
from orders.views import calculate_order_financials
from vendors.models import AuditLog, VendorApplication, VendorProfile

User = get_user_model()
logger = logging.getLogger(__name__)

# Dedicated markers for safe identification and isolation
DEMO_EMAIL_DOMAIN = 'shopsense.demo'
DEMO_VENDOR_ID_PREFIX = 'VNDDEMO'
DEMO_SKU_PREFIX = 'DEMO-'
DEMO_ORDER_PREFIX = 'DEMO-ORD-'
DEMO_IDEMPOTENCY_PREFIX = 'demo-'
DEMO_PAYMENT_PREFIX = 'PAY-DEMO-'

# Explicitly prefixed passwords to ensure they are never confused with secure production credentials
DEMO_VENDOR_PASSWORD = 'DemoVendor2026!'
DEMO_CUSTOMER_PASSWORD = 'DemoCustomer2026!'

# Vendor Profiles Templates (8 Distinct Categories)
VENDOR_TEMPLATES = [
    {
        'category_name': 'Electronics & Gadgets',
        'category_slug': 'electronics-gadgets',
        'category_desc': 'Cutting-edge personal electronics, audio gear, computing accessories, and smart devices.',
        'vendor_id': 'VNDDEMO0001',
        'business_name': 'Apex Electronics & Gadgets',
        'business_description': 'Authorized distributor and manufacturer of high-performance electronics, personal audio, and smart peripherals.',
        'contact_email': 'demo.vendor.electronics@shopsense.demo',
        'contact_phone': '+91 98765 00001',
        'business_address': '401 Tech Park, Whitefield',
        'city': 'Bengaluru',
        'state': 'Karnataka',
        'postal_code': '560066',
        'country': 'India',
        'tax_id': '29ABCDE1234F1Z5',
        'website': 'https://apexelectronics.shopsense.demo',
        'commission_rate': Decimal('10.00'),
        'color': '#2563EB',  # Blue
        'sku_code': 'ELEC',
    },
    {
        'category_name': 'Fashion & Clothing',
        'category_slug': 'fashion-clothing',
        'category_desc': 'Contemporary men and women apparel, activewear, premium fabrics, and seasonal essentials.',
        'vendor_id': 'VNDDEMO0002',
        'business_name': 'Aura Threads & Apparel',
        'business_description': 'Contemporary fashion design studio focused on sustainable natural fabrics, smart casuals, and modern urban wear.',
        'contact_email': 'demo.vendor.fashion@shopsense.demo',
        'contact_phone': '+91 98765 00002',
        'business_address': '12 Fashion Street, Bandra West',
        'city': 'Mumbai',
        'state': 'Maharashtra',
        'postal_code': '400050',
        'country': 'India',
        'tax_id': '27BCDEF2345G2Z6',
        'website': 'https://aurathreads.shopsense.demo',
        'commission_rate': Decimal('12.00'),
        'color': '#7C3AED',  # Purple
        'sku_code': 'FASH',
    },
    {
        'category_name': 'Home & Kitchen',
        'category_slug': 'home-kitchen',
        'category_desc': 'Culinary cookware, artisanal homeware, kitchen appliances, and storage organizers.',
        'vendor_id': 'VNDDEMO0003',
        'business_name': 'Urban Haven Home & Living',
        'business_description': 'Curators of handcrafted kitchen essentials, heavy-gauge cookware, and ergonomic living solutions.',
        'contact_email': 'demo.vendor.home@shopsense.demo',
        'contact_phone': '+91 98765 00003',
        'business_address': '88 Green Park Main',
        'city': 'New Delhi',
        'state': 'Delhi',
        'postal_code': '110016',
        'country': 'India',
        'tax_id': '07CDEFG3456H3Z7',
        'website': 'https://urbanhaven.shopsense.demo',
        'commission_rate': Decimal('8.50'),
        'color': '#059669',  # Emerald
        'sku_code': 'HOME',
    },
    {
        'category_name': 'Beauty & Personal Care',
        'category_slug': 'beauty-personal-care',
        'category_desc': 'Dermatologically formulated skincare, organic hair care, grooming appliances, and wellness.',
        'vendor_id': 'VNDDEMO0004',
        'business_name': 'Glow & Radiance Botanicals',
        'business_description': 'Clean-label organic skincare and dermatological personal care crafted with botanical actives and essential vitamins.',
        'contact_email': 'demo.vendor.beauty@shopsense.demo',
        'contact_phone': '+91 98765 00004',
        'business_address': '22 Koregaon Park Road',
        'city': 'Pune',
        'state': 'Maharashtra',
        'postal_code': '411001',
        'country': 'India',
        'tax_id': '27DEFGH4567I4Z8',
        'website': 'https://glowradiance.shopsense.demo',
        'commission_rate': Decimal('14.00'),
        'color': '#DB2777',  # Pink
        'sku_code': 'BEAU',
    },
    {
        'category_name': 'Sports & Fitness',
        'category_slug': 'sports-fitness',
        'category_desc': 'Performance athletic gear, strength training equipment, recovery tools, and yoga accessories.',
        'vendor_id': 'VNDDEMO0005',
        'business_name': 'Stride Athletics & Fitness',
        'business_description': 'Professional-grade athletic equipment, modular home gym gear, and resistance conditioning accessories.',
        'contact_email': 'demo.vendor.sports@shopsense.demo',
        'contact_phone': '+91 98765 00005',
        'business_address': '55 Jubilee Hills Road No. 36',
        'city': 'Hyderabad',
        'state': 'Telangana',
        'postal_code': '500033',
        'country': 'India',
        'tax_id': '36EFGHI5678J5Z9',
        'website': 'https://strideathletics.shopsense.demo',
        'commission_rate': Decimal('11.00'),
        'color': '#EA580C',  # Orange
        'sku_code': 'SPRT',
    },
    {
        'category_name': 'Books & Stationery',
        'category_slug': 'books-stationery',
        'category_desc': 'Archival writing notebooks, precision pens, tech and design literature, and desktop organizers.',
        'vendor_id': 'VNDDEMO0006',
        'business_name': 'PageTurner Books & Stationery',
        'business_description': 'Specialty stationers and booksellers providing archival papers, fine writing instruments, and engineering books.',
        'contact_email': 'demo.vendor.books@shopsense.demo',
        'contact_phone': '+91 98765 00006',
        'business_address': '19 Anna Salai, T. Nagar',
        'city': 'Chennai',
        'state': 'Tamil Nadu',
        'postal_code': '600017',
        'country': 'India',
        'tax_id': '33FGHIJ6789K6Z0',
        'website': 'https://pageturner.shopsense.demo',
        'commission_rate': Decimal('7.50'),
        'color': '#0284C7',  # Sky blue
        'sku_code': 'BOOK',
    },
    {
        'category_name': 'Grocery & Daily Essentials',
        'category_slug': 'grocery-essentials',
        'category_desc': 'Single-origin pantry goods, cold-pressed oils, organic nuts, dry fruits, and gourmet staples.',
        'vendor_id': 'VNDDEMO0007',
        'business_name': 'FarmFresh Organics & Pantry',
        'business_description': 'Direct-from-farm single-origin spices, artisanal cold-pressed oils, and certified organic pantry essentials.',
        'contact_email': 'demo.vendor.grocery@shopsense.demo',
        'contact_phone': '+91 98765 00007',
        'business_address': '7 C-Scheme, Ashok Nagar',
        'city': 'Jaipur',
        'state': 'Rajasthan',
        'postal_code': '302001',
        'country': 'India',
        'tax_id': '08GHIJK7890L7Z1',
        'website': 'https://farmfreshorganics.shopsense.demo',
        'commission_rate': Decimal('6.00'),
        'color': '#16A34A',  # Green
        'sku_code': 'GROC',
    },
    {
        'category_name': 'Toys & Accessories',
        'category_slug': 'toys-accessories',
        'category_desc': 'STEM robotics kits, educational wooden puzzles, hobbyist models, and family board games.',
        'vendor_id': 'VNDDEMO0008',
        'business_name': 'WonderPlay Toys & Hobbies',
        'business_description': 'Inspiring young minds through STEM robotics, Montessori wooden tactile toys, and high-quality hobby kits.',
        'contact_email': 'demo.vendor.toys@shopsense.demo',
        'contact_phone': '+91 98765 00008',
        'business_address': '104 SG Highway, Bodakdev',
        'city': 'Ahmedabad',
        'state': 'Gujarat',
        'postal_code': '380054',
        'country': 'India',
        'tax_id': '24HIJKL8901M8Z2',
        'website': 'https://wonderplaytoys.shopsense.demo',
        'commission_rate': Decimal('12.50'),
        'color': '#D97706',  # Amber
        'sku_code': 'TOYS',
    },
]

# Product Catalog Templates for each of the 8 vendor types (25 realistic products per category)
PRODUCT_CATALOG = {
    'ELEC': [
        ('Active Noise-Cancelling Headphones Pro', 'Over-ear headphones with 40mm neodymium drivers, 35-hour battery life, and transparency mode.', 'Over-ear ANC headphones with 35h battery.', '24990.00', '29990.00', '15000.00', 0.28, '18x16x8'),
        ('GaN 65W Dual USB-C Fast Charger', 'Compact gallium nitride fast wall charger with Power Delivery 3.0 and intelligent power allocation.', 'Dual USB-C 65W compact GaN charger.', '2499.00', '3299.00', '1100.00', 0.12, '6x5x3'),
        ('Ultra HD 4K Action Camera 60FPS', 'Waterproof rugged action camera with electronic image stabilization and front selfie screen.', 'Waterproof 4K 60FPS dual-screen action cam.', '14499.00', '17999.00', '8500.00', 0.15, '7x5x4'),
        ('Ergonomic Mechanical Keyboard RGB', 'Hot-swappable custom red switches, PBT double-shot keycaps, and per-key RGB backlighting.', 'Mechanical RGB keyboard with hot-swap switches.', '6999.00', '8999.00', '3800.00', 0.95, '44x14x4'),
        ('AMOLED GPS Fitness Smartwatch', 'Always-on AMOLED display with continuous heart rate, SpO2 sensor, and 14-day battery reserve.', 'AMOLED GPS smartwatch with 14-day battery.', '8999.00', '11999.00', '4900.00', 0.05, '12x8x6'),
        ('Magnetic 10000mAh Wireless Power Bank', 'MagSafe compatible slim power bank with 15W wireless and 20W USB-C bidirectional fast charge.', '10000mAh magnetic wireless power bank.', '3499.00', '4499.00', '1800.00', 0.22, '10x7x2'),
        ('True Wireless Stereo Earbuds ANC', 'Hybrid active noise cancellation with 10mm dynamic drivers and wireless charging case.', 'Hybrid ANC earbuds with wireless charging.', '4999.00', '6999.00', '2600.00', 0.06, '6x5x3'),
        ('Vertical Ergonomic Wireless Mouse', 'Natural handshake grip design with Bluetooth 5.2 and adjustable optical sensor up to 4000 DPI.', 'Vertical ergonomic wireless mouse 4000 DPI.', '2799.00', '3499.00', '1350.00', 0.14, '11x7x8'),
        ('27-inch QHD 165Hz IPS Gaming Monitor', 'Fast IPS panel with 1ms response time, AMD FreeSync Premium, and 99% sRGB color gamut.', '27-inch QHD 165Hz 1ms IPS gaming display.', '24999.00', '31999.00', '16500.00', 5.80, '61x37x21'),
        ('8-in-1 Aluminum USB-C Hub Dock', 'Dual 4K HDMI, 100W Power Delivery pass-through, SD card reader, and Gigabit Ethernet.', 'Aluminum 8-in-1 USB-C hub with 100W PD.', '3999.00', '4999.00', '1950.00', 0.11, '12x4x2'),
        ('Smart 2K Home Security Camera', 'Pan-tilt indoor camera with 360-degree coverage, AI motion detection, and infrared night vision.', '2K 360-degree pan-tilt indoor camera.', '2999.00', '3999.00', '1400.00', 0.25, '11x8x8'),
        ('Waterproof Outdoor Bluetooth Speaker 20W', 'IPX7 waterproof rugged portable speaker with dual passive radiators and 12-hour playtime.', '20W IPX7 waterproof Bluetooth speaker.', '3499.00', '4499.00', '1700.00', 0.55, '18x7x7'),
        ('Aluminum Foldable Laptop Stand', 'Precision CNC-machined ventilated aluminum stand with six adjustable viewing angles.', 'Adjustable foldable aluminum laptop riser.', '1499.00', '1999.00', '650.00', 0.32, '26x6x2'),
        ('15W Qi Fast Wireless Car Mount', 'Auto-clamping motorized air vent mount with infrared sensor and rapid inductive charging.', '15W auto-clamping Qi wireless car charger.', '2199.00', '2899.00', '980.00', 0.18, '11x7x6'),
        ('Studio USB Condenser Microphone', 'Cardioid pickup pattern with internal pop filter, gain dial, zero-latency headphone monitoring.', 'Studio cardioid USB microphone with tripod.', '4999.00', '6499.00', '2400.00', 0.65, '20x10x8'),
        ('Wi-Fi 6 Dual-Band Mesh Router AX3000', 'Next-gen OFDMA Wi-Fi 6 speeds up to 3000 Mbps with coverage for over 2500 square feet.', 'AX3000 dual-band Wi-Fi 6 mesh router.', '5999.00', '7999.00', '3200.00', 0.75, '22x15x6'),
        ('Smart LED Desk Lamp with Wireless Charging', 'Flicker-free eye-care LED with adjustable color temperatures and integrated Qi charging pad.', 'Eye-care smart LED lamp with Qi pad.', '2999.00', '3799.00', '1350.00', 0.85, '40x15x15'),
        ('1TB PCIe 4.0 NVMe M.2 Internal SSD', 'Blazing fast sequential reads up to 7000 MB/s with graphene thermal heat spreader.', '1TB NVMe PCIe 4.0 SSD 7000 MB/s.', '7499.00', '9499.00', '4600.00', 0.04, '8x2x1'),
        ('Universal Travel Adapter with 4 USB Ports', 'All-in-one worldwide plug adapter supporting US, UK, EU, and AU sockets with safety shutter.', 'Universal travel power adapter with 4 USB.', '1299.00', '1699.00', '520.00', 0.16, '7x5x5'),
        ('Full HD 1080P Streaming Webcam', 'Autofocus wide-angle webcam with dual noise-reduction microphones and privacy slider.', '1080P 60FPS streaming webcam with shutter.', '2799.00', '3699.00', '1250.00', 0.15, '10x5x5'),
    ],
    'FASH': [
        ('Supima Cotton Crewneck T-Shirt', 'Made from 100% extra-long staple Supima cotton with double-needle stitching and ribbed collar.', 'Premium 100% Supima cotton crewneck tee.', '1299.00', '1699.00', '500.00', 0.20, '25x20x2'),
        ('Slim-Fit Stretch Denim Jeans', 'Classic indigo 5-pocket denim with 2% elastane for comfortable all-day flexibility.', 'Slim-fit stretch denim jeans in dark wash.', '2499.00', '3299.00', '1100.00', 0.65, '30x25x4'),
        ('Pure Linen Casual Long-Sleeve Shirt', 'Pre-washed breathable European flax linen shirt with relaxed button-down spread collar.', 'Pure European flax linen casual shirt.', '2899.00', '3799.00', '1300.00', 0.28, '30x22x3'),
        ('Merino Wool Lightweight Knit Sweater', 'Ultra-fine 19.5 micron Australian Merino wool knit providing natural temperature regulation.', 'Ultra-fine Merino wool crewneck sweater.', '4499.00', '5999.00', '2100.00', 0.35, '32x24x3'),
        ('Tailored Stretch Chino Trousers', 'Flat-front versatile cotton twill chinos tailored for professional office and weekend wear.', 'Flat-front stretch cotton tailored chinos.', '2199.00', '2899.00', '950.00', 0.45, '32x22x3'),
        ('Packable Down Puffer Jacket', 'Water-resistant ripstop shell insulated with 700 fill-power responsibly sourced down.', '700-fill packable down puffer jacket.', '5999.00', '7999.00', '2800.00', 0.48, '35x25x8'),
        ('Breathable Athletic Running Shorts', 'Moisture-wicking 4-way stretch shorts with built-in compression liner and zipped key pocket.', '4-way stretch running shorts with liner.', '1499.00', '1999.00', '600.00', 0.18, '22x18x2'),
        ('Heavyweight Fleece Pullover Hoodie', '400 GSM brushed fleece pullover hoodie with double-layer hood and kangaroo pouch.', '400 GSM heavyweight cotton fleece hoodie.', '2999.00', '3999.00', '1350.00', 0.70, '35x28x5'),
        ('Waterproof Double-Breasted Trench Coat', 'Classic trench coat with storm flap, buckled waist belt, and water-repellent gabardine weave.', 'Water-repellent classic belted trench coat.', '7999.00', '10999.00', '3900.00', 1.10, '40x30x6'),
        ('High-Waist Seamless Yoga Leggings', 'Squat-proof compression knit with ergonomic ribbed waistband and side smartphone pocket.', 'High-waist squat-proof seamless leggings.', '1799.00', '2399.00', '750.00', 0.22, '24x18x2'),
        ('Relaxed Linen Blend Summer Dress', 'Flowy A-line silhouette with mother-of-pearl buttons, self-tie belt, and hidden side pockets.', 'Linen blend relaxed A-line summer dress.', '3299.00', '4299.00', '1450.00', 0.32, '30x22x3'),
        ('Silk-Touch Floral Wrap Blouse', 'Elegant V-neck drape blouse with flared cuffs and adjustable wrap tie waist.', 'Floral print silk-touch wrap blouse.', '1999.00', '2699.00', '850.00', 0.20, '26x20x2'),
        ('Corduroy Vintage Overshirt Jacket', 'Heavy-wale cotton corduroy with brass snap buttons and dual chest utility pockets.', 'Heavy cotton corduroy overshirt jacket.', '3499.00', '4499.00', '1550.00', 0.65, '34x26x4'),
        ('Organic Cotton Cuffed Lounge Sweatpants', 'Soft French terry lounge joggers with deep front pockets and custom braided drawstring.', 'Organic French terry cuffed sweatpants.', '1899.00', '2499.00', '800.00', 0.42, '30x22x3'),
        ('Classic Oxford Cotton Button-Down', 'Durable basket-weave Oxford cloth with button-down collar and box pleat back.', 'Classic basket-weave Oxford casual shirt.', '1999.00', '2699.00', '850.00', 0.30, '30x22x3'),
        ('Quick-Dry Performance Golf Polo', 'Pique knit moisture-wicking polo with UPF 30+ sun protection and ribbed collar.', 'Moisture-wicking performance golf polo.', '1699.00', '2199.00', '700.00', 0.25, '26x20x2'),
        ('Full-Grain Reversible Leather Belt', 'Handcrafted genuine full-grain leather belt with swivel buckle switching black and cognac.', 'Full-grain reversible leather dress belt.', '1499.00', '1999.00', '580.00', 0.22, '15x15x4'),
        ('Thermal Cashmere Blend Knit Beanie', 'Ribbed cuff beanie crafted with wool and cashmere for superior winter insulation.', 'Cashmere blend ribbed thermal beanie.', '899.00', '1299.00', '340.00', 0.08, '18x15x2'),
        ('Waterproof Softshell Windbreaker', 'Fleece-backed breathable membrane shell with sealed zippers and adjustable drawcord hood.', 'Fleece-lined waterproof softshell jacket.', '4299.00', '5499.00', '1950.00', 0.68, '35x25x5'),
        ('Modal Cotton Seamless Boxer Briefs 3-Pack', 'Silky soft micro-modal fabric with anti-chafing flatlock seams and contour pouch.', '3-pack micro-modal seamless boxer briefs.', '1299.00', '1699.00', '520.00', 0.24, '20x15x4'),
    ],
    'HOME': [
        ('Pre-Seasoned Cast Iron Skillet 10.5-inch', 'Heavy-duty foundry cast iron skillet with dual pour spouts and ergonomic helper handle.', '10.5-inch pre-seasoned cast iron skillet.', '1899.00', '2499.00', '850.00', 2.40, '42x28x6'),
        ('Japanese High-Carbon Chef Knife 8-inch', 'Forged from AUS-10 high-carbon stainless steel with ergonomic pakkawood handle.', '8-inch AUS-10 Japanese steel chef knife.', '3499.00', '4699.00', '1500.00', 0.26, '38x8x3'),
        ('Borosilicate Glass Pour-Over Coffee Maker', 'Heat-resistant borosilicate carafe with laser-cut reusable stainless steel mesh filter.', '800ml borosilicate glass pour-over dripper.', '1699.00', '2199.00', '720.00', 0.45, '20x14x14'),
        ('Electric Gooseneck Precision Kettle 1.0L', 'Variable temperature dial with 60-minute keep-warm mode and precision gooseneck pour spout.', '1.0L variable temp electric gooseneck kettle.', '4499.00', '5799.00', '2100.00', 1.15, '28x22x20'),
        ('Organic Bamboo Cutting Board 3-Piece Set', 'Moso bamboo boards with deep juice groove, side handles, and anti-slip silicone feet.', '3-piece organic bamboo cutting board set.', '1499.00', '1999.00', '620.00', 1.80, '40x30x4'),
        ('Airtight Glass Food Storage Containers (Set of 6)', 'Thermal shock resistant borosilicate containers with BPA-free locking silicone lids.', '6-pack airtight glass food containers.', '2299.00', '2999.00', '1050.00', 2.90, '32x22x15'),
        ('Egyptian Cotton 400TC Sheet Set (Queen)', 'Loomed from 100% long-staple Egyptian cotton with silky sateen finish and deep pockets.', 'Queen 400TC Egyptian cotton sheet set.', '4999.00', '6499.00', '2200.00', 1.95, '35x28x8'),
        ('Ergonomic Contour Memory Foam Pillow', 'Orthopedic cervical neck support pillow with breathable washable cooling bamboo cover.', 'Orthopedic cervical memory foam pillow.', '1899.00', '2599.00', '800.00', 1.10, '55x35x12'),
        ('Matte Ceramic Dinnerware 16-Piece Set', 'Stoneware service for 4 including dinner plates, salad plates, cereal bowls, and mugs.', '16-piece matte finish ceramic dinner set.', '5499.00', '6999.00', '2500.00', 8.50, '42x35x32'),
        ('Stainless Steel Mixing Bowls with Lids', 'Nesting set of 5 deep bowls with non-skid silicone bottoms and measurement markings.', '5-piece nesting stainless mixing bowls.', '1999.00', '2699.00', '850.00', 1.70, '28x28x16'),
        ('Digital Touchscreen Air Fryer 5.5L', 'Rapid 360-degree hot air convection frying with 8 preset one-touch cooking programs.', '5.5L digital rapid-air convection fryer.', '5999.00', '7999.00', '2900.00', 4.80, '34x30x32'),
        ('Ultra-Absorbent Microfiber Bath Towel Set', 'Pack of 4 plush 600 GSM quick-drying towels with reinforced double-stitched hems.', '4-pack 600 GSM plush microfiber bath towels.', '1799.00', '2399.00', '780.00', 1.40, '32x25x10'),
        ('Hand-Poured Soy Aromatherapy Candle', 'Natural soy wax infused with French lavender, sandalwood, and cedarwood essential oils.', '300g French lavender natural soy candle.', '899.00', '1199.00', '350.00', 0.50, '10x9x9'),
        ('Stainless Steel Salt & Pepper Grinder Pair', 'Manual adjustable ceramic burr grinders with brushed stainless steel body and dust caps.', 'Pair of adjustable ceramic burr grinders.', '1199.00', '1599.00', '480.00', 0.52, '20x12x6'),
        ('Collapsible Canvas Laundry Hamper', 'Waterproof PE coated interior with sturdy faux leather carry handles and wire frame rim.', 'Large waterproof canvas laundry hamper.', '999.00', '1399.00', '410.00', 0.60, '40x30x55'),
        ('Silicone Heat-Resistant Utensil 10-Piece Set', 'Food-grade non-stick silicone heads with natural acacia wooden handles and storage crock.', '10-piece silicone and wood kitchen utensils.', '1699.00', '2299.00', '730.00', 0.85, '32x12x12'),
        ('Rustproof Stainless Steel Dish Drying Rack', 'Two-tier expandable dish drainer with removable cutlery holder and swivel spout.', '2-tier rustproof expandable dish drying rack.', '2499.00', '3299.00', '1100.00', 2.10, '44x32x16'),
        ('Ultrasonic Essential Oil Diffuser 500ml', 'Whisper-quiet cool mist humidifier with 7 soothing ambient LED lights and auto-shutoff.', '500ml ultrasonic aromatherapy LED diffuser.', '1899.00', '2499.00', '800.00', 0.58, '18x18x14'),
        ('Vacuum Insulated Tumbler 32oz', 'Double-wall food-grade 18/8 stainless steel tumbler with spill-proof straw lid.', '32oz double-wall insulated tumbler.', '1399.00', '1799.00', '580.00', 0.46, '24x10x10'),
        ('Heavy Duty Stainless Garlic Press & Peeler', 'Ergonomic heavy zinc alloy crusher with silicone garlic peeler tube and cleaning brush.', 'Stainless steel garlic press with peeler.', '799.00', '1099.00', '320.00', 0.28, '18x5x4'),
    ],
    'BEAU': [
        ('Vitamin C 20% Brightening Serum', 'Formulated with stabilized L-Ascorbic Acid, Ferulic Acid, and Hyaluronic Acid for collagen boost.', '20% Vitamin C serum with Ferulic Acid 30ml.', '899.00', '1299.00', '350.00', 0.12, '10x4x4'),
        ('Gentle Hydrating Ceramide Cleanser', 'Non-foaming face wash formulated with 3 essential ceramides and niacinamide for skin barrier.', 'Gentle non-foaming ceramide cleanser 200ml.', '699.00', '949.00', '270.00', 0.26, '18x6x4'),
        ('Ultra-Matte Mineral Sunscreen SPF 50+', 'Broad spectrum UVA/UVB physical zinc oxide shield with zero white cast and sebum control.', 'Mineral SPF 50+ matte sunscreen 50ml.', '749.00', '999.00', '290.00', 0.08, '12x4x3'),
        ('Deep Conditioning Argan Hair Mask', 'Cold-pressed Moroccan argan oil and hydrolyzed keratin intensive treatment for damaged hair.', 'Moroccan argan intensive hair mask 250ml.', '849.00', '1199.00', '340.00', 0.32, '9x9x8'),
        ('Nourishing Raw Shea Butter Cream', 'Unrefined African shea butter whipped with sweet almond oil and vitamin E for deep hydration.', 'Whipped raw shea butter body cream 250g.', '649.00', '899.00', '250.00', 0.30, '9x9x7'),
        ('Sonic Electric Toothbrush 40000 VPM', 'High-frequency sonic vibrations with 5 cleaning modes, 2-minute timer, and 4 replacement heads.', 'Sonic toothbrush with 4 brush heads & travel case.', '2499.00', '3299.00', '1050.00', 0.35, '22x10x5'),
        ('Organic Cold-Pressed Rosehip Seed Oil', '100% pure virgin cold-pressed oil rich in provitamin A and essential linolenic fatty acids.', 'Organic cold-pressed rosehip oil 30ml.', '799.00', '1099.00', '310.00', 0.10, '10x4x4'),
        ('AHA 30% + BHA 2% Peeling Solution', '10-minute exfoliating facial peeling mask targeting uneven texture, blackheads, and dullness.', 'AHA BHA exfoliating facial peel 30ml.', '699.00', '949.00', '260.00', 0.11, '10x4x4'),
        ('Clarifying Tea Tree & Salicylic Toner', 'Alcohol-free balancing facial astringent with Australian tea tree extract and witch hazel.', 'Tea tree and salicylic acid toner 150ml.', '549.00', '749.00', '210.00', 0.20, '16x5x5'),
        ('Peptide Multi-Action Eye Cream', 'Matrixyl 3000 and caffeine formulated cream reducing puffiness, fine lines, and dark circles.', 'Multi-peptide firming eye cream 15ml.', '949.00', '1299.00', '380.00', 0.06, '11x3x3'),
        ('Detoxifying Activated Charcoal Clay Mask', 'Kaolin and bentonite clay blended with bamboo charcoal to draw out deep impurities.', 'Activated charcoal detox clay mask 100g.', '599.00', '799.00', '230.00', 0.18, '8x8x6'),
        ('Biotin & Collagen Volumizing Shampoo', 'Sulfate-free thickening shampoo promoting hair density, scalp vitality, and root volume.', 'Biotin and collagen volume shampoo 350ml.', '749.00', '999.00', '290.00', 0.42, '20x6x6'),
        ('Coconut & Jojoba Hair Conditioner', 'Lightweight hydrating conditioner formulated with cold-pressed virgin coconut and jojoba oils.', 'Hydrating coconut and jojoba conditioner 350ml.', '749.00', '999.00', '290.00', 0.42, '20x6x6'),
        ('Tinted Lip Treatment Balm SPF 15', 'Nourishing beeswax and wild berry butter formula providing lasting moisture and sheer tint.', 'Wild berry tinted lip balm SPF 15.', '349.00', '499.00', '120.00', 0.03, '7x2x2'),
        ('Herbal Hand & Cuticle Repair Cream', 'Fast-absorbing non-greasy formula with chamomile extract, urea, and shea butter.', 'Herbal chamomile hand repair cream 75ml.', '449.00', '599.00', '160.00', 0.10, '14x4x3'),
        ('Natural Bamboo Paddle Hair Brush', 'Anti-static cushioned bamboo bristles that stimulate scalp microcirculation and detangle gently.', 'Eco-friendly bamboo paddle hair brush.', '599.00', '799.00', '220.00', 0.15, '24x8x4'),
        ('Silicone Sonic Facial Cleansing Brush', 'Waterproof sonic micro-pulse device with soft silicone bristles and adjustable speeds.', 'Waterproof sonic silicone facial cleanser.', '1499.00', '1999.00', '600.00', 0.18, '12x7x4'),
        ('Pure Epsom Salt Muscle Soak 1kg', 'Natural magnesium sulfate crystals scented with pure eucalyptus and spearmint essential oils.', 'Eucalyptus Epsom bath soaking salts 1kg.', '599.00', '799.00', '220.00', 1.05, '22x15x6'),
        ('Complete Beard Grooming Kit', 'Includes cedarwood beard oil, organic conditioning balm, pearwood comb, and boar bristle brush.', 'Cedarwood beard care kit with brush & comb.', '1499.00', '1999.00', '580.00', 0.35, '18x12x6'),
        ('Reusable Organic Cotton Makeup Pads (16-Pack)', 'Double-sided velvet bamboo and cotton rounds with mesh laundry wash bag.', '16-pack reusable bamboo cotton makeup pads.', '499.00', '699.00', '180.00', 0.12, '12x10x8'),
    ],
    'SPRT': [
        ('Eco-Friendly TPE Alignment Yoga Mat', 'Dual-layer textured non-slip surface with laser-etched posture alignment guidance lines.', '6mm non-slip eco TPE yoga alignment mat.', '1699.00', '2299.00', '700.00', 0.95, '65x13x13'),
        ('Adjustable Quick-Select Dumbbell 24kg', 'Rapid selector dial allowing quick weight adjustments from 2.5kg to 24kg with compact stand.', '24kg quick-select adjustable dumbbell.', '12999.00', '16999.00', '7500.00', 25.50, '44x22x23'),
        ('Heavy Resistance Band Set (5 Levels)', 'Stackable natural latex tube bands up to 150 lbs with foam handles, ankle straps, and door anchor.', '5-tube stackable resistance band home gym kit.', '1499.00', '1999.00', '620.00', 0.85, '24x18x8'),
        ('Deep Tissue High-Density Foam Roller', 'Molded grid trigger point matrix designed to relieve myofascial tightness and back tension.', '18-inch high-density trigger point foam roller.', '1099.00', '1499.00', '450.00', 0.65, '45x14x14'),
        ('Speed Jump Rope with Ball Bearings', 'Tangle-free steel cable with 360-degree high-speed dual ball bearings and aluminum handles.', 'Aluminum high-speed bearing jump rope.', '799.00', '1099.00', '310.00', 0.18, '18x12x3'),
        ('Half-Gallon Motivational Water Bottle 2.2L', 'BPA-free Tritan bottle with hourly time markers, silicone straw, and leakproof locking lid.', '2.2L motivational time-marked water bottle.', '999.00', '1399.00', '390.00', 0.32, '30x12x12'),
        ('Anti-Burst Professional Exercise Ball 65cm', 'Commercial-grade PVC honeycomb anti-burst structure with quick foot inflation pump.', '65cm anti-burst stability fitness ball.', '1199.00', '1599.00', '480.00', 1.10, '25x18x12'),
        ('Padded Weightlifting Gym Gloves', 'Microfiber padded palm with silicone grip traction and integrated 18-inch wrist wrap support.', 'Padded weightlifting gloves with wrist wrap.', '799.00', '1099.00', '300.00', 0.14, '16x12x3'),
        ('Dual-Wheel Core Abdominal Roller', 'Extra-wide stable wheels with non-skid rubber tread and high-density thick knee pad.', 'Dual-wheel ab roller with knee mat.', '899.00', '1249.00', '360.00', 0.80, '28x20x15'),
        ('Adjustable Ankle & Wrist Weights (2kg Pair)', 'Breathable neoprene weights with adjustable iron-sand pockets and reinforced velcro strap.', '2kg pair adjustable ankle wrist weights.', '1099.00', '1499.00', '450.00', 2.05, '25x12x8'),
        ('Running Hydration Waist Pack Belt', 'Bounce-free ergonomic pack with two 250ml water flasks, phone pocket, and reflective trim.', 'Bounce-free running hydration belt with flasks.', '1299.00', '1799.00', '520.00', 0.28, '32x14x4'),
        ('Waterproof Sports Gym Duffle Bag 40L', 'Ripstop nylon duffle with ventilated shoe compartment, wet towel pocket, and padded strap.', '40L waterproof gym duffle with shoe pocket.', '1999.00', '2699.00', '820.00', 0.75, '50x26x26'),
        ('Adjustable Hand Grip Strengthener (10-60kg)', 'Sturdy alloy spring with non-slip rubber grip and mechanical repetition counter.', 'Adjustable 10-60kg hand grip with counter.', '549.00', '799.00', '220.00', 0.18, '16x11x3'),
        ('Quick-Dry Microfiber Sports Towels (3-Pack)', 'Ultra-compact lightweight towels absorbing 4x their weight in water with hanging loop.', '3-pack quick-dry microfiber gym towels.', '799.00', '1099.00', '310.00', 0.28, '20x15x5'),
        ('Fabric Booty Resistance Loop Bands (Set of 3)', 'Durable woven fabric elastic bands with non-slip inner latex grips in three tension levels.', '3-pack non-slip fabric booty loop bands.', '899.00', '1299.00', '350.00', 0.38, '22x12x4'),
        ('Bluetooth Smart Body Fat Scale', 'High-precision BIA sensors measuring 13 body composition metrics with smartphone syncing.', 'Smart Bluetooth body composition scale.', '1899.00', '2499.00', '780.00', 1.45, '30x30x3'),
        ('Compression Knee Support Sleeve (Pair)', '3D circular knitted elastic brace with side stabilizers and silicone patella gel ring.', 'Pair of 3D knit knee compression sleeves.', '999.00', '1399.00', '390.00', 0.22, '22x14x3'),
        ('Agility Ladder & Training Cones Set', '6-meter 12-rung adjustable agility ladder with 10 marker cones and carrying bag.', '6m speed agility ladder and 10 cones set.', '1199.00', '1599.00', '480.00', 0.95, '45x12x8'),
        ('Deep Tissue Percussion Massage Gun', 'Brushless motor delivering 3200 percussions per minute with 6 speeds and 4 massage heads.', '6-speed deep tissue percussion massage gun.', '3499.00', '4799.00', '1550.00', 1.15, '26x22x8'),
        ('Foldable Gymnastics & Exercise Mat', '2-inch thick high-density EPE foam tri-fold mat with puncture-resistant PU leather cover.', 'Tri-fold 2-inch thick exercise floor mat.', '2999.00', '3999.00', '1300.00', 2.80, '60x60x16'),
    ],
    'BOOK': [
        ('Hardcover Dotted Grid Journal A5', '160 GSM thick bleedproof bamboo paper with numbered pages, inner pocket, and bookmark ribbons.', 'A5 hardcover 160 GSM dotted grid journal.', '899.00', '1199.00', '350.00', 0.42, '21x15x2'),
        ('Brass Classic Fountain Pen Medium Nib', 'Weighted solid brass barrel with German iridium nib, ink converter, and 6 ink cartridges.', 'Solid brass classic fountain pen with converter.', '1699.00', '2299.00', '680.00', 0.16, '18x6x3'),
        ('Ergonomic Gel Ink Pens 0.5mm (Set of 10)', 'Quick-drying Japanese archival pigment ink with rubberized comfort grip.', '10-pack 0.5mm black gel ink pens.', '499.00', '699.00', '180.00', 0.12, '15x10x2'),
        ('Pastel Aesthetic Chisel Highlighters (6-Pack)', 'Soft water-based pastel pigments that do not bleed through thin paper or Bible pages.', '6-pack soft pastel aesthetic highlighters.', '399.00', '549.00', '140.00', 0.09, '14x8x2'),
        ('The Pragmatic Software Architect (Hardcover)', 'Essential technical handbook covering distributed architectures, scalability, and resilience.', 'The Pragmatic Software Architect book.', '1499.00', '1899.00', '650.00', 0.72, '24x17x4'),
        ('Clean Code Patterns & Refactoring Guide', 'Comprehensive practical patterns for writing maintainable, readable enterprise software.', 'Clean Code Patterns & Refactoring Guide.', '1299.00', '1699.00', '550.00', 0.65, '23x16x3'),
        ('System Design Interview Blueprint', 'Step-by-step frameworks for designing high-concurrency cloud native systems.', 'System Design Interview Blueprint book.', '1399.00', '1799.00', '600.00', 0.68, '24x17x3'),
        ('Adjustable Bamboo Desktop Bookstand', 'Natural bamboo book holder with spring page clips and 5 adjustable reading angles.', 'Adjustable bamboo desktop book reading stand.', '1199.00', '1599.00', '480.00', 0.85, '34x24x4'),
        ('Pastel Sticky Notes Cube (400 Sheets)', 'Heavyweight self-adhesive note cube with strong repositionable adhesive.', '400-sheet pastel self-adhesive notes cube.', '349.00', '499.00', '120.00', 0.22, '8x8x5'),
        ('Metal Mesh Multi-Compartment Desk Organizer', 'Sturdy steel mesh organizer with 6 divided slots and a pull-out sliding drawer.', '6-compartment metal mesh desk organizer.', '899.00', '1199.00', '360.00', 0.65, '22x14x13'),
        ('Dual-Sided Waterproof Leather Desk Pad (80x40cm)', 'Smooth PU leather desk blotter that protects desk surfaces from scratches and spills.', '80x40cm dual-sided PU leather desk pad.', '999.00', '1399.00', '400.00', 0.45, '42x6x6'),
        ('Self-Healing Rotary Cutting Mat A3', 'Double-sided 5-ply PVC mat with precise metric grid guidelines and angle markings.', 'A3 self-healing double-sided cutting mat.', '799.00', '1099.00', '310.00', 0.55, '45x30x1'),
        ('Precision Stainless Steel Rulers (15cm & 30cm)', 'Non-skid cork-backed rulers with laser-etched metric and imperial measurement scales.', 'Pair of cork-backed stainless steel rulers.', '399.00', '549.00', '140.00', 0.15, '33x4x1'),
        ('Watercolor Paint Studio Set (36 Colors)', 'Richly pigmented artist pans with refillable water brush pen and built-in mixing palette.', '36-color artist watercolor paint pan set.', '1299.00', '1799.00', '520.00', 0.40, '22x14x3'),
        ('Acid-Free Mixed Media Art Sketchbook', 'Spiral-bound 200 GSM cold-press heavy paper suitable for ink, gouache, and pencils.', 'Spiral-bound A4 200 GSM mixed media pad.', '699.00', '949.00', '270.00', 0.58, '30x21x2'),
        ('Vintage Brass Wax Seal Stamp Kit', 'Includes wooden handle brass stamp, 200 wax beads, melting spoon, and metallic pens.', 'Vintage brass wax sealing kit with spoon.', '999.00', '1399.00', '390.00', 0.32, '20x15x4'),
        ('Weekly Productivity Planner (Undated)', '12-month priority habit tracker with weekly planning spreads and reflection prompts.', 'Undated weekly productivity habit planner.', '799.00', '1099.00', '320.00', 0.38, '22x16x2'),
        ('Magnetic Dry-Erase Desktop Whiteboard', 'Dual-sided wedge easel whiteboard with 4 fine-tip dry erase markers and eraser.', 'Desktop magnetic dry-erase easel board.', '1099.00', '1499.00', '450.00', 0.70, '30x22x4'),
        ('Memory Foam Ergonomic Keyboard Wrist Rest', 'Contoured cooling memory foam support with non-slip polyurethane base.', 'Ergonomic memory foam keyboard wrist rest.', '699.00', '949.00', '260.00', 0.28, '44x8x3'),
        ('Pigment Fineliner Drawing Pens (Pack of 8)', 'Waterproof fade-proof micro-pigment ink ranging from 0.05mm to 0.8mm and brush tip.', '8-pack micro pigment black fineliners.', '749.00', '999.00', '280.00', 0.11, '15x10x2'),
    ],
    'GROC': [
        ('Single-Origin Arabica Whole Coffee Beans 500g', 'Hand-picked shade-grown Arabica from Coorg roasted to a balanced medium profile.', '500g single-origin Coorg Arabica coffee beans.', '699.00', '899.00', '320.00', 0.52, '24x14x8'),
        ('Darjeeling First Flush Loose Black Tea 250g', 'Muscatel floral notes from high-altitude tea gardens packed in an airtight tin canister.', '250g Darjeeling first flush loose leaf tea.', '799.00', '999.00', '360.00', 0.35, '14x9x9'),
        ('Raw Organic Wildflower Honey 500g', 'Unfiltered unpasteurized honey harvested from Himalayan forests retaining natural pollen.', '500g unfiltered raw wildflower honey jar.', '549.00', '699.00', '240.00', 0.75, '14x8x8'),
        ('Cold-Pressed Extra Virgin Olive Oil 1L', 'First cold-pressed olives from Mediterranean groves with acidity strictly below 0.3%.', '1L dark glass bottle extra virgin olive oil.', '1399.00', '1799.00', '680.00', 1.40, '28x8x8'),
        ('California Whole Raw Almonds 500g', 'Grade A natural nonpareil almonds rich in vitamin E, protein, and dietary fiber.', '500g vacuum sealed raw whole almonds.', '599.00', '799.00', '280.00', 0.52, '20x15x5'),
        ('Organic Rolled Whole Oats 1kg', 'Certified gluten-free thick-cut whole grain rolled oats packed with soluble beta-glucan.', '1kg organic gluten-free rolled oats pouch.', '399.00', '499.00', '180.00', 1.05, '26x18x8'),
        ('Pure Kashmiri Mongra Saffron 1g', 'Grade A1 all-red stigmas delivering intense aroma, vibrant golden color, and natural flavor.', '1g certified authentic Kashmiri saffron.', '499.00', '649.00', '210.00', 0.02, '8x6x2'),
        ('Himalayan Pink Rock Salt Coarse 1kg', 'Unrefined mineral-rich ancient rock salt crystals suitable for grinders and cooking.', '1kg coarse Himalayan pink rock salt pouch.', '199.00', '299.00', '80.00', 1.02, '20x14x6'),
        ('Organic Raw Chia Seeds 500g', 'Raw black chia seeds loaded with plant-based Omega-3 fatty acids, calcium, and antioxidants.', '500g organic black raw chia seeds pouch.', '349.00', '449.00', '150.00', 0.52, '18x12x5'),
        ('Organic Tricolor Quinoa 1kg', 'Blend of white, red, and black pre-washed quinoa grains providing complete plant protein.', '1kg pre-washed organic tricolor quinoa.', '549.00', '699.00', '250.00', 1.05, '22x16x7'),
        ('Ceremonial Grade Matcha Green Tea 50g', 'First harvest stone-ground Japanese Uji tencha tea leaves packed in sealed foil tin.', '50g ceremonial grade Uji matcha green tea.', '999.00', '1299.00', '450.00', 0.12, '8x7x7'),
        ('Artisanal 70% Dark Chocolate Bar (Pack of 3)', 'Single-origin South Indian cacao bean-to-bar chocolate sweetened with unrefined cane sugar.', '3-pack 70% single-origin dark chocolate.', '499.00', '649.00', '220.00', 0.28, '18x9x3'),
        ('Organic Raw Walnut Halves 400g', 'Crisp vacuum-packed light walnut halves rich in neuro-protective ALA Omega-3 fats.', '400g vacuum sealed raw walnut halves.', '649.00', '849.00', '310.00', 0.42, '20x14x6'),
        ('Roasted Pumpkin & Sunflower Seeds 250g', 'Lightly pink-salted superfood seeds mix roasted gently without added hydrogenated oils.', '250g roasted pumpkin and sunflower seeds mix.', '299.00', '399.00', '130.00', 0.28, '16x12x4'),
        ('Virgin Cold-Pressed Coconut Oil 500ml', 'Extracted from fresh coconut milk using cold centrifugation, unbleached and non-deodorized.', '500ml glass jar cold-pressed virgin coconut oil.', '449.00', '599.00', '190.00', 0.72, '16x8x8'),
        ('Organic Whole Golden Flaxseeds 500g', 'Naturally high in lignans and dietary fiber, ideal for smoothies, baking, and oat bowls.', '500g organic whole golden flaxseeds.', '249.00', '349.00', '110.00', 0.52, '18x12x5'),
        ('Sun-Dried Mediterranean Figs 400g', 'Naturally sweet tender dried figs with zero added sugar and no sulfur preservatives.', '400g premium sun-dried tender figs pouch.', '499.00', '649.00', '230.00', 0.42, '18x14x5'),
        ('Raw Apple Cider Vinegar with Mother 500ml', 'Unpasteurized unfiltered vinegar fermented from organically grown Himalayan crisp apples.', '500ml raw apple cider vinegar with mother.', '349.00', '449.00', '140.00', 0.85, '22x7x7'),
        ('Ayurvedic Golden Milk Turmeric Blend 200g', 'Lakadong high-curcumin turmeric blended with ginger, black pepper, and green cardamom.', '200g organic golden milk turmeric latte mix.', '399.00', '499.00', '160.00', 0.25, '12x8x8'),
        ('Jumbo Medjool Dates 500g', 'Caramel-sweet soft king dates hand-selected and packed fresh from the harvest.', '500g box of jumbo sweet Medjool dates.', '699.00', '899.00', '330.00', 0.55, '20x15x5'),
    ],
    'TOYS': [
        ('Architectural Building Blocks Set (750 Pcs)', 'Precision-molded interlocking bricks for building historic landmarks and modern skyscrapers.', '750-piece architectural landmark building bricks.', '2499.00', '3299.00', '1100.00', 1.45, '36x28x8'),
        ('STEM Programmable Robotics Rover Kit', 'Bluetooth educational rover kit with ultrasonic obstacle sensor, line tracker, and graphical coding.', 'STEM programmable robotics rover kit.', '3999.00', '5299.00', '1800.00', 0.95, '28x20x7'),
        ('3D Magnetic Construction Tiles (100 Pcs)', 'Ultrasonic welded food-grade ABS geometric tiles with strong internal neodymium magnets.', '100-piece 3D magnetic building tiles set.', '2199.00', '2899.00', '950.00', 2.10, '32x24x9'),
        ('Montessori Wooden Shape Sorting Puzzle', 'Natural solid beechwood sensory puzzle with water-based non-toxic pastel paints.', 'Montessori solid wooden geometric sorting puzzle.', '899.00', '1199.00', '380.00', 0.65, '22x18x6'),
        ('Motorized Solar System Planetarium Kit', 'Rotating mechanical model with sun projector light and 8 orbiting planets to assemble and paint.', 'Motorized rotating solar system planetarium.', '1499.00', '1999.00', '620.00', 0.80, '30x22x9'),
        ('Refractor Astronomical Telescope 50mm', 'Beginner stargazing telescope with 50mm coated glass objective, finder scope, and aluminum tripod.', '50mm astronomical telescope with tripod.', '3299.00', '4299.00', '1450.00', 1.65, '45x22x11'),
        ('Classic Wooden Chess & Checkers Set 15-inch', 'Folding walnut wood board with felted interior storage slots and handcrafted Staunton pieces.', '15-inch folding walnut chess & checkers set.', '1799.00', '2399.00', '780.00', 1.25, '38x20x6'),
        ('High-Speed RC Drift Car 1:16 Scale', 'Proportional 2.4GHz remote control racer reaching 25 km/h with LED headlights and extra drift tires.', '1:16 scale 2.4GHz high-speed RC drift car.', '2699.00', '3499.00', '1200.00', 0.85, '30x16x10'),
        ('Kids Monocular Microscope Lab Kit', 'Metal frame student microscope with 100x-1200x magnification, prepared slides, and specimen tools.', '1200x student microscope experiment lab kit.', '1999.00', '2599.00', '880.00', 1.30, '32x24x12'),
        ('Deluxe Wooden Art & Coloring Studio (120 Pcs)', 'Solid wood carrying chest with watercolors, colored pencils, oil pastels, and sketching pads.', '120-piece deluxe art studio in wooden chest.', '1899.00', '2499.00', '820.00', 1.70, '38x26x5'),
        ('Interactive Touch-Sensitive Robot Puppy', 'Voice-responsive robotic pet that barks, dances, and follows hand gestures with LED eyes.', 'Interactive smart gesture robot puppy.', '2299.00', '2999.00', '980.00', 0.75, '22x18x15'),
        ('1000-Piece Panoramic Landscape Puzzle', 'Precision-cut glare-free recycled cardboard puzzle featuring high-resolution nature landscape.', '1000-piece panoramic landscape jigsaw puzzle.', '799.00', '1099.00', '320.00', 0.82, '37x27x5'),
        ('Wooden Railway Train Track Set (40 Pcs)', 'Solid beechwood modular track with magnetic engine, freight cars, suspension bridge, and station.', '40-piece wooden railway train and bridge set.', '2199.00', '2899.00', '960.00', 1.85, '35x25x8'),
        ('Kinetic Sensory Play Sand Kit (1kg)', 'Natural non-drying kinetic modeling sand with 10 castle sculpting molds and foldable play tray.', '1kg non-drying kinetic sensory sand with molds.', '899.00', '1199.00', '360.00', 1.35, '26x20x6'),
        ('Glow-in-the-Dark Constellation Galaxy Stars', '200 luminous 3D celestial stars and planets with safe removable adhesive mounting putty.', '200-piece glow-in-the-dark galaxy stars set.', '499.00', '699.00', '180.00', 0.16, '16x12x3'),
        ('Flying Hover Orb Drone with RGB Lights', '360-degree infrared sensor boomerang sphere with vibrant dynamic lighting and USB charge.', 'Flying boomerang hover orb drone with RGB.', '1299.00', '1799.00', '520.00', 0.15, '10x10x10'),
        ('Montessori 8-Note Wooden Xylophone', 'Tuned multi-colored aluminum keys securely fastened to natural hardwood base with wooden mallets.', 'Tuned 8-note wooden xylophone with mallets.', '749.00', '999.00', '290.00', 0.55, '26x12x5'),
        ('Kids Outdoor Gardening & Exploration Tool Set', 'Real metal hand trowel, fork, watering can, gardening gloves, and canvas multi-pocket tote.', 'Kids metal gardening tool tote bag set.', '999.00', '1399.00', '410.00', 0.70, '25x20x12'),
        ('Pop-Up Castle Indoor Play Tent', 'Foldable breathable polyester tent with roll-up door, mesh windows, and lightweight carry case.', 'Pop-up indoor castle play tent with carry case.', '1499.00', '1999.00', '630.00', 1.05, '40x40x5'),
        ('DIY Crystal Growing Science Lab', 'Chemical crystallization experiment creating 6 vibrant colorful geological crystal formations.', 'DIY 6-crystal growing chemistry science lab.', '899.00', '1199.00', '370.00', 0.65, '22x16x6'),
    ],
}

# Customer Seed Names and Addresses
CUSTOMER_SEED_DATA = [
    ('demo.customer01@shopsense.demo', 'Aarav', 'Sharma', '+91 98765 10001', '101 Indiranagar 100 Feet Road', 'Bengaluru', 'Karnataka', '560038'),
    ('demo.customer02@shopsense.demo', 'Diya', 'Patel', '+91 98765 10002', '45 Linking Road, Khar West', 'Mumbai', 'Maharashtra', '400052'),
    ('demo.customer03@shopsense.demo', 'Rohan', 'Iyer', '+91 98765 10003', '78 Basant Lok, Vasant Vihar', 'New Delhi', 'Delhi', '110057'),
    ('demo.customer04@shopsense.demo', 'Priya', 'Nair', '+91 98765 10004', '12 Kalyani Nagar Main Road', 'Pune', 'Maharashtra', '411006'),
    ('demo.customer05@shopsense.demo', 'Vikram', 'Singh', '+91 98765 10005', '89 Road No. 45, Jubilee Hills', 'Hyderabad', 'Telangana', '500033'),
    ('demo.customer06@shopsense.demo', 'Ananya', 'Deshmukh', '+91 98765 10006', '33 TTK Road, Alwarpet', 'Chennai', 'Tamil Nadu', '600018'),
    ('demo.customer07@shopsense.demo', 'Kabir', 'Mehta', '+91 98765 10007', '15 MI Road, C-Scheme', 'Jaipur', 'Rajasthan', '302001'),
    ('demo.customer08@shopsense.demo', 'Neha', 'Reddy', '+91 98765 10008', '56 Vastrapur Lake Road', 'Ahmedabad', 'Gujarat', '380015'),
    ('demo.customer09@shopsense.demo', 'Aditya', 'Verma', '+91 98765 10009', '14 Park Street, Flat 4B', 'Kolkata', 'West Bengal', '700016'),
    ('demo.customer10@shopsense.demo', 'Sneha', 'Kulkarni', '+91 98765 10010', '27 Mall Road, Civil Lines', 'Gurugram', 'Haryana', '122001'),
    ('demo.customer11@shopsense.demo', 'Arjun', 'Bhat', '+91 98765 10011', '62 Koramangala 4th Block', 'Bengaluru', 'Karnataka', '560034'),
    ('demo.customer12@shopsense.demo', 'Meera', 'Pillai', '+91 98765 10012', '19 Juhu Tara Road', 'Mumbai', 'Maharashtra', '400049'),
    ('demo.customer13@shopsense.demo', 'Rahul', 'Saxena', '+91 98765 10013', '90 Defense Colony, Ring Road', 'New Delhi', 'Delhi', '110024'),
    ('demo.customer14@shopsense.demo', 'Pooja', 'Menon', '+91 98765 10014', '34 Aundh Road', 'Pune', 'Maharashtra', '411007'),
    ('demo.customer15@shopsense.demo', 'Karthik', 'Rao', '+91 98765 10015', '41 Madhapur HITEC City', 'Hyderabad', 'Telangana', '500081'),
    ('demo.customer16@shopsense.demo', 'Ritu', 'Sen', '+91 98765 10016', '50 Salt Lake Sector 1', 'Kolkata', 'West Bengal', '700064'),
    ('demo.customer17@shopsense.demo', 'Siddharth', 'Joshi', '+91 98765 10017', '18 Navrangpura Cross Road', 'Ahmedabad', 'Gujarat', '380009'),
    ('demo.customer18@shopsense.demo', 'Kavita', 'Bansal', '+91 98765 10018', '7 Raja Park Main Market', 'Jaipur', 'Rajasthan', '302004'),
    ('demo.customer19@shopsense.demo', 'Manish', 'Gupta', '+91 98765 10019', '88 Sector 18 Commercial Belt', 'Noida', 'Uttar Pradesh', '201301'),
    ('demo.customer20@shopsense.demo', 'Swati', 'Choudhury', '+91 98765 10020', '23 Anna Nagar 2nd Avenue', 'Chennai', 'Tamil Nadu', '600040'),
    ('demo.customer21@shopsense.demo', 'Varun', 'Malhotra', '+91 98765 10021', '105 HSR Layout Sector 2', 'Bengaluru', 'Karnataka', '560102'),
    ('demo.customer22@shopsense.demo', 'Tanvi', 'Hegde', '+91 98765 10022', '31 Powai Hiranandani', 'Mumbai', 'Maharashtra', '400076'),
    ('demo.customer23@shopsense.demo', 'Gaurav', 'Kapoor', '+91 98765 10023', '72 Greater Kailash Part 1', 'New Delhi', 'Delhi', '110048'),
    ('demo.customer24@shopsense.demo', 'Shreya', 'Chatterjee', '+91 98765 10024', '14 Ballygunge Circular Road', 'Kolkata', 'West Bengal', '700019'),
    ('demo.customer25@shopsense.demo', 'Nikhil', 'Gokhale', '+91 98765 10025', '6 Baner-Pashan Link Road', 'Pune', 'Maharashtra', '411045'),
]


def get_sanitized_db_info() -> Dict[str, str]:
    """Extract database connection metadata with all credentials strictly redacted."""
    from django.db import connection
    db_dict = connection.settings_dict
    engine = db_dict.get('ENGINE', 'unknown').split('.')[-1]
    raw_host = db_dict.get('HOST', 'localhost') or 'localhost'
    raw_port = str(db_dict.get('PORT', '')) or 'default'
    raw_name = str(db_dict.get('NAME', 'unknown'))

    # Strip any embedded user:pass credentials from host or name strings
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


def is_database_approved_for_demo(db_info: Dict[str, str]) -> Tuple[bool, str]:
    """
    Verify whether the active database target is explicitly approved for live demo data modifications.
    
    Protects production and shared development databases (such as Supabase PostgreSQL)
    from unintended writes or deletes unless explicitly authorized.
    """
    # 1. Automated test suites are always safe
    if os.environ.get('PYTEST_CURRENT_TEST') or ('pytest' in sys.modules and 'test' in sys.argv):
        return True, "Automated test environment detected."

    # 2. Check explicit approval via environment variable or Django setting
    env_approval = os.environ.get('SHOPSENSE_DEMO_DATABASE_APPROVED', '').strip().lower()
    setting_approval = getattr(settings, 'SHOPSENSE_DEMO_DATABASE_APPROVED', False)
    if env_approval in ('true', '1', 'yes') or setting_approval is True:
        return True, "Explicit authorization granted via SHOPSENSE_DEMO_DATABASE_APPROVED."

    return False, (
        f"Database target '{db_info['engine']}://{db_info['host']}/{db_info['name']}' "
        "is not explicitly approved for demo data operations. "
        "To prevent accidental data modification on development or shared databases (including Supabase PostgreSQL), "
        "live seeding and cleanup require explicit approval.\n"
        "Set SHOPSENSE_DEMO_DATABASE_APPROVED=True in your environment or .env file before running live operations.\n"
        "(Use --dry-run to preview operations safely without making database or file changes)."
    )


def generate_demo_product_image(product_name: str, category_name: str, color_hex: str) -> ContentFile:
    """Generate an elegant, verified lightweight PNG placeholder image using Pillow."""
    img = Image.new('RGB', (600, 600), color=color_hex)
    draw = ImageDraw.Draw(img)

    # Inset frame
    draw.rectangle([24, 24, 576, 576], outline=(255, 255, 255), width=4)
    draw.rectangle([34, 34, 566, 566], outline=(255, 255, 255), width=1)

    # Header label background
    draw.rectangle([40, 480, 560, 550], fill=(0, 0, 0, 180))

    # Center circle badge
    draw.ellipse([220, 180, 380, 340], fill=(255, 255, 255))
    draw.ellipse([230, 190, 370, 330], outline=(0, 0, 0), width=2)

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    filename = f"demo_{slugify(product_name)[:30]}.png"
    return ContentFile(buffer.getvalue(), name=filename)


class Command(BaseCommand):
    help = (
        'Safe, repeatable demo data generator for ShopSense multi-vendor marketplace. '
        'Seeds diverse vendors, products, inventory movements, customers, and orders.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--vendors',
            type=int,
            default=8,
            help='Number of vendor profiles to seed (1-8, defaults to 8).',
        )
        parser.add_argument(
            '--products-per-vendor',
            type=int,
            default=15,
            help='Number of unique products per vendor to seed (defaults to 15).',
        )
        parser.add_argument(
            '--customers',
            type=int,
            default=25,
            help='Number of demo customer accounts to seed (defaults to 25).',
        )
        parser.add_argument(
            '--orders',
            type=int,
            default=50,
            help='Number of historical demo orders to seed (defaults to 50).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Simulate demo data generation without persisting changes to the database.',
        )
        parser.add_argument(
            '--clear-demo-data',
            '--cleanup',
            action='store_true',
            dest='clear_demo_data',
            default=False,
            help='Safely remove only records created exclusively by this demo data generator.',
        )
        parser.add_argument(
            '--skip-analytics',
            action='store_true',
            default=False,
            help='Skip post-seeding analytics calculations (alerts, suggestions, forecasts, RFM).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        clear_demo = options['clear_demo_data']
        vendors = options['vendors']
        products_per_vendor = options['products_per_vendor']
        customers = options['customers']
        orders = options['orders']

        db_info = get_sanitized_db_info()

        # 1. Production safety guard: Unconditionally refuse execution in production environments (DEBUG=False)
        if is_production_environment():
            raise CommandError(
                "DEMO SEEDER BLOCKED: Running demo data seeding or cleanup against a production database "
                f"(DEBUG=False, engine={db_info['engine']}) is strictly prohibited. "
                "The demo data generator is restricted to development and test environments."
            )

        # 2. Database target approval check for LIVE execution (not required for dry-run simulation)
        if not dry_run:
            approved, reason = is_database_approved_for_demo(db_info)
            if not approved:
                raise CommandError(
                    f"DEMO SEEDER BLOCKED: {reason}\n"
                    "Tip: You can safely simulate operations without making database changes using --dry-run."
                )

        # 3. Report active database target clearly (never exposes passwords or credentials)
        self.stdout.write(self.style.NOTICE(
            f"Database Target: Backend={db_info['engine']} | Host={db_info['host']} | "
            f"Port={db_info['port']} | Database={db_info['name']}"
        ))
        if 'sqlite' in db_info['engine'].lower():
            self.stdout.write(self.style.NOTICE(
                "  -> Notice: Running against local SQLite database."
            ))
        elif 'supabase' in db_info['host'].lower():
            self.stdout.write(self.style.NOTICE(
                "  -> Notice: Running against Supabase PostgreSQL database."
            ))

        # 4. Validate argument bounds first
        if not clear_demo:
            if vendors < 1 or vendors > 50:
                raise CommandError(f"Invalid --vendors argument '{vendors}'. Must be between 1 and 50.")
            if products_per_vendor < 1 or products_per_vendor > 200:
                raise CommandError(f"Invalid --products-per-vendor argument '{products_per_vendor}'. Must be between 1 and 200.")
            if customers < 1 or customers > 500:
                raise CommandError(f"Invalid --customers argument '{customers}'. Must be between 1 and 500.")
            if orders < 0 or orders > 1000:
                raise CommandError(f"Invalid --orders argument '{orders}'. Must be between 0 and 1000.")

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"=== [DRY RUN] Simulation mode active on {db_info['engine']} ({db_info['host']}). "
                "No database modifications will be committed and no media files will be created or deleted. ==="
            ))
        else:
            self.stdout.write(self.style.NOTICE(
                '=== Live execution: database writes will be safely applied within managed transactions. ==='
            ))

        if clear_demo:
            try:
                self.handle_cleanup(dry_run=dry_run)
            except CommandError:
                raise
            except Exception as e:
                logger.exception("Error executing demo data cleanup")
                raise CommandError(f"Cleanup failed: {e}")
            return

        # Execute seeding
        try:
            with transaction.atomic():
                summary = self.seed_marketplace(
                    num_vendors=vendors,
                    num_products_per_vendor=products_per_vendor,
                    num_customers=customers,
                    num_orders=orders,
                    skip_analytics=options['skip_analytics'],
                    dry_run=dry_run,
                )

                if dry_run:
                    transaction.set_rollback(True)
                    self.stdout.write(self.style.WARNING(
                        f"[DRY RUN] Simulated all seeding operations on {db_info['engine']}. "
                        "Transaction rolled back successfully. No records were committed."
                    ))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        '=== Demo data generation finished successfully and committed to database! ==='
                    ))

            self.print_summary(summary, dry_run=dry_run, db_info=db_info)

        except Exception as e:
            logger.exception("Error executing demo data seeder")
            raise CommandError(f"Seeder execution failed: {e}")

    def handle_cleanup(self, dry_run: bool = False):
        """Safely delete only demo records tagged with unique demo markers."""
        db_info = get_sanitized_db_info()
        self.stdout.write(self.style.NOTICE(
            f"Beginning safe cleanup of demo records on {db_info['engine']} ({db_info['host']})..."
        ))

        # 1. Foreign-key safety validation:
        # Detect any non-demo products associated with demo vendors.
        # Product.vendor has on_delete=CASCADE, so deleting a demo vendor would cascade-delete
        # any products owned by it. If any product lacks the demo SKU prefix, abort immediately!
        demo_vendors_qs = VendorProfile.objects.filter(vendor_id__startswith=DEMO_VENDOR_ID_PREFIX)
        alien_products = Product.objects.filter(
            vendor__in=demo_vendors_qs
        ).exclude(sku__startswith=DEMO_SKU_PREFIX)

        if alien_products.exists():
            alien_count = alien_products.count()
            sample_skus = list(alien_products.values_list('sku', flat=True)[:5])
            raise CommandError(
                f"CLEANUP ABORTED FOR SAFETY: Detected {alien_count} non-demo product(s) "
                f"associated with demo vendors (e.g. {sample_skus}). "
                "Deleting demo vendors would cascade-delete these non-demo products. "
                "Cleanup has been safely aborted. No records or files were deleted."
            )

        # 2. Identify and track physical demo image files before DB transaction
        demo_images = list(ProductImage.objects.filter(product__sku__startswith=DEMO_SKU_PREFIX))
        deleted_images = len(demo_images)
        files_to_delete = [
            img_obj.image.name for img_obj in demo_images
            if img_obj.image and hasattr(img_obj.image, 'name') and img_obj.image.name
        ]

        # 3. Phase 1: Database record deletions within atomic transaction
        with transaction.atomic():
            # 1. Clean up recommendation records
            recs = RecommendationCandidate.objects.filter(
                product__sku__startswith=DEMO_SKU_PREFIX
            )
            recs_user = RecommendationCandidate.objects.filter(
                user__email__endswith=f"@{DEMO_EMAIL_DOMAIN}"
            )
            deleted_recs = recs.count() + recs_user.count()
            if not dry_run:
                recs.delete()
                recs_user.delete()

            # 2. Clean up demand forecasts
            preds = ForecastPrediction.objects.filter(product__sku__startswith=DEMO_SKU_PREFIX)
            deleted_preds = preds.count()
            if not dry_run:
                preds.delete()

            models_qs = ForecastModel.objects.filter(product__sku__startswith=DEMO_SKU_PREFIX)
            deleted_fmodels = models_qs.count()
            if not dry_run:
                models_qs.delete()

            # 3. Customer RFM segment assignments
            seg_assignments = CustomerSegmentAssignment.objects.filter(
                user__email__endswith=f"@{DEMO_EMAIL_DOMAIN}"
            )
            deleted_segs = seg_assignments.count()
            if not dry_run:
                seg_assignments.delete()

            # 4. Low stock alerts & replenishment requests
            alerts = LowStockAlert.objects.filter(product__sku__startswith=DEMO_SKU_PREFIX)
            deleted_alerts = alerts.count()
            if not dry_run:
                alerts.delete()

            replenishments = ReplenishmentRequest.objects.filter(product__sku__startswith=DEMO_SKU_PREFIX)
            deleted_repls = replenishments.count()
            if not dry_run:
                replenishments.delete()

            # 5. Orders and payments
            demo_orders = Order.objects.filter(order_number__startswith=DEMO_ORDER_PREFIX)
            deleted_orders = demo_orders.count()

            demo_payments = Payment.objects.filter(payment_id__startswith=DEMO_PAYMENT_PREFIX)
            deleted_payments = demo_payments.count()

            demo_items = OrderItem.objects.filter(order__order_number__startswith=DEMO_ORDER_PREFIX)
            deleted_items = demo_items.count()

            if not dry_run:
                demo_payments.delete()
                demo_items.delete()
                demo_orders.delete()

            # 6. Inventory stock and movements
            demo_movements = StockMovement.objects.filter(product__sku__startswith=DEMO_SKU_PREFIX)
            deleted_movements = demo_movements.count()

            demo_wstocks = WarehouseStock.objects.filter(product__sku__startswith=DEMO_SKU_PREFIX)
            deleted_wstocks = demo_wstocks.count()

            demo_catalog_inv = Inventory.objects.filter(product__sku__startswith=DEMO_SKU_PREFIX)
            deleted_catalog_inv = demo_catalog_inv.count()

            if not dry_run:
                demo_movements.delete()
                demo_wstocks.delete()
                demo_catalog_inv.delete()

            # 7. Products and images (database records only; physical files unlinked post-commit)
            demo_products = Product.objects.filter(sku__startswith=DEMO_SKU_PREFIX)
            deleted_products = demo_products.count()

            if not dry_run:
                ProductImage.objects.filter(product__sku__startswith=DEMO_SKU_PREFIX).delete()
                demo_products.delete()

            # 8. Vendors & Applications
            demo_vendors = VendorProfile.objects.filter(vendor_id__startswith=DEMO_VENDOR_ID_PREFIX)
            deleted_vendors = demo_vendors.count()

            demo_apps = VendorApplication.objects.filter(vendor_id__startswith=DEMO_VENDOR_ID_PREFIX)
            deleted_apps = demo_apps.count()

            if not dry_run:
                demo_vendors.delete()
                demo_apps.delete()

            # 9. Customers & Addresses
            demo_addresses = Address.objects.filter(user__email__endswith=f"@{DEMO_EMAIL_DOMAIN}")
            deleted_addresses = demo_addresses.count()

            demo_users = User.objects.filter(email__endswith=f"@{DEMO_EMAIL_DOMAIN}")
            deleted_users = demo_users.count()

            if not dry_run:
                demo_addresses.delete()
                demo_users.delete()

            if dry_run:
                transaction.set_rollback(True)

        # 4. Phase 2: Post-Commit Physical File Deletion
        # Only executes after the database transaction has successfully committed!
        # If the DB transaction raised an error or rolled back, this section is NEVER reached.
        unlinked_files = 0
        failed_files = 0
        if not dry_run:
            from django.core.files.storage import default_storage
            for fname in files_to_delete:
                try:
                    if default_storage.exists(fname):
                        default_storage.delete(fname)
                        unlinked_files += 1
                except Exception as file_err:
                    failed_files += 1
                    logger.warning(f"Could not delete physical image file '{fname}' from storage: {file_err}")
                    self.stdout.write(self.style.WARNING(
                        f"Warning: Failed to delete image file '{fname}' from storage: {file_err}"
                    ))

        mode_str = "[DRY RUN] Would delete" if dry_run else "Successfully deleted"
        storage_msg = f" ({unlinked_files} files unlinked from storage)" if not dry_run else " (no files modified in dry run)"
        if failed_files > 0:
            storage_msg += f" [{failed_files} file unlinks failed - see logs]"

        self.stdout.write(self.style.SUCCESS(
            f"{mode_str}:\n"
            f"  - {deleted_users} demo users ({deleted_vendors} vendors, {deleted_users - deleted_vendors} customers)\n"
            f"  - {deleted_apps} vendor applications\n"
            f"  - {deleted_products} demo products and {deleted_images} product image records{storage_msg}\n"
            f"  - {deleted_movements} stock ledger movements and {deleted_wstocks} warehouse stock balances\n"
            f"  - {deleted_orders} demo orders, {deleted_items} items, {deleted_payments} payments\n"
            f"  - {deleted_alerts} alerts, {deleted_repls} replenishment requests, {deleted_preds} predictions\n"
            f"  - Ordinary non-demo application data remained completely untouched."
        ))
        self.stdout.write(self.style.SUCCESS(
            f"{mode_str}:\n"
            f"  - {deleted_users} demo users ({deleted_vendors} vendors, {deleted_users - deleted_vendors} customers)\n"
            f"  - {deleted_apps} vendor applications\n"
            f"  - {deleted_products} demo products and {deleted_images} product images\n"
            f"  - {deleted_movements} stock ledger movements and {deleted_wstocks} warehouse stock balances\n"
            f"  - {deleted_orders} demo orders, {deleted_items} items, {deleted_payments} payments\n"
            f"  - {deleted_alerts} alerts, {deleted_repls} replenishment requests, {deleted_preds} predictions\n"
            f"  - Ordinary non-demo application data remained completely untouched."
        ))

    def seed_marketplace(
        self,
        num_vendors: int,
        num_products_per_vendor: int,
        num_customers: int,
        num_orders: int,
        skip_analytics: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Core seeding pipeline for marketplace demo data."""
        summary = {
            'vendors_created': 0,
            'vendors_reused': 0,
            'products_created': 0,
            'products_reused': 0,
            'warehouse_units_inbounded': 0,
            'customers_created': 0,
            'customers_reused': 0,
            'orders_created': 0,
            'orders_reused': 0,
            'order_sales_units_deducted': 0,
            'alerts_created': 0,
            'replenishments_created': 0,
            'forecasts_trained': 0,
            'customers_segmented': 0,
            'recommendations_created': 0,
            'discrepancies': 0,
        }

        # 1. Warehouses Setup
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
        warehouses = [wh_default, wh_west, wh_north]

        # Find existing admin user for application review
        admin_user = User.objects.filter(role=User.Role.ADMIN).first()

        # 2. Seed Vendors
        selected_templates = []
        for i in range(num_vendors):
            template = VENDOR_TEMPLATES[i % len(VENDOR_TEMPLATES)].copy()
            if i >= len(VENDOR_TEMPLATES):
                idx = i + 1
                template['vendor_id'] = f"{DEMO_VENDOR_ID_PREFIX}{idx:04d}"
                template['business_name'] = f"{template['business_name']} #{idx}"
                template['contact_email'] = f"demo.vendor.{template['sku_code'].lower()}{idx}@{DEMO_EMAIL_DOMAIN}"
            selected_templates.append(template)

        seeded_vendors: List[VendorProfile] = []
        for vdata in selected_templates:
            vendor_profile, created = self.get_or_create_vendor(vdata, admin_user)
            if created:
                summary['vendors_created'] += 1
            else:
                summary['vendors_reused'] += 1
            seeded_vendors.append(vendor_profile)

        self.stdout.write(self.style.SUCCESS(
            f"Vendors processed: {summary['vendors_created']} created, {summary['vendors_reused']} reused."
        ))

        # 3. Seed Products and Inbound Warehouse Stock
        active_demo_products: List[Product] = []
        all_demo_products: List[Product] = []

        for v_idx, vendor_profile in enumerate(seeded_vendors):
            vdata = selected_templates[v_idx]
            cat_obj, _ = Category.objects.get_or_create(
                slug=vdata['category_slug'],
                defaults={
                    'name': vdata['category_name'],
                    'description': vdata['category_desc'],
                    'is_active': True,
                    'sort_order': v_idx + 1,
                },
            )

            raw_catalog = PRODUCT_CATALOG.get(vdata['sku_code'], PRODUCT_CATALOG['ELEC'])
            for p_idx in range(num_products_per_vendor):
                base_item = raw_catalog[p_idx % len(raw_catalog)]
                cycle = p_idx // len(raw_catalog)
                sku = f"{DEMO_SKU_PREFIX}{vdata['sku_code']}-{(v_idx + 1):02d}-{(p_idx + 1):03d}"
                name = base_item[0] if cycle == 0 else f"{base_item[0]} (Gen {cycle + 1})"

                product, prod_created = Product.objects.get_or_create(
                    sku=sku,
                    defaults={
                        'vendor': vendor_profile,
                        'category': cat_obj,
                        'name': name,
                        'slug': f"{slugify(name)[:50]}-{sku.lower()}",
                        'description': base_item[1],
                        'short_description': base_item[2],
                        'price': Decimal(base_item[3]),
                        'compare_at_price': Decimal(base_item[4]),
                        'cost_price': Decimal(base_item[5]),
                        'weight': Decimal(str(base_item[6])),
                        'dimensions': base_item[7],
                        'status': Product.Status.ACTIVE,
                        'is_featured': (p_idx == 0),
                    },
                )

                if prod_created:
                    summary['products_created'] += 1
                    # Attach product image via Django storage mechanism (only when not in dry-run mode)
                    if not dry_run:
                        try:
                            content_file = generate_demo_product_image(
                                product_name=product.name,
                                category_name=cat_obj.name,
                                color_hex=vdata['color'],
                            )
                            ProductImage.objects.create(
                                product=product,
                                image=content_file,
                                alt_text=product.name,
                                is_primary=True,
                                sort_order=0,
                            )
                        except Exception as img_err:
                            logger.warning(f"Failed generating placeholder image for {product.sku}: {img_err}")
                else:
                    summary['products_reused'] += 1

                all_demo_products.append(product)

                # Determine stock scenario: ensure healthy, low-stock, and out-of-stock scenarios for all vendors
                if p_idx == 0:
                    # Guaranteed healthy stock with high volume
                    stock_targets = {wh_default: 50, wh_west: 25, wh_north: 15}
                    low_thresh = 15
                    active_demo_products.append(product)
                elif p_idx == 1:
                    # Guaranteed low stock scenario
                    stock_targets = {wh_default: 4, wh_west: 0, wh_north: 0}
                    low_thresh = 12
                    active_demo_products.append(product)
                elif p_idx == 2:
                    # Guaranteed out-of-stock scenario
                    product.status = Product.Status.OUT_OF_STOCK
                    product.save(update_fields=['status'])
                    stock_targets = {wh_default: 0, wh_west: 0, wh_north: 0}
                    low_thresh = 10
                elif p_idx % 10 == 9:
                    # Inactive product
                    product.status = Product.Status.INACTIVE
                    product.save(update_fields=['status'])
                    stock_targets = {wh_default: 0, wh_west: 0, wh_north: 0}
                    low_thresh = 10
                elif p_idx % 6 == 0:
                    # Additional out-of-stock
                    product.status = Product.Status.OUT_OF_STOCK
                    product.save(update_fields=['status'])
                    stock_targets = {wh_default: 0, wh_west: 0, wh_north: 0}
                    low_thresh = 10
                elif p_idx % 6 == 1:
                    # Additional low stock
                    stock_targets = {wh_default: 3, wh_west: 0, wh_north: 0}
                    low_thresh = 10
                    active_demo_products.append(product)
                else:
                    # Healthy stock scenario
                    stock_targets = {wh_default: 40, wh_west: 20, wh_north: 15}
                    low_thresh = 10
                    active_demo_products.append(product)

                # Inbound Stock Movements via StockService
                for wh, target_qty in stock_targets.items():
                    inbound_key = f"{DEMO_IDEMPOTENCY_PREFIX}inbound-{wh.code}-{product.sku}"
                    if not StockMovement.objects.filter(idempotency_key=inbound_key).exists():
                        if target_qty > 0:
                            StockService.record_stock_movement(
                                product=product,
                                warehouse=wh,
                                quantity_change=target_qty,
                                movement_type=StockMovement.MovementType.PURCHASE,
                                reason="Initial vendor demo consignment inbound",
                                idempotency_key=inbound_key,
                                performed_by=admin_user,
                            )
                            summary['warehouse_units_inbounded'] += target_qty
                        else:
                            # Ensure WarehouseStock row exists even if quantity is 0
                            WarehouseStock.objects.get_or_create(
                                warehouse=wh,
                                product=product,
                                defaults={'quantity': 0, 'reserved_quantity': 0, 'damaged_quantity': 0},
                            )

                # Synchronize catalog inventory to reflect zero warehouse stock if all targets were 0
                StockService.sync_catalog_inventory(product)

                # Configure catalog Inventory threshold
                inv, _ = Inventory.objects.get_or_create(
                    product=product,
                    defaults={'low_stock_threshold': low_thresh, 'quantity': 0},
                )
                if inv.low_stock_threshold != low_thresh:
                    inv.low_stock_threshold = low_thresh
                    inv.save(update_fields=['low_stock_threshold'])

        self.stdout.write(self.style.SUCCESS(
            f"Products processed: {summary['products_created']} created, {summary['products_reused']} reused. "
            f"+{summary['warehouse_units_inbounded']} warehouse stock units inbounded."
        ))

        # 4. Seed Demo Customers
        seeded_customers: List[User] = []
        for c_idx in range(num_customers):
            c_data = CUSTOMER_SEED_DATA[c_idx % len(CUSTOMER_SEED_DATA)]
            email = c_data[0] if c_idx < len(CUSTOMER_SEED_DATA) else f"demo.customer{c_idx + 1:02d}@{DEMO_EMAIL_DOMAIN}"
            first_name = c_data[1]
            last_name = c_data[2] if c_idx < len(CUSTOMER_SEED_DATA) else f"Customer {c_idx + 1}"

            customer, cust_created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'role': User.Role.CUSTOMER,
                    'is_active': True,
                    'phone': c_data[3],
                },
            )
            if cust_created:
                customer.set_password(DEMO_CUSTOMER_PASSWORD)
                customer.save()
                summary['customers_created'] += 1
            else:
                summary['customers_reused'] += 1

            # Default customer address
            Address.objects.get_or_create(
                user=customer,
                is_default=True,
                defaults={
                    'first_name': customer.first_name,
                    'last_name': customer.last_name,
                    'phone': customer.phone or '+91 98765 10000',
                    'street_address': c_data[4],
                    'city': c_data[5],
                    'state': c_data[6],
                    'postal_code': c_data[7],
                    'country': 'India',
                },
            )
            seeded_customers.append(customer)

        self.stdout.write(self.style.SUCCESS(
            f"Customers processed: {summary['customers_created']} created, {summary['customers_reused']} reused."
        ))

        # 5. Seed Historical Orders
        now = timezone.now()
        payment_methods = [
            Payment.Method.UPI,
            Payment.Method.CARD,
            Payment.Method.NET_BANKING,
            Payment.Method.WALLET,
            Payment.Method.COD,
        ]

        # Use healthy-stocked active products for order fulfillment
        fulfillment_pool = [p for p in active_demo_products if p.inventory.quantity >= 15]
        if not fulfillment_pool:
            fulfillment_pool = active_demo_products

        for o_idx in range(num_orders):
            order_num = f"{DEMO_ORDER_PREFIX}{o_idx + 1:05d}"
            if Order.objects.filter(order_number=order_num).exists():
                summary['orders_reused'] += 1
                continue

            customer = seeded_customers[o_idx % len(seeded_customers)]
            # Spread order dates across the past 55 days for demand forecasting and RFM segmentation
            days_ago = max(1, int(55 - (o_idx * 52 / max(1, num_orders))))
            order_time = now - timedelta(days=days_ago, hours=(o_idx % 12), minutes=(o_idx * 7 % 60))

            # Status distribution: 70% DELIVERED, 10% SHIPPED, 10% CONFIRMED/PROCESSING, 5% CANCELLED, 5% REFUNDED
            status_mod = o_idx % 20
            if status_mod == 19:
                order_status = Order.Status.CANCELLED
            elif status_mod == 18:
                order_status = Order.Status.REFUNDED
            elif status_mod in (16, 17):
                order_status = Order.Status.PROCESSING
            elif status_mod in (14, 15):
                order_status = Order.Status.SHIPPED
            else:
                order_status = Order.Status.DELIVERED

            # Determine items in order (1 to 3 items)
            num_items = (o_idx % 3) + 1
            order_prods = [
                fulfillment_pool[(o_idx * 3 + j) % len(fulfillment_pool)]
                for j in range(num_items)
            ]

            # Calculate line totals
            item_quantities = [(j % 2) + 1 for j in range(num_items)]
            subtotal = sum(prod.price * qty for prod, qty in zip(order_prods, item_quantities))
            shipping_cost, tax_amount, total = calculate_order_financials(subtotal)

            addr = customer.addresses.first()
            confirmed_time = order_time + timedelta(hours=1) if order_status != Order.Status.PENDING else None
            shipped_time = order_time + timedelta(days=1) if order_status in [Order.Status.SHIPPED, Order.Status.DELIVERED, Order.Status.REFUNDED] else None
            delivered_time = order_time + timedelta(days=3) if order_status in [Order.Status.DELIVERED, Order.Status.REFUNDED] else None

            order = Order.objects.create(
                order_number=order_num,
                user=customer,
                email=customer.email,
                phone=customer.phone,
                status=order_status,
                shipping_first_name=customer.first_name,
                shipping_last_name=customer.last_name,
                shipping_address=addr.street_address if addr else '100 Demo Road',
                shipping_city=addr.city if addr else 'Bengaluru',
                shipping_state=addr.state if addr else 'Karnataka',
                shipping_postal_code=addr.postal_code if addr else '560001',
                shipping_country='India',
                subtotal=subtotal,
                shipping_cost=shipping_cost,
                tax_amount=tax_amount,
                discount_amount=Decimal('0.00'),
                total=total,
                admin_notes='[DEMO_DATA] Seeded multi-vendor demo order',
                created_at=order_time,
                confirmed_at=confirmed_time,
                shipped_at=shipped_time,
                delivered_at=delivered_time,
            )

            # Create Order Items and update inventory
            for prod, qty in zip(order_prods, item_quantities):
                if order_status == Order.Status.CANCELLED:
                    item_status = OrderItem.Status.CANCELLED
                elif order_status in [Order.Status.DELIVERED, Order.Status.REFUNDED]:
                    item_status = OrderItem.Status.DELIVERED
                elif order_status == Order.Status.SHIPPED:
                    item_status = OrderItem.Status.SHIPPED
                else:
                    item_status = OrderItem.Status.CONFIRMED

                OrderItem.objects.create(
                    order=order,
                    product=prod,
                    vendor=prod.vendor,
                    product_name=prod.name,
                    product_sku=prod.sku,
                    quantity=qty,
                    unit_price=prod.price,
                    total_price=prod.price * qty,
                    status=item_status,
                    shipped_at=shipped_time,
                    delivered_at=delivered_time,
                    created_at=order_time,
                )

                # Deduct stock for non-cancelled orders via StockService to preserve ledger parity
                if order_status not in [Order.Status.CANCELLED, Order.Status.PENDING]:
                    sale_key = f"{DEMO_IDEMPOTENCY_PREFIX}sale-{order.order_number}-{prod.sku}"
                    if not StockMovement.objects.filter(idempotency_key=sale_key).exists():
                        StockService.record_stock_movement(
                            product=prod,
                            warehouse=wh_default,
                            quantity_change=-qty,
                            movement_type=StockMovement.MovementType.SALE,
                            reason=f"Order checkout fulfillment for {order.order_number}",
                            order=order,
                            idempotency_key=sale_key,
                            performed_by=admin_user,
                        )
                        summary['order_sales_units_deducted'] += qty

            # Payment record
            pay_method = payment_methods[o_idx % len(payment_methods)]
            if order_status == Order.Status.REFUNDED:
                pay_status = Payment.Status.REFUNDED
            elif order_status == Order.Status.CANCELLED:
                pay_status = Payment.Status.FAILED
            elif pay_method == Payment.Method.COD and order_status != Order.Status.DELIVERED:
                pay_status = Payment.Status.PENDING
            else:
                pay_status = Payment.Status.COMPLETED

            Payment.objects.create(
                order=order,
                payment_id=f"{DEMO_PAYMENT_PREFIX}{order.order_number}",
                method=pay_method,
                status=pay_status,
                amount=order.total,
                currency='INR',
                created_at=order_time,
                completed_at=confirmed_time,
            )

            summary['orders_created'] += 1

        self.stdout.write(self.style.SUCCESS(
            f"Orders processed: {summary['orders_created']} created, {summary['orders_reused']} reused. "
            f"-{summary['order_sales_units_deducted']} units deducted via SALE movements."
        ))

        # 6. Verify Stock Reconciliation
        discrepancies = StockService.reconcile_inventory()
        summary['discrepancies'] = len(discrepancies)
        if discrepancies:
            self.stdout.write(self.style.WARNING(
                f"Warning: {len(discrepancies)} inventory ledger discrepancies detected."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "Inventory ledger reconciliation verified: 0 discrepancies across all products."
            ))

        # 7. Refresh Analytics (Alerts, Replenishment, Forecasts, Segments, Recommendations)
        if not skip_analytics:
            self.stdout.write(self.style.NOTICE("Refreshing analytics models and recommendation candidates..."))
            summary['alerts_created'] = AlertService.generate_all_alerts()
            summary['replenishments_created'] = ReplenishmentService.generate_all_suggestions()
            summary['forecasts_trained'] = ForecastService.train_all_forecasts()
            seg_results = CustomerAnalyticsService.segment_customers()
            summary['customers_segmented'] = seg_results.get('total_customers', 0)
            summary['recommendations_created'] = RecommendationService.refresh_recommendation_candidates()
            self.stdout.write(self.style.SUCCESS("Analytics refresh completed successfully."))

        return summary

    def get_or_create_vendor(self, vdata: Dict[str, Any], admin_user: Optional[User]) -> Tuple[VendorProfile, bool]:
        """Create or retrieve a vendor profile via existing approval workflow."""
        existing_profile = VendorProfile.objects.filter(vendor_id=vdata['vendor_id']).first()
        if existing_profile:
            return existing_profile, False

        # Create or retrieve Vendor Application
        app, app_created = VendorApplication.objects.get_or_create(
            contact_email=vdata['contact_email'],
            defaults={
                'business_name': vdata['business_name'],
                'business_description': vdata['business_description'],
                'contact_phone': vdata['contact_phone'],
                'business_address': vdata['business_address'],
                'city': vdata['city'],
                'state': vdata['state'],
                'postal_code': vdata['postal_code'],
                'country': vdata['country'],
                'tax_id': vdata['tax_id'],
                'website': vdata['website'],
                'vendor_id': vdata['vendor_id'],
                'status': VendorApplication.Status.PENDING,
            },
        )

        # Set user password securely with explicit demo prefix
        applicant_user = app.applicant_user
        applicant_user.set_password(DEMO_VENDOR_PASSWORD)
        applicant_user.save()

        # Execute approval workflow
        if app.status != VendorApplication.Status.APPROVED:
            app.approve(reviewed_by=admin_user, notes='Approved by demo data generator')

        applicant_user.is_active = True
        applicant_user.role = User.Role.VENDOR
        applicant_user.save(update_fields=['is_active', 'role'])

        profile = VendorProfile.objects.get(vendor_id=vdata['vendor_id'])
        profile.is_verified = True
        profile.commission_rate = vdata['commission_rate']
        profile.save(update_fields=['is_verified', 'commission_rate'])

        # Audit log entry for vendor approval
        AuditLog.objects.create(
            user=admin_user,
            action=AuditLog.ActionType.VENDOR_APPROVED,
            target_vendor=profile,
            target_user=applicant_user,
            details={'notes': 'Demo vendor auto-approved'},
        )

        return profile, True

    def print_summary(self, summary: Dict[str, Any], dry_run: bool = False, db_info: Optional[Dict[str, str]] = None):
        """Display clear execution metrics and summary table."""
        status_tag = "[DRY RUN]" if dry_run else "[COMMITTED]"
        backend_str = f"{db_info['engine']} ({db_info['host']})" if db_info else "default"
        self.stdout.write("\n" + "=" * 65)
        self.stdout.write(f"  SHOPSENSE DEMO DATA SEEDER SUMMARY {status_tag}")
        self.stdout.write("=" * 65)
        self.stdout.write(f"  Target Database:                  {backend_str}")
        self.stdout.write(f"  Execution Mode:                   {'DRY RUN (Simulation - Rolled Back)' if dry_run else 'LIVE (Committed)'}")
        self.stdout.write(f"  Vendors Created / Reused:         {summary['vendors_created']} / {summary['vendors_reused']}")
        self.stdout.write(f"  Products Created / Reused:        {summary['products_created']} / {summary['products_reused']}")
        self.stdout.write(f"  Warehouse Units Inbounded:        {summary['warehouse_units_inbounded']}")
        self.stdout.write(f"  Customers Created / Reused:       {summary['customers_created']} / {summary['customers_reused']}")
        self.stdout.write(f"  Orders Created / Reused:          {summary['orders_created']} / {summary['orders_reused']}")
        self.stdout.write(f"  Order Sales Units Deducted:       {summary['order_sales_units_deducted']}")
        self.stdout.write(f"  Inventory Ledger Discrepancies:   {summary['discrepancies']}")
        self.stdout.write(f"  Low Stock Alerts Active:          {summary['alerts_created']}")
        self.stdout.write(f"  Replenishment Requests Suggested: {summary['replenishments_created']}")
        self.stdout.write(f"  Demand Forecast Models Trained:   {summary['forecasts_trained']}")
        self.stdout.write(f"  Customer RFM Segments Assigned:   {summary['customers_segmented']}")
        self.stdout.write(f"  Recommendation Candidates:        {summary['recommendations_created']}")
        self.stdout.write("=" * 65 + "\n")
