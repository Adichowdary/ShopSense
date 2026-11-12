"""
URL configuration for ShopSense Vendors app.
"""

from django.urls import path

from orders import vendor_views as order_vendor_views

from . import views

app_name = 'vendors'

urlpatterns = [
    # Public vendor onboarding
    path('onboarding/', views.VendorOnboardingView.as_view(), name='onboarding'),
    path('application/submitted/', views.ApplicationSubmittedView.as_view(), name='application_submitted'),

    # Vendor self-service (requires vendor role)
    path('profile/', views.VendorProfileView.as_view(), name='profile'),
    path('profile/edit/', views.VendorUpdateView.as_view(), name='profile_edit'),

    # Vendor order management
    path('orders/', order_vendor_views.VendorOrderListView.as_view(), name='order_list'),
    path('orders/<str:order_number>/', order_vendor_views.VendorOrderDetailView.as_view(), name='order_detail'),
    path('orders/<str:order_number>/items/<int:item_pk>/fulfill/', order_vendor_views.VendorOrderItemFulfillView.as_view(), name='order_item_fulfill'),

    # Admin vendor management (requires admin role)
    path('admin/applications/', views.VendorApplicationListView.as_view(), name='admin_applications'),
    path('admin/applications/<int:pk>/', views.VendorApplicationDetailView.as_view(), name='admin_application_detail'),
    path('admin/applications/<int:pk>/action/', views.VendorApplicationActionView.as_view(), name='admin_application_action'),
    path('admin/vendors/', views.VendorListView.as_view(), name='admin_vendor_list'),
    path('admin/vendors/<int:pk>/', views.VendorDetailView.as_view(), name='admin_vendor_detail'),
]