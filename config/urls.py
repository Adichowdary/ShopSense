"""
URL configuration for ShopSense project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('vendors/', include('vendors.urls', namespace='vendors')),
    path('dashboard/', include('dashboard.urls', namespace='dashboard')),
    path('catalog/', include('catalog.urls', namespace='catalog')),
    path('orders/', include('orders.urls', namespace='orders')),
    path('inventory/', include('inventory.urls', namespace='inventory')),
    path('', include('catalog.storefront_urls', namespace='store')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Custom error handlers
handler404 = 'config.views.handler404'
handler500 = 'config.views.handler500'