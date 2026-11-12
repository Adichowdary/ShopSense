"""
Centralized authorization mixins for ShopSense Orders and Dashboard.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _


class AdminRequiredMixin(UserPassesTestMixin):
    """
    Mixin to enforce that the requesting user has administrative
    privileges and active staff status.
    """

    def test_func(self):
        user = self.request.user
        return bool(user.is_authenticated and user.can_access_admin_dashboard())

    def handle_no_permission(self):
        messages.error(self.request, _('You do not have permission to access the admin dashboard.'))
        return redirect('accounts:login')


class VendorRequiredMixin(UserPassesTestMixin):
    """
    Mixin to enforce that the requesting user is an active vendor
    with an active VendorProfile.
    """

    def test_func(self):
        user = self.request.user
        return bool(
            user.is_authenticated
            and user.can_access_vendor_dashboard()
            and hasattr(user, 'vendor_profile')
            and user.vendor_profile.is_active
        )

    def handle_no_permission(self):
        messages.error(self.request, _('You do not have permission to access the vendor portal.'))
        return redirect('accounts:login')
