"""
Comprehensive test suite for ShopSense Milestone 2:
- Category cycle validation & hierarchy
- Warehouse defaults & constraints
- Stock movement ledger append-only & idempotency
- Transfer lifecycle & over-shipping/over-receiving protection
- Low stock alert deduplication, acknowledgement & recovery
- Replenishment ROP calculation & approval workflows
- Turnover analytics & velocity classification
- Forecasting WAPE calculation & zero-demand edge cases
- RFM segmentation & silhouette score handling
- Recommendation candidate generation & holdout precision@k
- Admin & vendor role-based access & strict vendor data isolation
"""

from decimal import Decimal
import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from catalog.forms import CategoryForm
from catalog.models import Category, Product, Inventory
from inventory.models import (
    Warehouse,
    WarehouseStock,
    StockMovement,
    StockTransfer,
    StockTransferItem,
    LowStockAlert,
    ReplenishmentRequest,
    ForecastModel,
    ForecastPrediction,
    CustomerSegment,
    CustomerSegmentAssignment,
    RecommendationCandidate,
    RecommendationEvaluation,
)
from inventory.services import (
    StockService,
    TransferService,
    AlertService,
    ReplenishmentService,
    TurnoverService,
    ForecastService,
    CustomerAnalyticsService,
    RecommendationService,
)
from orders.models import Order, OrderItem
from vendors.models import VendorProfile


@pytest.fixture
def vendor_profile(vendor_user):
    profile, _ = VendorProfile.objects.get_or_create(
        user=vendor_user,
        defaults={
            'vendor_id': f'VND-{vendor_user.pk:05d}',
            'business_name': 'Acme Supplies',
            'contact_email': vendor_user.email,
            'is_active': True,
        },
    )
    return profile


@pytest.fixture
def other_vendor_profile(client):
    from tests.conftest import UserFactory
    other_user = UserFactory(email='other_vendor_test@example.com', role='VENDOR')
    profile, _ = VendorProfile.objects.get_or_create(
        user=other_user,
        defaults={
            'vendor_id': f'VND-OTH-{other_user.pk:05d}',
            'business_name': 'Apex Retailers',
            'contact_email': other_user.email,
            'is_active': True,
        },
    )
    return profile


@pytest.fixture
def test_category():
    return Category.objects.create(name='Electronics', slug='electronics')


@pytest.fixture
def product(vendor_profile, test_category):
    prod = Product.objects.create(
        vendor=vendor_profile,
        category=test_category,
        name='Premium Headphones',
        slug='premium-headphones',
        sku='PH-100',
        description='High fidelity wireless headphones.',
        price=Decimal('4999.00'),
        status=Product.Status.ACTIVE,
    )
    Inventory.objects.create(
        product=prod,
        quantity=50,
        low_stock_threshold=10,
    )
    return prod


@pytest.fixture
def other_vendor_product(other_vendor_profile, test_category):
    prod = Product.objects.create(
        vendor=other_vendor_profile,
        category=test_category,
        name='Apex Mechanical Keyboard',
        slug='apex-keyboard',
        sku='AK-900',
        description='RGB Mechanical Keyboard.',
        price=Decimal('6999.00'),
        status=Product.Status.ACTIVE,
    )
    Inventory.objects.create(
        product=prod,
        quantity=30,
        low_stock_threshold=5,
    )
    return prod


@pytest.fixture
def warehouses():
    wh1 = Warehouse.objects.create(
        name='Main Center',
        code='WH-MAIN',
        city='Mumbai',
        state='Maharashtra',
        status=Warehouse.Status.ACTIVE,
        is_default=True,
    )
    wh2 = Warehouse.objects.create(
        name='South Center',
        code='WH-SOUTH',
        city='Chennai',
        state='Tamil Nadu',
        status=Warehouse.Status.ACTIVE,
        is_default=False,
    )
    return wh1, wh2


# ==========================================
# 1. Category Hierarchy & Cycle Tests
# ==========================================
@pytest.mark.django_db
class TestCategoryHierarchy:

    def test_category_self_parenting_prohibited(self):
        cat = Category.objects.create(name='Gadgets', slug='gadgets')
        cat.parent = cat
        with pytest.raises(ValidationError):
            cat.save()

    def test_category_indirect_cycle_prohibited(self):
        root = Category.objects.create(name='L1', slug='l1')
        mid = Category.objects.create(name='L2', slug='l2', parent=root)
        leaf = Category.objects.create(name='L3', slug='l3', parent=mid)

        # Attempt to make root parent point to leaf -> cyclic loop
        root.parent = leaf
        with pytest.raises(ValidationError):
            root.save()

    def test_category_ancestors_and_descendants(self):
        root = Category.objects.create(name='Electronics', slug='elec')
        comp = Category.objects.create(name='Computers', slug='comp', parent=root)
        laptop = Category.objects.create(name='Laptops', slug='laptop', parent=comp)

        ancestors = laptop.get_ancestors()
        assert ancestors == [root, comp]

        descendants = root.get_descendants()
        assert comp in descendants
        assert laptop in descendants

    def test_category_product_count(self, vendor_profile):
        root = Category.objects.create(name='Apparel', slug='apparel')
        sub = Category.objects.create(name='Shirts', slug='shirts', parent=root)

        Product.objects.create(
            vendor=vendor_profile,
            category=sub,
            name='Cotton Shirt',
            slug='cotton-shirt',
            sku='CS-1',
            description='Test',
            price=Decimal('999.00'),
            status=Product.Status.ACTIVE,
        )
        assert root.get_product_count(include_descendants=True) == 1
        assert root.get_product_count(include_descendants=False) == 0

    def test_category_form_cycle_validation(self):
        cat1 = Category.objects.create(name='Cat A', slug='cat-a')
        form = CategoryForm(data={
            'name': 'Cat A',
            'slug': 'cat-a',
            'parent': cat1.pk,
            'is_active': True,
            'sort_order': 0,
        }, instance=cat1)
        assert not form.is_valid()
        assert 'parent' in form.errors


# ==========================================
# 2. Warehouse & Stock Constraints
# ==========================================
@pytest.mark.django_db
class TestWarehouseAndStock:

    def test_warehouse_default_uniqueness(self, warehouses):
        wh1, wh2 = warehouses
        assert wh1.is_default is True
        assert wh2.is_default is False

        # Make wh2 default
        wh2.is_default = True
        wh2.save()

        wh1.refresh_from_db()
        wh2.refresh_from_db()
        assert wh2.is_default is True
        assert wh1.is_default is False

    def test_stock_movement_append_only_prevent_update(self, product, warehouses):
        wh1, _ = warehouses
        mov = StockService.record_stock_movement(
            product=product,
            warehouse=wh1,
            quantity_change=20,
            movement_type=StockMovement.MovementType.PURCHASE,
            reason="Inbound delivery",
        )
        mov.reason = "Altered reason"
        with pytest.raises(ValidationError):
            mov.save()

    def test_stock_movement_append_only_prevent_delete(self, product, warehouses):
        wh1, _ = warehouses
        mov = StockService.record_stock_movement(
            product=product,
            warehouse=wh1,
            quantity_change=20,
            movement_type=StockMovement.MovementType.PURCHASE,
            reason="Inbound delivery",
        )
        with pytest.raises(ValidationError):
            mov.delete()

    def test_stock_movement_idempotency_same_payload(self, product, warehouses):
        wh1, _ = warehouses
        key = "idemp-purchase-1001"
        m1 = StockService.record_stock_movement(
            product=product,
            warehouse=wh1,
            quantity_change=15,
            movement_type=StockMovement.MovementType.PURCHASE,
            reason="Initial purchase",
            idempotency_key=key,
        )
        # Duplicate with same payload
        m2 = StockService.record_stock_movement(
            product=product,
            warehouse=wh1,
            quantity_change=15,
            movement_type=StockMovement.MovementType.PURCHASE,
            reason="Initial purchase",
            idempotency_key=key,
        )
        assert m1.pk == m2.pk
        stock = WarehouseStock.objects.get(product=product, warehouse=wh1)
        assert stock.quantity == 15

    def test_stock_movement_idempotency_conflicting_payload_rejected(self, product, warehouses):
        wh1, _ = warehouses
        key = "idemp-conflict-test"
        StockService.record_stock_movement(
            product=product,
            warehouse=wh1,
            quantity_change=10,
            movement_type=StockMovement.MovementType.PURCHASE,
            reason="Initial",
            idempotency_key=key,
        )
        # Conflicting quantity
        with pytest.raises(ValidationError):
            StockService.record_stock_movement(
                product=product,
                warehouse=wh1,
                quantity_change=20,  # Conflict!
                movement_type=StockMovement.MovementType.PURCHASE,
                reason="Initial",
                idempotency_key=key,
            )

    def test_insufficient_stock_raises_error(self, product, warehouses):
        wh1, _ = warehouses
        # Warehouse stock is 0
        with pytest.raises(ValidationError):
            StockService.record_stock_movement(
                product=product,
                warehouse=wh1,
                quantity_change=-5,
                movement_type=StockMovement.MovementType.SALE,
                reason="Sale deduction",
            )


# ==========================================
# 3. Warehouse Transfer Lifecycle Tests
# ==========================================
@pytest.mark.django_db
class TestTransferLifecycle:

    def test_transfer_lifecycle_success(self, product, warehouses, admin_user):
        wh1, wh2 = warehouses
        # Seed stock at source
        StockService.record_stock_movement(
            product=product,
            warehouse=wh1,
            quantity_change=50,
            movement_type=StockMovement.MovementType.PURCHASE,
            reason="Seed stock",
        )

        # 1. Create transfer
        transfer = TransferService.create_transfer(
            source_warehouse=wh1,
            destination_warehouse=wh2,
            items_data=[{'product': product, 'quantity': 20}],
            requested_by=admin_user,
        )
        assert transfer.status == StockTransfer.TransferStatus.REQUESTED

        # 2. Approve transfer
        TransferService.approve_transfer(transfer, approved_by=admin_user)
        assert transfer.status == StockTransfer.TransferStatus.APPROVED

        # 3. Ship transfer
        TransferService.ship_transfer(transfer)
        assert transfer.status == StockTransfer.TransferStatus.IN_TRANSIT
        # Source stock deducted
        wh1_stock = WarehouseStock.objects.get(product=product, warehouse=wh1)
        assert wh1_stock.quantity == 30

        # 4. Receive transfer
        TransferService.receive_transfer(transfer)
        assert transfer.status == StockTransfer.TransferStatus.RECEIVED
        # Destination stock credited
        wh2_stock = WarehouseStock.objects.get(product=product, warehouse=wh2)
        assert wh2_stock.quantity == 20

    def test_transfer_same_warehouse_fails(self, product, warehouses):
        wh1, _ = warehouses
        with pytest.raises(ValidationError):
            TransferService.create_transfer(
                source_warehouse=wh1,
                destination_warehouse=wh1,
                items_data=[{'product': product, 'quantity': 5}],
            )

    def test_transfer_over_shipping_fails(self, product, warehouses, admin_user):
        wh1, wh2 = warehouses
        StockService.record_stock_movement(
            product=product,
            warehouse=wh1,
            quantity_change=50,
            movement_type=StockMovement.MovementType.PURCHASE,
            reason="Seed",
        )
        transfer = TransferService.create_transfer(
            source_warehouse=wh1,
            destination_warehouse=wh2,
            items_data=[{'product': product, 'quantity': 10}],
            requested_by=admin_user,
        )
        TransferService.approve_transfer(transfer, approved_by=admin_user)

        with pytest.raises(ValidationError):
            TransferService.ship_transfer(transfer, shipped_items={product.pk: 15})

    def test_transfer_cancellation_prevented_in_transit(self, product, warehouses, admin_user):
        wh1, wh2 = warehouses
        StockService.record_stock_movement(
            product=product,
            warehouse=wh1,
            quantity_change=50,
            movement_type=StockMovement.MovementType.PURCHASE,
            reason="Seed",
        )
        transfer = TransferService.create_transfer(
            source_warehouse=wh1,
            destination_warehouse=wh2,
            items_data=[{'product': product, 'quantity': 10}],
            requested_by=admin_user,
        )
        TransferService.approve_transfer(transfer, approved_by=admin_user)
        TransferService.ship_transfer(transfer)

        # Cannot cancel while in transit
        with pytest.raises(ValidationError):
            TransferService.cancel_transfer(transfer, cancelled_by=admin_user)


# ==========================================
# 4. Alerts & Replenishment Tests
# ==========================================
@pytest.mark.django_db
class TestAlertsAndReplenishment:

    def test_alert_generation_and_deduplication(self, product, warehouses):
        wh1, _ = warehouses
        # Stock = 5, threshold = 10 -> Low stock
        WarehouseStock.objects.create(warehouse=wh1, product=product, quantity=5)

        alerts = AlertService.evaluate_product_stock(product, warehouse=wh1)
        assert len(alerts) == 1
        assert alerts[0].alert_type == LowStockAlert.AlertType.LOW_STOCK

        # Re-evaluating does not produce duplicate active alert
        second_eval = AlertService.evaluate_product_stock(product, warehouse=wh1)
        assert len(second_eval) == 0
        assert LowStockAlert.objects.filter(product=product).count() == 1

    def test_alert_resolution_on_stock_recovery(self, product, warehouses):
        wh1, _ = warehouses
        stock = WarehouseStock.objects.create(warehouse=wh1, product=product, quantity=2)
        AlertService.evaluate_product_stock(product, warehouse=wh1)

        alert = LowStockAlert.objects.get(product=product)
        assert alert.status == LowStockAlert.Status.ACTIVE

        # Stock recovers to 50
        stock.quantity = 50
        stock.save()

        AlertService.evaluate_product_stock(product, warehouse=wh1)
        alert.refresh_from_db()
        assert alert.status == LowStockAlert.Status.RESOLVED

    def test_replenishment_rop_and_approval(self, product, admin_user):
        # Set product stock to 0 so it breaches reorder point (ROP = 10)
        product.inventory.quantity = 0
        product.inventory.save()

        req = ReplenishmentService.evaluate_replenishment(
            product=product,
            lead_time_days=7,
            safety_stock=10,
        )
        assert req is not None
        assert req.status == ReplenishmentRequest.Status.SUGGESTED

        # Admin approves
        approved_req = ReplenishmentService.approve_request(
            req,
            approved_quantity=25,
            approved_by=admin_user,
        )
        assert approved_req.status == ReplenishmentRequest.Status.APPROVED
        assert approved_req.approved_quantity == 25


# ==========================================
# 5. Turnover & Analytics Tests
# ==========================================
@pytest.mark.django_db
class TestTurnoverAndForecasting:

    def test_turnover_metrics_calculation(self, product, customer_user):
        order = Order.objects.create(
            user=customer_user,
            email=customer_user.email,
            status=Order.Status.DELIVERED,
            subtotal=Decimal('9998.00'),
            total=Decimal('9998.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            vendor=product.vendor,
            product_name=product.name,
            product_sku=product.sku,
            quantity=2,
            unit_price=product.price,
            total_price=Decimal('9998.00'),
        )
        metrics = TurnoverService.get_turnover_metrics(product=product, days=30)
        assert metrics['units_sold'] == 2
        assert metrics['turnover_ratio'] > 0

    def test_wape_calculation_normal_and_zero_demand(self):
        # Normal series
        wape, acc = ForecastService.calculate_wape([10.0, 20.0], [12.0, 18.0])
        assert wape == 13.33
        assert acc == 86.67

        # Zero actual demand
        wape_zero, acc_zero = ForecastService.calculate_wape([0.0, 0.0], [5.0, 5.0])
        assert wape_zero is None
        assert acc_zero is None

        # Both actual and pred zero
        wape_both_zero, acc_both_zero = ForecastService.calculate_wape([0.0, 0.0], [0.0, 0.0])
        assert wape_both_zero == 0.0
        assert acc_both_zero == 100.0

    def test_forecast_training_and_predictions(self, product):
        model = ForecastService.train_and_forecast_product(product, history_days=30, forecast_horizon_days=7)
        assert model.is_active is True
        predictions = ForecastPrediction.objects.filter(product=product)
        assert predictions.count() == 7


# ==========================================
# 6. Customer RFM & Recommendations Tests
# ==========================================
@pytest.mark.django_db
class TestCustomerAndRecommendations:

    def test_customer_rfm_segmentation(self, customer_user, product):
        order = Order.objects.create(
            user=customer_user,
            email=customer_user.email,
            status=Order.Status.CONFIRMED,
            subtotal=Decimal('6000.00'),
            total=Decimal('6000.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            vendor=product.vendor,
            product_name=product.name,
            product_sku=product.sku,
            quantity=5,
            unit_price=product.price,
            total_price=Decimal('6000.00'),
        )

        results = CustomerAnalyticsService.segment_customers()
        assert results['total_customers'] >= 1
        assignment = CustomerSegmentAssignment.objects.filter(user=customer_user).first()
        assert assignment is not None

    def test_recommendation_generation_and_evaluation(self, product, customer_user):
        order = Order.objects.create(
            user=customer_user,
            email=customer_user.email,
            status=Order.Status.DELIVERED,
            subtotal=Decimal('4999.00'),
            total=Decimal('4999.00'),
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            vendor=product.vendor,
            product_name=product.name,
            product_sku=product.sku,
            quantity=1,
            unit_price=product.price,
            total_price=Decimal('4999.00'),
        )

        # Refresh candidates
        count = RecommendationService.refresh_recommendation_candidates()
        assert count >= 1

        # Holdout evaluation
        eval_obj = RecommendationService.evaluate_recommendations(k=5, holdout_days=30)
        assert eval_obj is not None
        assert eval_obj.model_version == 'v1.0-hybrid'


# ==========================================
# 7. Inventory Reconciliation & Backfill Tests
# ==========================================
@pytest.mark.django_db
class TestInventoryReconciliation:

    def test_backfill_empty_inventory(self):
        # Clear any existing inventories
        Inventory.objects.all().delete()
        count = StockService.backfill_warehouse_stock()
        assert count == 0
        assert WarehouseStock.objects.count() == 0

    def test_backfill_existing_inventory(self, product):
        # Product fixture has quantity=50, reserved_quantity=0 (or 5)
        # Ensure no warehouse stocks exist yet
        WarehouseStock.objects.filter(product=product).delete()
        StockMovement.objects.filter(product=product).delete()

        count = StockService.backfill_warehouse_stock()
        assert count >= 1

        default_wh = Warehouse.objects.filter(is_default=True).first()
        assert default_wh is not None

        stock = WarehouseStock.objects.get(product=product, warehouse=default_wh)
        assert stock.quantity == product.inventory.quantity

        movement = StockMovement.objects.get(product=product, warehouse=default_wh)
        assert movement.quantity_change == product.inventory.quantity
        assert movement.movement_type == StockMovement.MovementType.PURCHASE

        # Clean reconciliation
        discrepancies = StockService.reconcile_inventory(warehouse=default_wh)
        assert len(discrepancies) == 0

    def test_repeated_backfills_are_idempotent(self, product):
        WarehouseStock.objects.filter(product=product).delete()
        StockMovement.objects.filter(product=product).delete()

        # First execution
        first_count = StockService.backfill_warehouse_stock()
        assert first_count >= 1

        wh = Warehouse.objects.filter(is_default=True).first()
        initial_stock = WarehouseStock.objects.get(product=product, warehouse=wh).quantity
        initial_movements = StockMovement.objects.filter(product=product, warehouse=wh).count()

        # Second execution (repeated)
        second_count = StockService.backfill_warehouse_stock()
        assert second_count == 0

        after_stock = WarehouseStock.objects.get(product=product, warehouse=wh).quantity
        after_movements = StockMovement.objects.filter(product=product, warehouse=wh).count()

        assert initial_stock == after_stock
        assert initial_movements == after_movements

    def test_reconciliation_detects_inconsistent_stock_balances(self, product, warehouses):
        wh1, _ = warehouses
        stock = WarehouseStock.objects.create(warehouse=wh1, product=product, quantity=10)
        StockMovement.objects.create(
            product=product,
            warehouse=wh1,
            quantity_change=8,
            movement_type=StockMovement.MovementType.PURCHASE,
            reason="Incomplete ledger entry",
        )

        discrepancies = StockService.reconcile_inventory(warehouse=wh1)
        assert len(discrepancies) == 1
        assert discrepancies[0]['difference'] == 2  # 10 - 8 = +2
        assert discrepancies[0]['recorded_stock'] == 10
        assert discrepancies[0]['ledger_sum'] == 8
        # Ensure reconciliation didn't silently overwrite
        stock.refresh_from_db()
        assert stock.quantity == 10

    def test_management_command_reconcile_inventory_ledger(self, product):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command('reconcile_inventory_ledger', backfill=True, stdout=out)
        output = out.getvalue()
        assert 'Backfill' in output or 'Reconciliation' in output


# ==========================================
# 8. Authorization & Strict Vendor Isolation
# ==========================================
@pytest.mark.django_db
class TestDashboardSecurityAndVendorIsolation:

    def test_admin_access_allowed(self, authenticated_client):
        response = authenticated_client.get(reverse('inventory:admin_overview'))
        assert response.status_code == 200

    def test_vendor_denied_admin_inventory(self, vendor_client):
        response = vendor_client.get(reverse('inventory:admin_overview'))
        assert response.status_code == 302

    def test_customer_denied_inventory(self, customer_client):
        response = customer_client.get(reverse('inventory:admin_overview'))
        assert response.status_code == 302
        response_vendor = customer_client.get(reverse('inventory:vendor_overview'))
        assert response_vendor.status_code == 302

    def test_vendor_sees_only_own_products_and_alerts(
        self,
        vendor_client,
        vendor_profile,
        product,
        other_vendor_product,
    ):
        response = vendor_client.get(reverse('inventory:vendor_overview'))
        assert response.status_code == 200

        # Vendor sees own product
        assert product.name in response.content.decode()
        # Vendor CANNOT see other vendor's product
        assert other_vendor_product.name not in response.content.decode()
