"""
Views for ShopSense Orders app: Cart, Concurrency-Safe Checkout, and Order History.
"""

import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, TemplateView, View

from catalog.models import Inventory, Product

from .models import Address, Cart, CartItem, Order, OrderItem, Payment

logger = logging.getLogger(__name__)

# Constants for shipping calculation
FREE_SHIPPING_THRESHOLD = Decimal('50.00')
STANDARD_SHIPPING_FEE = Decimal('5.00')
TAX_RATE = Decimal('0.05')  # 5% estimated tax


def calculate_order_financials(subtotal):
    """Calculate shipping fee, tax, and grand total based on subtotal."""
    if subtotal <= 0:
        return Decimal('0.00'), Decimal('0.00'), Decimal('0.00')

    shipping = Decimal('0.00') if subtotal >= FREE_SHIPPING_THRESHOLD else STANDARD_SHIPPING_FEE
    tax = (subtotal * TAX_RATE).quantize(Decimal('0.01'))
    total = subtotal + shipping + tax
    return shipping, tax, total


class CartView(LoginRequiredMixin, TemplateView):
    """View customer shopping cart and order summary."""

    template_name = 'orders/cart.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart, _created = Cart.objects.get_or_create(user=self.request.user)

        # Prefetch items and check live inventory
        items = list(
            cart.items.select_related('product__inventory', 'product__vendor')
            .prefetch_related('product__images')
            .order_by('-created_at')
        )

        subtotal = sum(item.product.price * item.quantity for item in items)
        shipping, tax, total = calculate_order_financials(subtotal)
        qualifies_for_free_shipping = subtotal >= FREE_SHIPPING_THRESHOLD
        amount_needed_for_free_shipping = (
            max(Decimal('0.00'), FREE_SHIPPING_THRESHOLD - subtotal)
            if not qualifies_for_free_shipping
            else Decimal('0.00')
        )

        context.update({
            'page_title': _('Shopping Cart | ShopSense'),
            'cart': cart,
            'items': items,
            'subtotal': subtotal,
            'shipping': shipping,
            'tax': tax,
            'total': total,
            'free_shipping_threshold': FREE_SHIPPING_THRESHOLD,
            'qualifies_for_free_shipping': qualifies_for_free_shipping,
            'amount_needed_for_free_shipping': amount_needed_for_free_shipping,
        })
        return context


class AddToCartView(LoginRequiredMixin, View):
    """Add a product to customer cart with strict server-side inventory validation."""

    def post(self, request, *args, **kwargs):
        product_id = request.POST.get('product_id')
        try:
            quantity = int(request.POST.get('quantity', 1))
        except (ValueError, TypeError):
            quantity = 1

        if quantity < 1:
            quantity = 1

        product = get_object_or_404(
            Product.objects.select_related('inventory'),
            pk=product_id,
            status=Product.Status.ACTIVE,
        )

        available_stock = product.inventory.quantity if hasattr(product, 'inventory') else 0
        if available_stock <= 0:
            msg = _('Sorry, %(name)s is currently out of stock.') % {'name': product.name}
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': str(msg)}, status=400)
            messages.error(request, msg)
            return redirect(request.META.get('HTTP_REFERER', 'orders:cart'))

        cart, _created = Cart.objects.get_or_create(user=request.user)
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity},
        )

        if not created:
            new_qty = cart_item.quantity + quantity
            if new_qty > available_stock:
                cart_item.quantity = available_stock
                cart_item.save(update_fields=['quantity'])
                msg = _('Stock limit reached. Added %(avail)s units of %(name)s.') % {
                    'avail': available_stock,
                    'name': product.name,
                }
            else:
                cart_item.quantity = new_qty
                cart_item.save(update_fields=['quantity'])
                msg = _('Updated %(name)s quantity to %(qty)s in your cart.') % {
                    'name': product.name,
                    'qty': cart_item.quantity,
                }
        else:
            if quantity > available_stock:
                cart_item.quantity = available_stock
                cart_item.save(update_fields=['quantity'])
                msg = _('Added %(avail)s available units of %(name)s to your cart.') % {
                    'avail': available_stock,
                    'name': product.name,
                }
            else:
                msg = _('Added %(name)s to your cart.') % {'name': product.name}

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'success',
                'message': str(msg),
                'total_items': cart.total_items,
            })

        messages.success(request, msg)
        # Check if direct "Buy Now" flow was triggered
        if request.POST.get('buy_now'):
            return redirect('orders:checkout')
        return redirect('orders:cart')


class UpdateCartItemView(LoginRequiredMixin, View):
    """Update quantity of an existing cart item."""

    def post(self, request, pk, *args, **kwargs):
        cart = get_object_or_404(Cart, user=request.user)
        item = get_object_or_404(CartItem.objects.select_related('product__inventory'), pk=pk, cart=cart)

        try:
            quantity = int(request.POST.get('quantity', 1))
        except (ValueError, TypeError):
            quantity = 1

        if quantity <= 0:
            item.delete()
            messages.info(request, _('Removed %(name)s from your cart.') % {'name': item.product.name})
        else:
            available_stock = item.product.inventory.quantity if hasattr(item.product, 'inventory') else 0
            if quantity > available_stock:
                item.quantity = available_stock
                item.save(update_fields=['quantity'])
                messages.warning(
                    request,
                    _('Only %(avail)s units available for %(name)s.') % {
                        'avail': available_stock,
                        'name': item.product.name,
                    },
                )
            else:
                item.quantity = quantity
                item.save(update_fields=['quantity'])
                messages.success(request, _('Cart updated successfully.'))

        return redirect('orders:cart')


class RemoveFromCartView(LoginRequiredMixin, View):
    """Remove a specific item from cart."""

    def post(self, request, pk, *args, **kwargs):
        cart = get_object_or_404(Cart, user=request.user)
        item = get_object_or_404(CartItem, pk=pk, cart=cart)
        name = item.product.name
        item.delete()
        messages.info(request, _('Removed %(name)s from your cart.') % {'name': name})
        return redirect('orders:cart')


class ClearCartView(LoginRequiredMixin, View):
    """Clear all items from user's shopping cart."""

    def post(self, request, *args, **kwargs):
        cart = get_object_or_404(Cart, user=request.user)
        cart.items.all().delete()
        messages.info(request, _('Your cart has been cleared.'))
        return redirect('orders:cart')


class CheckoutView(LoginRequiredMixin, TemplateView):
    """Customer checkout view displaying cart review, saved delivery addresses, and payment selection."""

    template_name = 'orders/checkout.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        cart = Cart.objects.filter(user=request.user).first()
        if not cart or not cart.items.exists():
            messages.warning(request, _('Your cart is empty. Add products before checking out.'))
            return redirect('orders:cart')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart = Cart.objects.get(user=self.request.user)
        items = list(
            cart.items.select_related('product__inventory', 'product__vendor')
            .prefetch_related('product__images')
        )

        subtotal = sum(item.product.price * item.quantity for item in items)
        shipping, tax, total = calculate_order_financials(subtotal)
        addresses = Address.objects.filter(user=self.request.user)

        context.update({
            'page_title': _('Checkout | ShopSense'),
            'cart': cart,
            'items': items,
            'subtotal': subtotal,
            'shipping': shipping,
            'tax': tax,
            'total': total,
            'addresses': addresses,
            'default_address': addresses.filter(is_default=True).first() or addresses.first(),
        })
        return context


class PlaceOrderView(LoginRequiredMixin, View):
    """
    Process checkout and place order with database-level concurrency protection.
    Uses select_for_update() on Inventory rows within an atomic transaction
    to prevent race conditions and overselling.
    """

    def post(self, request, *args, **kwargs):
        cart = get_object_or_404(Cart, user=request.user)
        cart_items = list(cart.items.select_related('product').all())

        if not cart_items:
            messages.error(request, _('Your cart is empty.'))
            return redirect('orders:cart')

        # Address handling
        address_id = request.POST.get('address_id')
        shipping_first_name = request.POST.get('shipping_first_name', '').strip()
        shipping_last_name = request.POST.get('shipping_last_name', '').strip()
        shipping_phone = request.POST.get('shipping_phone', '').strip()
        shipping_address = request.POST.get('shipping_address', '').strip()
        shipping_city = request.POST.get('shipping_city', '').strip()
        shipping_state = request.POST.get('shipping_state', '').strip()
        shipping_postal_code = request.POST.get('shipping_postal_code', '').strip()
        shipping_country = request.POST.get('shipping_country', 'India').strip()
        save_address = request.POST.get('save_address')

        if address_id:
            try:
                addr = Address.objects.get(pk=address_id, user=request.user)
                shipping_first_name = addr.first_name
                shipping_last_name = addr.last_name
                shipping_phone = addr.phone
                shipping_address = addr.street_address
                shipping_city = addr.city
                shipping_state = addr.state
                shipping_postal_code = addr.postal_code
                shipping_country = addr.country
            except Address.DoesNotExist:
                messages.error(request, _('Selected address was not found.'))
                return redirect('orders:checkout')
        else:
            if not all([shipping_first_name, shipping_last_name, shipping_phone, shipping_address, shipping_city, shipping_state, shipping_postal_code]):
                messages.error(request, _('Please fill in all required shipping address fields.'))
                return redirect('orders:checkout')

            # Optionally save new address for customer
            if save_address:
                Address.objects.create(
                    user=request.user,
                    first_name=shipping_first_name,
                    last_name=shipping_last_name,
                    phone=shipping_phone,
                    street_address=shipping_address,
                    city=shipping_city,
                    state=shipping_state,
                    postal_code=shipping_postal_code,
                    country=shipping_country,
                    is_default=(not Address.objects.filter(user=request.user).exists()),
                )

        # Payment method
        payment_method = request.POST.get('payment_method', 'COD').upper()
        if payment_method not in [m.value for m in Payment.Method]:
            payment_method = Payment.Method.COD

        customer_notes = request.POST.get('customer_notes', '').strip()

        # Atomic transaction with concurrency row-locking
        try:
            with transaction.atomic():
                product_ids = [item.product_id for item in cart_items]
                # Lock inventory records to prevent concurrent checkouts from overselling
                locked_inventories = {
                    inv.product_id: inv
                    for inv in Inventory.objects.select_for_update().filter(product_id__in=product_ids)
                }

                # Verify stock for every item
                for item in cart_items:
                    inv = locked_inventories.get(item.product_id)
                    if not inv or inv.quantity < item.quantity:
                        avail = inv.quantity if inv else 0
                        messages.error(
                            request,
                            _('Sorry, "%(name)s" only has %(avail)s items in stock. Please adjust your cart.')
                            % {'name': item.product.name, 'avail': avail},
                        )
                        return redirect('orders:cart')

                # Calculate order totals from verified server prices
                subtotal = sum(item.product.price * item.quantity for item in cart_items)
                shipping_cost, tax_amount, total = calculate_order_financials(subtotal)

                # Create Order
                order = Order.objects.create(
                    user=request.user,
                    email=request.user.email,
                    phone=shipping_phone,
                    status=Order.Status.CONFIRMED,
                    shipping_first_name=shipping_first_name,
                    shipping_last_name=shipping_last_name,
                    shipping_address=shipping_address,
                    shipping_city=shipping_city,
                    shipping_state=shipping_state,
                    shipping_postal_code=shipping_postal_code,
                    shipping_country=shipping_country,
                    subtotal=subtotal,
                    shipping_cost=shipping_cost,
                    tax_amount=tax_amount,
                    total=total,
                    customer_notes=customer_notes,
                    confirmed_at=timezone.now(),
                )

                # Create Order Items and deduct inventory
                for item in cart_items:
                    product = item.product
                    inv = locked_inventories[product.id]

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        vendor=product.vendor,
                        product_name=product.name,
                        product_sku=product.sku,
                        quantity=item.quantity,
                        unit_price=product.price,
                        total_price=product.price * item.quantity,
                    )

                    # Deduct stock
                    inv.quantity -= item.quantity
                    inv.save(update_fields=['quantity', 'updated_at'])

                    # Mark product out of stock if quantity hits zero
                    if inv.quantity <= 0 and product.status == Product.Status.ACTIVE:
                        product.status = Product.Status.OUT_OF_STOCK
                        product.save(update_fields=['status', 'updated_at'])

                    # Synchronize warehouse stock and audit movement ledger
                    try:
                        from inventory.models import WarehouseStock, StockMovement
                        from inventory.services.stock_services import StockService

                        warehouse = StockService.get_or_create_default_warehouse()
                        wh_stock = WarehouseStock.objects.filter(warehouse=warehouse, product=product).first()
                        if wh_stock:
                            wh_stock.quantity = max(0, wh_stock.quantity - item.quantity)
                            wh_stock.save(update_fields=['quantity', 'updated_at'])

                        StockMovement.objects.create(
                            product=product,
                            warehouse=warehouse,
                            quantity_change=-item.quantity,
                            movement_type=StockMovement.MovementType.SALE,
                            order=order,
                            reason=f"Storefront checkout order #{order.order_number}",
                            performed_by=request.user if request.user.is_authenticated else None,
                        )
                    except Exception as stock_err:
                        logger.warning(f"Could not sync warehouse stock movement for {product.sku}: {stock_err}")

                # Record Payment
                Payment.objects.create(
                    order=order,
                    payment_id=f'PAY-{order.order_number}',
                    method=payment_method,
                    status=Payment.Status.COMPLETED if payment_method != Payment.Method.COD else Payment.Status.PENDING,
                    amount=order.total,
                    currency='INR',
                )

                # Clear shopping cart
                cart.items.all().delete()

            logger.info(f'Order {order.order_number} successfully placed by user {request.user.email}')
            messages.success(
                request,
                _('Order %(num)s placed successfully!') % {'num': order.order_number},
            )
            return redirect('orders:order_confirmation', order_number=order.order_number)

        except Exception as e:
            logger.exception('Failed to process checkout transaction')
            messages.error(request, _('An error occurred while placing your order. Please try again.'))
            return redirect('orders:checkout')


class OrderConfirmationView(LoginRequiredMixin, DetailView):
    """Customer order confirmation view."""

    model = Order
    template_name = 'orders/order_confirmation.html'
    context_object_name = 'order'
    slug_field = 'order_number'
    slug_url_kwarg = 'order_number'

    def get_queryset(self):
        # Strict customer scoping: Customers only see their own orders
        return Order.objects.filter(user=self.request.user).prefetch_related('items__product')


class OrderListView(LoginRequiredMixin, ListView):
    """Customer past orders history."""

    model = Order
    template_name = 'orders/order_list.html'
    context_object_name = 'orders'
    paginate_by = 10

    def get_queryset(self):
        # Strict customer scoping
        return (
            Order.objects.filter(user=self.request.user)
            .select_related('user')
            .prefetch_related('items__product__images')
            .order_by('-created_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('My Orders | ShopSense')
        return context


class OrderDetailView(LoginRequiredMixin, DetailView):
    """Customer order details and invoice receipt."""

    model = Order
    template_name = 'orders/order_detail.html'
    context_object_name = 'order'
    slug_field = 'order_number'
    slug_url_kwarg = 'order_number'

    def get_queryset(self):
        # Strict customer scoping
        return (
            Order.objects.filter(user=self.request.user)
            .select_related('user')
            .prefetch_related('items__product__images', 'items__vendor', 'payments')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Order %(num)s') % {'num': self.object.order_number}
        context['payment'] = self.object.payments.first()
        return context