"""
Views for ShopSense Dashboard app.
"""

import logging
from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from accounts.models import User
from catalog.models import Category, Product
from orders.models import Order, OrderItem, Payment
from vendors.models import AuditLog, VendorApplication, VendorProfile

logger = logging.getLogger(__name__)


class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin to require admin access."""

    def test_func(self):
        return self.request.user.can_access_admin_dashboard()

    def handle_no_permission(self):
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.error(self.request, _('You do not have permission to access the admin dashboard.'))
        return redirect('accounts:login')


class AdminDashboardView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Main admin dashboard view."""

    template_name = 'dashboard/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Dashboard')

        # Date ranges
        now = timezone.now()
        last_30_days = now - timedelta(days=30)
        last_7_days = now - timedelta(days=7)

        # Vendor statistics
        vendor_stats = VendorApplication.objects.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status=VendorApplication.Status.PENDING)),
            approved=Count('id', filter=Q(status=VendorApplication.Status.APPROVED)),
            rejected=Count('id', filter=Q(status=VendorApplication.Status.REJECTED)),
        )

        # Active vendors
        active_vendors = VendorProfile.objects.filter(is_active=True).count()

        # Recent vendor applications (last 7 days)
        recent_applications = VendorApplication.objects.filter(
            submitted_at__gte=last_7_days
        ).select_related('reviewed_by').order_by('-submitted_at')[:10]

        # Pending approvals
        pending_approvals = VendorApplication.objects.filter(
            status=VendorApplication.Status.PENDING
        ).select_related('reviewed_by').order_by('submitted_at')[:10]

        # User statistics
        user_stats = User.objects.aggregate(
            total=Count('id'),
            admins=Count('id', filter=Q(role=User.Role.ADMIN)),
            vendors=Count('id', filter=Q(role=User.Role.VENDOR)),
            customers=Count('id', filter=Q(role=User.Role.CUSTOMER)),
            active=Count('id', filter=Q(is_active=True)),
        )

        # Recent users
        recent_users = User.objects.filter(
            date_joined__gte=last_7_days
        ).order_by('-date_joined')[:10]

        # Recent audit logs (admin activity)
        recent_activity = AuditLog.objects.select_related('user', 'target_user', 'target_vendor').order_by('-created_at')[:15]

        # Product statistics
        product_stats = {
            'total': Product.objects.count(),
            'active': Product.objects.filter(status=Product.Status.ACTIVE).count(),
            'out_of_stock': Product.objects.filter(
                Q(status=Product.Status.OUT_OF_STOCK) | Q(inventory__quantity__lte=0)
            ).count(),
        }
        order_aggregates = Order.objects.aggregate(
            total_orders=Count('id'),
            pending=Count('id', filter=Q(status=Order.Status.PENDING)),
            completed=Count('id', filter=Q(status=Order.Status.DELIVERED)),
            revenue=Sum('total', filter=~Q(status=Order.Status.CANCELLED)),
        )
        order_stats = {
            'total': order_aggregates['total_orders'] or 0,
            'pending': order_aggregates['pending'] or 0,
            'completed': order_aggregates['completed'] or 0,
            'revenue': order_aggregates['revenue'] or 0,
        }
        recent_orders = Order.objects.select_related('user').order_by('-created_at')[:8]

        context.update({
            'vendor_stats': vendor_stats,
            'active_vendors': active_vendors,
            'recent_applications': recent_applications,
            'pending_approvals': pending_approvals,
            'user_stats': user_stats,
            'recent_users': recent_users,
            'recent_activity': recent_activity,
            'product_stats': product_stats,
            'order_stats': order_stats,
            'recent_orders': recent_orders,
            'last_30_days': last_30_days,
            'last_7_days': last_7_days,
        })
        return context


class AdminSettingsView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Admin settings view."""

    template_name = 'dashboard/settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Settings')
        return context


class AdminReportsView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Admin reports view."""

    template_name = 'dashboard/reports.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Reports')
        return context