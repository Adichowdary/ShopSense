"""
URL routes for ShopSense Customer Storefront.
"""

from django.urls import path
from . import storefront_views

app_name = 'store'

urlpatterns = [
    path('', storefront_views.StorefrontHomeView.as_view(), name='home'),
    path('products/', storefront_views.StorefrontProductListView.as_view(), name='product_list'),
    path('products/<int:pk>/', storefront_views.StorefrontProductDetailView.as_view(), name='product_detail'),
    path('products/<slug:slug>/', storefront_views.StorefrontProductDetailView.as_view(), name='product_detail_slug'),
    path('products/c/<slug:category>/', storefront_views.StorefrontProductListView.as_view(), name='category_products'),
]
