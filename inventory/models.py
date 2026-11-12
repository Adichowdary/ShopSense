"""
Models for ShopSense Inventory and Customer Analytics.
"""

from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Warehouse(models.Model):
    """Physical storage and fulfillment warehouse."""

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Active')
        INACTIVE = 'INACTIVE', _('Inactive')
        MAINTENANCE = 'MAINTENANCE', _('Under Maintenance')

    name = models.CharField(_('name'), max_length=255)
    code = models.CharField(_('code'), max_length=50, unique=True)
    address_line1 = models.CharField(_('address line 1'), max_length=255, blank=True)
    address_line2 = models.CharField(_('address line 2'), max_length=255, blank=True)
    city = models.CharField(_('city'), max_length=100, blank=True)
    state = models.CharField(_('state'), max_length=100, blank=True)
    postal_code = models.CharField(_('postal code'), max_length=20, blank=True)
    country = models.CharField(_('country'), max_length=100, default='India')
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    is_default = models.BooleanField(
        _('is default'),
        default=False,
        help_text=_('Default warehouse used for storefront inventory syncing and fulfillment'),
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_warehouses',
        verbose_name=_('manager'),
    )
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('warehouse')
        verbose_name_plural = _('warehouses')
        ordering = ['-is_default', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['is_default'],
                condition=models.Q(is_default=True),
                name='unique_default_warehouse',
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        if self.is_default:
            # Ensure only one default warehouse exists transactionally
            Warehouse.objects.exclude(pk=self.pk).filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


class WarehouseStock(models.Model):
    """Inventory levels for a specific product in a specific warehouse."""

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='stocks',
        verbose_name=_('warehouse'),
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        related_name='warehouse_stocks',
        verbose_name=_('product'),
    )
    quantity = models.IntegerField(_('on-hand quantity'), default=0)
    reserved_quantity = models.IntegerField(_('reserved quantity'), default=0)
    damaged_quantity = models.IntegerField(_('damaged quantity'), default=0)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('warehouse stock')
        verbose_name_plural = _('warehouse stocks')
        constraints = [
            models.UniqueConstraint(
                fields=['warehouse', 'product'],
                name='unique_warehouse_product_stock',
            ),
            models.CheckConstraint(
                check=models.Q(quantity__gte=0),
                name='warehouse_stock_quantity_nonnegative',
            ),
            models.CheckConstraint(
                check=models.Q(reserved_quantity__gte=0),
                name='warehouse_stock_reserved_nonnegative',
            ),
            models.CheckConstraint(
                check=models.Q(damaged_quantity__gte=0),
                name='warehouse_stock_damaged_nonnegative',
            ),
        ]

    def __str__(self):
        return f"{self.product.name} @ {self.warehouse.name}: {self.available_quantity} available"

    @property
    def available_quantity(self):
        """Available quantity = Physical On-Hand - Reserved - Damaged."""
        return max(0, self.quantity - self.reserved_quantity - self.damaged_quantity)


class StockMovement(models.Model):
    """
    Append-only audit ledger of every inventory change.
    Every stock-changing event produces an atomic ledger entry.
    """

    class MovementType(models.TextChoices):
        PURCHASE = 'PURCHASE', _('Purchase / Inbound')
        SALE = 'SALE', _('Sale / Checkout Deduction')
        RETURN = 'RETURN', _('Customer Return')
        TRANSFER_IN = 'TRANSFER_IN', _('Transfer Inbound')
        TRANSFER_OUT = 'TRANSFER_OUT', _('Transfer Outbound')
        ADJUSTMENT = 'ADJUSTMENT', _('Manual Adjustment')
        CANCELLATION = 'CANCELLATION', _('Order Cancellation Restock')
        DAMAGE = 'DAMAGE', _('Damage Write-off')

    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        related_name='stock_movements',
        verbose_name=_('product'),
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
        verbose_name=_('warehouse'),
    )
    quantity_change = models.IntegerField(_('quantity change'))
    movement_type = models.CharField(
        _('movement type'),
        max_length=32,
        choices=MovementType.choices,
    )
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
        verbose_name=_('order'),
    )
    transfer = models.ForeignKey(
        'StockTransfer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movements',
        verbose_name=_('stock transfer'),
    )
    reason = models.CharField(_('reason'), max_length=255)
    notes = models.TextField(_('notes'), blank=True)
    idempotency_key = models.CharField(
        _('idempotency key'),
        max_length=128,
        unique=True,
        null=True,
        blank=True,
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='performed_stock_movements',
        verbose_name=_('performed by'),
    )
    timestamp = models.DateTimeField(_('timestamp'), default=timezone.now, db_index=True)

    class Meta:
        verbose_name = _('stock movement')
        verbose_name_plural = _('stock movements')
        ordering = ['-timestamp']

    def __str__(self):
        sign = '+' if self.quantity_change > 0 else ''
        return f"[{self.movement_type}] {self.product.sku}: {sign}{self.quantity_change} ({self.timestamp:%Y-%m-%d %H:%M})"

    def save(self, *args, **kwargs):
        if self.pk:
            # Enforce append-only integrity: prohibit modifications to existing ledger entries
            existing = StockMovement.objects.filter(pk=self.pk).exists()
            if existing:
                raise ValidationError(_("StockMovement ledger entries are append-only and cannot be modified."))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(_("StockMovement ledger entries are append-only and cannot be deleted."))


class StockTransfer(models.Model):
    """Transfer of stock between warehouses."""

    class TransferStatus(models.TextChoices):
        REQUESTED = 'REQUESTED', _('Requested')
        APPROVED = 'APPROVED', _('Approved')
        IN_TRANSIT = 'IN_TRANSIT', _('In Transit')
        RECEIVED = 'RECEIVED', _('Received')
        CANCELLED = 'CANCELLED', _('Cancelled')

    transfer_number = models.CharField(_('transfer number'), max_length=64, unique=True)
    source_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='outgoing_transfers',
        verbose_name=_('source warehouse'),
    )
    destination_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='incoming_transfers',
        verbose_name=_('destination warehouse'),
    )
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=TransferStatus.choices,
        default=TransferStatus.REQUESTED,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requested_transfers',
        verbose_name=_('requested by'),
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_transfers',
        verbose_name=_('approved by'),
    )
    shipped_at = models.DateTimeField(_('shipped at'), null=True, blank=True)
    received_at = models.DateTimeField(_('received at'), null=True, blank=True)
    cancelled_at = models.DateTimeField(_('cancelled at'), null=True, blank=True)
    notes = models.TextField(_('notes'), blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('stock transfer')
        verbose_name_plural = _('stock transfers')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transfer_number} ({self.source_warehouse.code} -> {self.destination_warehouse.code}): {self.status}"

    def clean(self):
        super().clean()
        if self.source_warehouse_id and self.destination_warehouse_id:
            if self.source_warehouse_id == self.destination_warehouse_id:
                raise ValidationError(_("Source and destination warehouses must be different."))


class StockTransferItem(models.Model):
    """Line item in a stock transfer."""

    transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('transfer'),
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        related_name='transfer_items',
        verbose_name=_('product'),
    )
    requested_quantity = models.PositiveIntegerField(_('requested quantity'))
    shipped_quantity = models.PositiveIntegerField(_('shipped quantity'), default=0)
    received_quantity = models.PositiveIntegerField(_('received quantity'), default=0)

    class Meta:
        verbose_name = _('stock transfer item')
        verbose_name_plural = _('stock transfer items')
        constraints = [
            models.UniqueConstraint(
                fields=['transfer', 'product'],
                name='unique_transfer_product_item',
            ),
        ]

    def __str__(self):
        return f"{self.product.sku}: req {self.requested_quantity}, shipped {self.shipped_quantity}, received {self.received_quantity}"


class LowStockAlert(models.Model):
    """Alert raised when available inventory breaches configured thresholds."""

    class AlertType(models.TextChoices):
        LOW_STOCK = 'LOW_STOCK', _('Low Stock Threshold Breached')
        OUT_OF_STOCK = 'OUT_OF_STOCK', _('Out of Stock')
        PROJECTED_STOCKOUT = 'PROJECTED_STOCKOUT', _('Projected Stockout')

    class Severity(models.TextChoices):
        INFO = 'INFO', _('Info')
        WARNING = 'WARNING', _('Warning')
        CRITICAL = 'CRITICAL', _('Critical')

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Active')
        ACKNOWLEDGED = 'ACKNOWLEDGED', _('Acknowledged')
        RESOLVED = 'RESOLVED', _('Resolved')

    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        related_name='low_stock_alerts',
        verbose_name=_('product'),
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='low_stock_alerts',
        verbose_name=_('warehouse'),
    )
    alert_type = models.CharField(
        _('alert type'),
        max_length=32,
        choices=AlertType.choices,
        default=AlertType.LOW_STOCK,
    )
    severity = models.CharField(
        _('severity'),
        max_length=16,
        choices=Severity.choices,
        default=Severity.WARNING,
    )
    threshold = models.IntegerField(_('threshold'))
    observed_stock = models.IntegerField(_('observed stock'))
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_alerts',
        verbose_name=_('acknowledged by'),
    )
    acknowledged_at = models.DateTimeField(_('acknowledged at'), null=True, blank=True)
    resolved_at = models.DateTimeField(_('resolved at'), null=True, blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('low stock alert')
        verbose_name_plural = _('low stock alerts')
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.severity}] {self.product.sku} ({self.alert_type}): {self.observed_stock} <= {self.threshold} [{self.status}]"


class ReplenishmentRequest(models.Model):
    """Suggested or approved inventory replenishment order."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Draft')
        SUGGESTED = 'SUGGESTED', _('Suggested')
        APPROVED = 'APPROVED', _('Approved')
        REJECTED = 'REJECTED', _('Rejected')
        ORDERED = 'ORDERED', _('Ordered')
        COMPLETED = 'COMPLETED', _('Completed')

    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        related_name='replenishment_requests',
        verbose_name=_('product'),
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replenishment_requests',
        verbose_name=_('warehouse'),
    )
    suggested_quantity = models.PositiveIntegerField(_('suggested quantity'))
    approved_quantity = models.PositiveIntegerField(_('approved quantity'), null=True, blank=True)
    observed_stock = models.IntegerField(_('observed stock'))
    safety_stock = models.IntegerField(_('safety stock'), default=0)
    lead_time_days = models.IntegerField(_('lead time days'), default=7)
    reorder_point = models.IntegerField(_('reorder point'))
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.SUGGESTED,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requested_replenishments',
        verbose_name=_('requested by'),
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_replenishments',
        verbose_name=_('approved by'),
    )
    notes = models.TextField(_('notes'), blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)

    class Meta:
        verbose_name = _('replenishment request')
        verbose_name_plural = _('replenishment requests')
        ordering = ['-created_at']

    def __str__(self):
        return f"Replenish {self.product.sku}: suggested {self.suggested_quantity} ({self.status})"


class ForecastModel(models.Model):
    """Trained demand forecasting model configuration and metrics."""

    model_type = models.CharField(_('model type'), max_length=64)
    version = models.CharField(_('version'), max_length=32)
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='forecast_models',
        verbose_name=_('product scope'),
    )
    training_cutoff = models.DateTimeField(_('training cutoff'))
    forecast_horizon_days = models.PositiveIntegerField(_('forecast horizon days'), default=30)
    metrics = models.JSONField(_('evaluation metrics'), default=dict)
    parameters = models.JSONField(_('model parameters'), default=dict)
    is_active = models.BooleanField(_('is active'), default=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)

    class Meta:
        verbose_name = _('forecast model')
        verbose_name_plural = _('forecast models')
        ordering = ['-created_at']

    def __str__(self):
        scope = self.product.sku if self.product else "Global"
        return f"{self.model_type} v{self.version} [{scope}]"


class ForecastPrediction(models.Model):
    """Individual daily demand prediction produced by a forecast model."""

    forecast_model = models.ForeignKey(
        ForecastModel,
        on_delete=models.CASCADE,
        related_name='predictions',
        verbose_name=_('forecast model'),
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        related_name='forecast_predictions',
        verbose_name=_('product'),
    )
    prediction_date = models.DateField(_('prediction date'), db_index=True)
    predicted_demand = models.FloatField(_('predicted demand'))
    lower_bound = models.FloatField(_('lower bound'), null=True, blank=True)
    upper_bound = models.FloatField(_('upper bound'), null=True, blank=True)
    actual_demand = models.FloatField(_('actual demand'), null=True, blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)

    class Meta:
        verbose_name = _('forecast prediction')
        verbose_name_plural = _('forecast predictions')
        ordering = ['prediction_date']
        constraints = [
            models.UniqueConstraint(
                fields=['forecast_model', 'product', 'prediction_date'],
                name='unique_forecast_product_date',
            ),
        ]

    def __str__(self):
        return f"{self.product.sku} on {self.prediction_date}: predicted {self.predicted_demand}"


class CustomerSegment(models.Model):
    """Customer segment definition based on RFM analytics."""

    name = models.CharField(_('name'), max_length=128)
    code = models.CharField(_('code'), max_length=64, unique=True)
    description = models.TextField(_('description'), blank=True)
    criteria = models.JSONField(_('criteria'), default=dict)
    model_version = models.CharField(_('model version'), max_length=32, default='v1.0')
    is_active = models.BooleanField(_('is active'), default=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)

    class Meta:
        verbose_name = _('customer segment')
        verbose_name_plural = _('customer segments')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class CustomerSegmentAssignment(models.Model):
    """Customer assignment to an RFM segment with recorded feature scores."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='segment_assignments',
        verbose_name=_('customer'),
    )
    segment = models.ForeignKey(
        CustomerSegment,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name=_('segment'),
    )
    recency_days = models.IntegerField(_('recency (days)'), default=0)
    frequency = models.IntegerField(_('frequency (orders)'), default=0)
    monetary_value = models.DecimalField(_('monetary value (INR)'), max_digits=12, decimal_places=2, default=Decimal('0.00'))
    features = models.JSONField(_('features'), default=dict)
    assigned_at = models.DateTimeField(_('assigned at'), default=timezone.now)

    class Meta:
        verbose_name = _('segment assignment')
        verbose_name_plural = _('segment assignments')
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'segment'],
                name='unique_user_segment',
            ),
        ]

    def __str__(self):
        return f"{self.user.email} -> {self.segment.name}"


class RecommendationCandidate(models.Model):
    """Precomputed product recommendation for customers or storefront."""

    class RecommendationType(models.TextChoices):
        POPULAR = 'POPULAR', _('Popular / Best Seller')
        CATEGORY = 'CATEGORY', _('Category Based')
        CO_PURCHASE = 'CO_PURCHASE', _('Frequently Bought Together')
        PERSONALIZED = 'PERSONALIZED', _('Personalized Customer History')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='recommendations',
        verbose_name=_('customer'),
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        related_name='recommendation_records',
        verbose_name=_('product'),
    )
    recommendation_type = models.CharField(
        _('type'),
        max_length=32,
        choices=RecommendationType.choices,
        default=RecommendationType.POPULAR,
    )
    score = models.FloatField(_('score'), default=0.0)
    rank = models.PositiveIntegerField(_('rank'), default=1)
    reason = models.CharField(_('reason'), max_length=255, blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)

    class Meta:
        verbose_name = _('recommendation candidate')
        verbose_name_plural = _('recommendation candidates')
        ordering = ['rank', '-score']

    def __str__(self):
        target = self.user.email if self.user else "Anonymous/Storefront"
        return f"{target} -> {self.product.sku} ({self.recommendation_type}, rank {self.rank})"


class RecommendationEvaluation(models.Model):
    """Evaluation metrics for recommendation system."""

    model_version = models.CharField(_('model version'), max_length=32)
    evaluation_date = models.DateField(_('evaluation date'), default=timezone.now)
    sample_size = models.IntegerField(_('sample size'), default=0)
    coverage_percentage = models.FloatField(_('coverage percentage'), default=0.0)
    precision_at_k = models.FloatField(_('precision@k'), default=0.0)
    k_value = models.PositiveIntegerField(_('k value'), default=5)
    metrics = models.JSONField(_('metrics'), default=dict)
    notes = models.TextField(_('notes'), blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)

    class Meta:
        verbose_name = _('recommendation evaluation')
        verbose_name_plural = _('recommendation evaluations')
        ordering = ['-evaluation_date']

    def __str__(self):
        return f"Eval v{self.model_version} on {self.evaluation_date}: P@{self.k_value}={self.precision_at_k:.2f}"


class AnalyticalWorkflowRun(models.Model):
    """Execution history and status log for scheduled analytical workflows."""

    class WorkflowName(models.TextChoices):
        REVENUE_ANALYTICS = 'REVENUE_ANALYTICS', _('Revenue Analytics Processing')
        INVENTORY_FORECAST = 'INVENTORY_FORECAST', _('Inventory Forecast Generation')
        CUSTOMER_SEGMENTATION = 'CUSTOMER_SEGMENTATION', _('Customer Segmentation')
        PRODUCT_RECOMMENDATION = 'PRODUCT_RECOMMENDATION', _('Product Recommendation Generation')
        DASHBOARD_METRIC_REFRESH = 'DASHBOARD_METRIC_REFRESH', _('Dashboard Metric Refresh')
        ANALYTICAL_REPORT_GENERATION = 'ANALYTICAL_REPORT_GENERATION', _('Analytical Report Generation')
        MODEL_EVALUATION_TRACKING = 'MODEL_EVALUATION_TRACKING', _('Model Evaluation and Tracking')

    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        RUNNING = 'RUNNING', _('Running')
        SUCCESS = 'SUCCESS', _('Success')
        FAILED = 'FAILED', _('Failed')
        RETRYING = 'RETRYING', _('Retrying')

    workflow_name = models.CharField(
        _('workflow name'),
        max_length=64,
        choices=WorkflowName.choices,
        db_index=True,
    )
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    start_time = models.DateTimeField(_('start time'), default=timezone.now)
    end_time = models.DateTimeField(_('end time'), null=True, blank=True)
    duration_seconds = models.FloatField(_('duration (seconds)'), default=0.0)
    retry_count = models.PositiveIntegerField(_('retry count'), default=0)
    error_message = models.TextField(_('error message'), blank=True)
    metadata = models.JSONField(_('execution metadata'), default=dict, blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)

    class Meta:
        verbose_name = _('analytical workflow run')
        verbose_name_plural = _('analytical workflow runs')
        ordering = ['-start_time']

    def __str__(self):
        return f"{self.workflow_name} [{self.status}] @ {self.start_time:%Y-%m-%d %H:%M:%S}"


class DataConsistencyLog(models.Model):
    """Audit log of automated reconciliation between source records and analytical metrics."""

    run_date = models.DateTimeField(_('run date'), default=timezone.now)
    overall_consistency_percentage = models.FloatField(_('overall consistency %'), default=100.0)
    passed = models.BooleanField(_('passed threshold (>= 99%)'), default=True)
    metrics_compared = models.JSONField(_('metrics compared'), default=dict)
    discrepancies = models.JSONField(_('discrepancies'), default=list, blank=True)
    notes = models.TextField(_('notes'), blank=True)
    created_at = models.DateTimeField(_('created at'), default=timezone.now)

    class Meta:
        verbose_name = _('data consistency log')
        verbose_name_plural = _('data consistency logs')
        ordering = ['-run_date']

    def __str__(self):
        return f"Consistency Log @ {self.run_date:%Y-%m-%d %H:%M}: {self.overall_consistency_percentage:.2f}% (Passed: {self.passed})"

