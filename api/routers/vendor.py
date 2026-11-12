"""
FastAPI Router: Vendor Analytics API.
Enforces strict multi-tenant vendor isolation.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from django.db.models import Count, Sum, F, Avg, Q
from django.contrib.auth import get_user_model

from api.auth import require_admin_or_vendor
from api.schemas import (
    VendorSummaryResponse,
    VendorProductPerformance,
    VendorInventorySummary,
)
from catalog.models import Product, Inventory
from orders.models import Order, OrderItem
from vendors.models import VendorProfile

router = APIRouter(prefix="/vendor", tags=["Vendor Analytics"])
User = get_user_model()


def resolve_target_vendor(user: User, vendor_id: Optional[int] = None) -> VendorProfile:
    """Resolve vendor profile while enforcing cross-vendor access prevention."""
    is_admin = hasattr(user, 'can_access_admin_dashboard') and user.can_access_admin_dashboard()
    
    if is_admin:
        if vendor_id:
            profile = VendorProfile.objects.filter(pk=vendor_id).first()
            if not profile:
                raise HTTPException(status_code=404, detail="Vendor not found")
            return profile
        first_vendor = VendorProfile.objects.filter(is_active=True).first()
        if not first_vendor:
            raise HTTPException(status_code=404, detail="No active vendors found in the marketplace")
        return first_vendor

    # Vendor user: must only access their own profile
    vendor_profile = getattr(user, 'vendor_profile', None)
    if not vendor_profile or not vendor_profile.is_active:
        raise HTTPException(status_code=403, detail="Active vendor profile required")
    
    if vendor_id and vendor_id != vendor_profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot inspect another vendor's performance metrics.",
        )
    return vendor_profile


@router.get("/summary", response_model=VendorSummaryResponse)
def get_vendor_summary(
    vendor_id: Optional[int] = Query(None, description="Vendor ID (Admin only or own ID)"),
    user: User = Depends(require_admin_or_vendor),
):
    """Retrieve high-level sales and operational summary for the vendor."""
    vendor = resolve_target_vendor(user, vendor_id)

    qualifying = [Order.Status.CONFIRMED, Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED]
    items = OrderItem.objects.filter(vendor=vendor, order__status__in=qualifying)

    agg = items.aggregate(
        total_sales=Sum('total_price'),
        total_units=Sum('quantity'),
        distinct_orders=Count('order', distinct=True),
    )
    total_sales = float(agg['total_sales'] or 0.0)
    total_units = int(agg['total_units'] or 0)
    total_orders = int(agg['distinct_orders'] or 0)
    aov = round(total_sales / total_orders, 2) if total_orders > 0 else 0.0

    active_products = Product.objects.filter(vendor=vendor, status=Product.Status.ACTIVE).count()

    return VendorSummaryResponse(
        vendor_id=vendor.vendor_id,
        business_name=vendor.business_name,
        total_sales=total_sales,
        total_orders=total_orders,
        total_units_sold=total_units,
        active_products_count=active_products,
        average_order_value=aov,
    )


@router.get("/products", response_model=List[VendorProductPerformance])
def get_vendor_products_performance(
    vendor_id: Optional[int] = Query(None, description="Vendor ID"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_admin_or_vendor),
):
    """Retrieve catalog performance and inventory levels for the vendor's products."""
    vendor = resolve_target_vendor(user, vendor_id)

    qualifying = [Order.Status.CONFIRMED, Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED]
    products = (
        Product.objects.filter(vendor=vendor)
        .select_related('inventory')
        .annotate(
            units_sold=Sum('order_items__quantity', filter=Q(order_items__order__status__in=qualifying)),
            total_rev=Sum('order_items__total_price', filter=Q(order_items__order__status__in=qualifying)),
        )
        .order_by('-total_rev')[offset : offset + limit]
    )

    results = []
    for p in products:
        results.append(
            VendorProductPerformance(
                product_id=p.id,
                name=p.name,
                sku=p.sku,
                price=float(p.price),
                units_sold=int(p.units_sold or 0),
                revenue=float(p.total_rev or 0.0),
                stock_quantity=p.inventory.quantity if hasattr(p, 'inventory') else 0,
                status=p.status,
            )
        )
    return results


@router.get("/inventory", response_model=VendorInventorySummary)
def get_vendor_inventory_summary(
    vendor_id: Optional[int] = Query(None, description="Vendor ID"),
    user: User = Depends(require_admin_or_vendor),
):
    """Retrieve aggregated stock levels, reserved units, and low-stock indicators for vendor products."""
    vendor = resolve_target_vendor(user, vendor_id)

    prods = Product.objects.filter(vendor=vendor).select_related('inventory')
    total_on_hand = sum(p.inventory.quantity for p in prods if hasattr(p, 'inventory'))
    low_stock = sum(1 for p in prods if hasattr(p, 'inventory') and 0 < p.inventory.quantity <= p.inventory.low_stock_threshold)
    out_of_stock = sum(1 for p in prods if hasattr(p, 'inventory') and p.inventory.quantity <= 0)

    # Calculate reserved stock from pending unfulfilled order items
    pending_items = OrderItem.objects.filter(
        vendor=vendor,
        order__status__in=[Order.Status.PENDING, Order.Status.CONFIRMED],
        status=OrderItem.Status.PENDING,
    ).aggregate(res=Sum('quantity'))
    reserved = int(pending_items['res'] or 0)
    available = max(0, total_on_hand - reserved)

    return VendorInventorySummary(
        total_stock_on_hand=total_on_hand,
        available_stock=available,
        reserved_stock=reserved,
        low_stock_items_count=low_stock,
        out_of_stock_items_count=out_of_stock,
    )
