"""
URL configuration for ShopSense Orders app.
"""

from django.urls import path

from . import views

app_name = 'orders'

urlpatterns = [
    # Cart routes
    path('cart/', views.CartView.as_view(), name='cart'),
    path('cart/add/', views.AddToCartView.as_view(), name='cart_add'),
    path('cart/update/<int:pk>/', views.UpdateCartItemView.as_view(), name='cart_update'),
    path('cart/remove/<int:pk>/', views.RemoveFromCartView.as_view(), name='cart_remove'),
    path('cart/clear/', views.ClearCartView.as_view(), name='cart_clear'),

    # Checkout & Placement routes
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('checkout/place/', views.PlaceOrderView.as_view(), name='place_order'),
    path('order/confirmed/<str:order_number>/', views.OrderConfirmationView.as_view(), name='order_confirmation'),

    # Order History & Details
    path('my-orders/', views.OrderListView.as_view(), name='order_list'),
    path('my-orders/<str:order_number>/', views.OrderDetailView.as_view(), name='order_detail'),
]