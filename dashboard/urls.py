"""
URL configuration for ShopSense Dashboard app.
"""

from django.urls import path

from catalog import views as catalog_views
from orders import admin_views as order_admin_views
from vendors import views as vendor_views

from . import bi_views, views

app_name = 'dashboard'

urlpatterns = [
    path('', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('settings/', views.AdminSettingsView.as_view(), name='admin_settings'),
    path('reports/', views.AdminReportsView.as_view(), name='admin_reports'),

    # Business Intelligence & Analytics URLs
    path('bi/', bi_views.AdminBusinessIntelligenceView.as_view(), name='bi_overview'),
    path('bi/customers/', bi_views.CustomerIntelligenceDashboardView.as_view(), name='bi_customers'),
    path('bi/inventory/', bi_views.InventoryIntelligenceDashboardView.as_view(), name='bi_inventory'),
    path('bi/recommendations/', bi_views.RecommendationIntelligenceDashboardView.as_view(), name='bi_recommendations'),
    path('bi/export/', bi_views.ExportReportView.as_view(), name='export_report'),
    path('bi/export/pdf/', bi_views.ExportPDFReportView.as_view(), name='bi_export_pdf'),
    path('bi/export/excel/', bi_views.ExportExcelReportView.as_view(), name='bi_export_excel'),

    # Vendor management URLs
    path('vendors/applications/', vendor_views.VendorApplicationListView.as_view(), name='vendor_applications'),
    path('vendors/applications/<int:pk>/', vendor_views.VendorApplicationDetailView.as_view(), name='vendor_application_detail'),
    path('vendors/applications/<int:pk>/action/', vendor_views.VendorApplicationActionView.as_view(), name='vendor_application_action'),
    path('vendors/', vendor_views.VendorListView.as_view(), name='vendor_list'),
    path('vendors/<int:pk>/', vendor_views.VendorDetailView.as_view(), name='vendor_detail'),

    # Product management URLs
    path('products/', catalog_views.ProductListView.as_view(), name='product_list'),
    path('products/create/', catalog_views.ProductCreateView.as_view(), name='product_create'),
    path('products/<int:pk>/', catalog_views.ProductDetailView.as_view(), name='product_detail'),
    path('products/<int:pk>/edit/', catalog_views.ProductUpdateView.as_view(), name='product_edit'),
    path('products/<int:pk>/delete/', catalog_views.ProductDeleteView.as_view(), name='product_delete'),
    path('products/<int:pk>/images/<int:image_pk>/delete/', catalog_views.ProductImageDeleteView.as_view(), name='product_image_delete'),

    # Order management URLs
    path('orders/', order_admin_views.AdminOrderListView.as_view(), name='order_list'),
    path('orders/<str:order_number>/', order_admin_views.AdminOrderDetailView.as_view(), name='order_detail'),
    path('orders/<str:order_number>/status/', order_admin_views.AdminOrderStatusUpdateView.as_view(), name='order_status_update'),
]