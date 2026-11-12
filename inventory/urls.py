"""
URL configuration for ShopSense Inventory and Analytics app.
"""

from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Dashboard overviews
    path('admin/overview/', views.AdminInventoryDashboardView.as_view(), name='admin_overview'),
    path('vendor/overview/', views.VendorInventoryDashboardView.as_view(), name='vendor_overview'),

    # Alert & replenishment actions
    path('alerts/<int:pk>/acknowledge/', views.AcknowledgeAlertActionView.as_view(), name='acknowledge_alert'),
    path('replenishments/<int:pk>/action/', views.ApproveReplenishmentActionView.as_view(), name='approve_replenishment'),

    # Transfers
    path('transfers/', views.WarehouseTransferListView.as_view(), name='transfer_list'),
    path('transfers/create/', views.WarehouseTransferCreateView.as_view(), name='transfer_create'),
    path('transfers/<int:pk>/action/', views.WarehouseTransferActionView.as_view(), name='transfer_action'),
]
