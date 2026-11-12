"""
Admin registration for Inventory app.
"""

from django.contrib import admin
from .models import (
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
    AnalyticalWorkflowRun,
    DataConsistencyLog,
)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'city', 'state', 'status', 'is_default', 'manager', 'created_at')
    list_filter = ('status', 'is_default')
    search_fields = ('name', 'code', 'city')


@admin.register(WarehouseStock)
class WarehouseStockAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'quantity', 'reserved_quantity', 'damaged_quantity', 'available_quantity', 'updated_at')
    list_filter = ('warehouse',)
    search_fields = ('product__name', 'product__sku', 'warehouse__name')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'product', 'warehouse', 'movement_type', 'quantity_change', 'reason', 'performed_by')
    list_filter = ('movement_type', 'warehouse', 'timestamp')
    search_fields = ('product__sku', 'product__name', 'reason', 'idempotency_key')
    readonly_fields = [f.name for f in StockMovement._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StockTransferItemInline(admin.TabularInline):
    model = StockTransferItem
    extra = 1


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ('transfer_number', 'source_warehouse', 'destination_warehouse', 'status', 'requested_by', 'created_at')
    list_filter = ('status', 'source_warehouse', 'destination_warehouse')
    search_fields = ('transfer_number',)
    inlines = [StockTransferItemInline]


@admin.register(LowStockAlert)
class LowStockAlertAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'alert_type', 'severity', 'threshold', 'observed_stock', 'status', 'created_at')
    list_filter = ('alert_type', 'severity', 'status')
    search_fields = ('product__sku', 'product__name')


@admin.register(ReplenishmentRequest)
class ReplenishmentRequestAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'suggested_quantity', 'approved_quantity', 'status', 'requested_by', 'created_at')
    list_filter = ('status', 'warehouse')
    search_fields = ('product__sku', 'product__name')


@admin.register(ForecastModel)
class ForecastModelAdmin(admin.ModelAdmin):
    list_display = ('model_type', 'version', 'product', 'training_cutoff', 'is_active', 'created_at')
    list_filter = ('model_type', 'is_active')


@admin.register(ForecastPrediction)
class ForecastPredictionAdmin(admin.ModelAdmin):
    list_display = ('product', 'prediction_date', 'predicted_demand', 'actual_demand', 'forecast_model')
    list_filter = ('prediction_date', 'forecast_model')
    search_fields = ('product__sku',)


@admin.register(CustomerSegment)
class CustomerSegmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'model_version', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')


@admin.register(CustomerSegmentAssignment)
class CustomerSegmentAssignmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'segment', 'recency_days', 'frequency', 'monetary_value', 'assigned_at')
    list_filter = ('segment',)
    search_fields = ('user__email',)


@admin.register(RecommendationCandidate)
class RecommendationCandidateAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'recommendation_type', 'score', 'rank', 'created_at')
    list_filter = ('recommendation_type',)
    search_fields = ('product__sku', 'user__email')


@admin.register(RecommendationEvaluation)
class RecommendationEvaluationAdmin(admin.ModelAdmin):
    list_display = ('model_version', 'evaluation_date', 'precision_at_k', 'k_value', 'coverage_percentage', 'sample_size')


@admin.register(AnalyticalWorkflowRun)
class AnalyticalWorkflowRunAdmin(admin.ModelAdmin):
    list_display = ('workflow_name', 'status', 'start_time', 'end_time', 'duration_seconds', 'retry_count')
    list_filter = ('workflow_name', 'status', 'start_time')
    search_fields = ('workflow_name', 'error_message')
    readonly_fields = ('start_time', 'created_at')


@admin.register(DataConsistencyLog)
class DataConsistencyLogAdmin(admin.ModelAdmin):
    list_display = ('run_date', 'overall_consistency_percentage', 'passed', 'created_at')
    list_filter = ('passed', 'run_date')
    search_fields = ('notes',)
    readonly_fields = ('run_date', 'created_at')

