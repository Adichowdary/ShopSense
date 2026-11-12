"""
Context processors for ShopSense Orders app.
"""

from .models import Cart


def cart_context(request):
    """Provide cart total items count to all templates."""
    cart_items_count = 0
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.filter(user=request.user).first()
            if cart:
                cart_items_count = cart.total_items
        except Exception:
            cart_items_count = 0

    return {
        'cart_items_count': cart_items_count,
    }
