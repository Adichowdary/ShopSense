"""
Views for ShopSense Accounts app.
"""

import logging

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeDoneView,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, UpdateView

from .forms import (
    CustomPasswordChangeForm,
    CustomPasswordResetForm,
    CustomSetPasswordForm,
    LoginForm,
    ProfileUpdateForm,
    RegistrationForm,
)
from .models import User

logger = logging.getLogger(__name__)


class CustomLoginView(LoginView):
    """Custom login view with enhanced security."""

    form_class = LoginForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        """Redirect users to their respective portal based on role."""
        redirect_to = self.get_redirect_url()
        user = self.request.user

        # Prevent redirect loops: if next points to a restricted dashboard the user cannot access
        if redirect_to and '/dashboard/' in redirect_to:
            if not (user.is_authenticated and hasattr(user, 'can_access_admin_dashboard') and user.can_access_admin_dashboard()):
                redirect_to = None

        if redirect_to and ('/vendors/profile' in redirect_to or '/vendors/orders' in redirect_to):
            if not (user.is_authenticated and hasattr(user, 'can_access_vendor_dashboard') and user.can_access_vendor_dashboard()):
                redirect_to = None

        if redirect_to:
            return redirect_to

        if user.is_authenticated:
            if hasattr(user, 'can_access_admin_dashboard') and user.can_access_admin_dashboard():
                return reverse_lazy('dashboard:admin_dashboard')
            elif hasattr(user, 'is_vendor') and user.is_vendor():
                return reverse_lazy('vendors:profile')
            else:
                return reverse_lazy('store:home')
        return reverse_lazy('store:home')

    def dispatch(self, request, *args, **kwargs):
        if self.redirect_authenticated_user and self.request.user.is_authenticated:
            # Safely redirect authenticated users to their portal to avoid loops
            return HttpResponseRedirect(str(self.get_success_url()))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """Log the user in and reset failed attempts."""
        user = form.get_user()
        user.reset_failed_login()
        login(self.request, user)
        logger.info(f'User {user.email} logged in successfully from IP {self.get_client_ip()}')
        messages.success(self.request, _('Welcome back, %(name)s!') % {'name': user.get_short_name()})
        return super().form_valid(form)

    def form_invalid(self, form):
        """Handle invalid login attempts."""
        email = form.data.get('username', '').lower()
        try:
            user = User.objects.get(email=email)
            user.increment_failed_login()
            logger.warning(f'Failed login attempt for {email} from IP {self.get_client_ip()}')
        except User.DoesNotExist:
            logger.warning(f'Failed login attempt for non-existent email {email} from IP {self.get_client_ip()}')
        return super().form_invalid(form)

    def get_client_ip(self):
        """Get client IP address."""
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return self.request.META.get('REMOTE_ADDR', '')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Sign In')
        return context


class CustomLogoutView(LogoutView):
    """Custom logout view."""

    http_method_names = ['get', 'post', 'options']

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            logger.info(f'User {request.user.email} logged out')
            messages.info(request, _('You have been logged out successfully.'))
        logout(request)
        return redirect('accounts:login')


class RegistrationView(TemplateView):
    """User registration view."""

    template_name = 'accounts/register.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard:admin_dashboard')
        form = RegistrationForm()
        return render(request, self.template_name, {'form': form, 'page_title': _('Create Account')})

    def post(self, request, *args, **kwargs):
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            logger.info(f'New user registered: {user.email} with role {user.role}')
            messages.success(
                request,
                _('Your account has been created successfully! Please sign in.')
            )
            return redirect('accounts:login')
        return render(request, self.template_name, {'form': form, 'page_title': _('Create Account')})


class CustomPasswordResetView(PasswordResetView):
    """Custom password reset view."""

    form_class = CustomPasswordResetForm
    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.html'
    subject_template_name = 'registration/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Reset Password')
        return context


class CustomPasswordResetDoneView(PasswordResetDoneView):
    """Password reset done view."""

    template_name = 'registration/password_reset_done.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Check Your Email')
        return context


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    """Password reset confirm view."""

    form_class = CustomSetPasswordForm
    template_name = 'registration/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:password_reset_complete')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Set New Password')
        return context


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    """Password reset complete view."""

    template_name = 'registration/password_reset_complete.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Password Reset Complete')
        return context


class CustomPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """Custom password change view."""

    form_class = CustomPasswordChangeForm
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('accounts:password_change_done')

    def get_template_names(self):
        if hasattr(self.request.user, 'role') and self.request.user.role == 'ADMIN':
            return ['accounts/password_change_admin.html']
        return ['accounts/password_change.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Change Password')
        return context

    def form_valid(self, form):
        messages.success(self.request, _('Your password has been changed successfully.'))
        return super().form_valid(form)


class CustomPasswordChangeDoneView(LoginRequiredMixin, PasswordChangeDoneView):
    """Password change done view."""

    template_name = 'accounts/password_change_done.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Password Changed')
        return context


class ProfileView(LoginRequiredMixin, TemplateView):
    """User profile and customer account dashboard view."""

    template_name = 'accounts/profile.html'

    def get_template_names(self):
        if hasattr(self.request.user, 'role') and self.request.user.role == 'ADMIN':
            return ['accounts/profile_admin.html']
        return ['accounts/profile.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('My Profile')
        context['user'] = self.request.user
        
        # Populate customer account details safely
        user = self.request.user
        if hasattr(user, 'orders'):
            context['recent_orders'] = user.orders.all().order_by('-created_at')[:5]
            context['total_orders_count'] = user.orders.count()
        else:
            context['recent_orders'] = []
            context['total_orders_count'] = 0

        if hasattr(user, 'addresses'):
            context['saved_addresses'] = user.addresses.all()
        else:
            context['saved_addresses'] = []

        if hasattr(user, 'cart'):
            context['cart_items_count'] = user.cart.total_items
        else:
            context['cart_items_count'] = 0

        return context


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Update user profile."""

    form_class = ProfileUpdateForm
    template_name = 'accounts/profile_edit.html'
    success_url = reverse_lazy('accounts:profile')

    def get_template_names(self):
        if hasattr(self.request.user, 'role') and self.request.user.role == 'ADMIN':
            return ['accounts/profile_edit_admin.html']
        return ['accounts/profile_edit.html']

    def get_object(self):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Edit Profile')
        return context

    def form_valid(self, form):
        messages.success(self.request, _('Your profile has been updated successfully.'))
        return super().form_valid(form)