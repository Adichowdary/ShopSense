"""
Views for ShopSense Vendors app.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from .forms import AdminVendorActionForm, VendorApplicationForm, VendorProfileForm
from .models import AuditLog, VendorApplication, VendorProfile

logger = logging.getLogger(__name__)


class VendorOnboardingView(CreateView):
    """Public vendor onboarding/application view."""

    model = VendorApplication
    form_class = VendorApplicationForm
    template_name = 'vendors/onboarding.html'
    success_url = reverse_lazy('vendors:application_submitted')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Become a Vendor')
        context['steps'] = [
            {'number': 1, 'title': _('Business Info'), 'active': True},
            {'number': 2, 'title': _('Contact Details'), 'active': False},
            {'number': 3, 'title': _('Review & Submit'), 'active': False},
        ]
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        logger.info(f'New vendor application submitted: {self.object.business_name} ({self.object.vendor_id})')
        messages.success(
            self.request,
            _('Your application has been submitted successfully! '
              'Your vendor ID is %(vendor_id)s. We will review your application and contact you at %(email)s.') %
            {'vendor_id': self.object.vendor_id, 'email': self.object.contact_email}
        )
        # Store application ID in session for success page
        self.request.session['vendor_application_id'] = self.object.pk
        return response


class ApplicationSubmittedView(TemplateView):
    """View shown after successful vendor application submission."""

    template_name = 'vendors/application_submitted.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Application Submitted')

        # Get the latest application for this session/user
        application_id = self.request.session.get('vendor_application_id')
        if application_id:
            try:
                from .models import VendorApplication
                application = VendorApplication.objects.get(pk=application_id)
                context.update({
                    'vendor_id': application.vendor_id,
                    'business_name': application.business_name,
                    'contact_email': application.contact_email,
                    'submitted_at': application.submitted_at,
                })
            except VendorApplication.DoesNotExist:
                pass

        return context


class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin enforcing administrator access."""

    def test_func(self):
        return bool(
            self.request.user.is_authenticated
            and hasattr(self.request.user, 'can_access_admin_dashboard')
            and self.request.user.can_access_admin_dashboard()
        )

    def handle_no_permission(self):
        messages.error(self.request, _('You do not have permission to access the admin dashboard.'))
        return redirect('accounts:login')


class VendorApplicationListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """Admin view for listing vendor applications."""

    model = VendorApplication
    template_name = 'dashboard/vendors/applications.html'
    context_object_name = 'applications'
    paginate_by = 20

    def test_func(self):
        return self.request.user.can_access_admin_dashboard()

    def get_queryset(self):
        queryset = super().get_queryset().select_related('reviewed_by')
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(business_name__icontains=search) |
                Q(contact_email__icontains=search) |
                Q(vendor_id__icontains=search)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Vendor Applications')
        context['status_choices'] = VendorApplication.Status.choices
        context['current_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('search', '')
        # Statistics
        context['stats'] = {
            'total': VendorApplication.objects.count(),
            'pending': VendorApplication.objects.filter(status=VendorApplication.Status.PENDING).count(),
            'approved': VendorApplication.objects.filter(status=VendorApplication.Status.APPROVED).count(),
            'rejected': VendorApplication.objects.filter(status=VendorApplication.Status.REJECTED).count(),
            'more_info': VendorApplication.objects.filter(status=VendorApplication.Status.MORE_INFO).count(),
        }
        return context


class VendorApplicationDetailView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    """Admin view for vendor application details."""

    model = VendorApplication
    template_name = 'dashboard/vendors/application_detail.html'
    context_object_name = 'application'
    pk_url_kwarg = 'pk'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Application Details')
        context['action_form'] = AdminVendorActionForm()
        return context


class VendorApplicationActionView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Handle admin actions on vendor applications."""

    def post(self, request, pk):
        application = get_object_or_404(VendorApplication, pk=pk)
        form = AdminVendorActionForm(request.POST)

        if form.is_valid():
            action = form.cleaned_data['action']
            notes = form.cleaned_data['notes']

            if action == 'approve':
                application.approve(request.user, notes)
                # Get the created vendor profile for audit log
                vendor_profile = VendorProfile.objects.get(vendor_id=application.vendor_id)
                AuditLog.objects.create(
                    user=request.user,
                    action=AuditLog.ActionType.VENDOR_APPROVED,
                    target_user=application.applicant_user,
                    target_vendor=vendor_profile,
                    details={'vendor_id': application.vendor_id, 'business_name': application.business_name},
                    ip_address=self.get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                )
                messages.success(request, _('Vendor application approved successfully.'))

            elif action == 'reject':
                application.reject(request.user, notes)
                AuditLog.objects.create(
                    user=request.user,
                    action=AuditLog.ActionType.VENDOR_REJECTED,
                    target_user=application.applicant_user,
                    details={'vendor_id': application.vendor_id, 'business_name': application.business_name, 'reason': notes},
                    ip_address=self.get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                )
                messages.success(request, _('Vendor application rejected.'))

            elif action == 'more_info':
                application.request_more_info(request.user, notes)
                messages.success(request, _('More information requested from vendor.'))

            logger.info(f'Admin {request.user.email} {action}d vendor application {application.vendor_id}')

        return redirect('dashboard:vendor_application_detail', pk=pk)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')


class VendorListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """Admin view for listing approved vendors."""

    model = VendorProfile
    template_name = 'dashboard/vendors/list.html'
    context_object_name = 'vendors'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset().select_related('user')
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(business_name__icontains=search) |
                Q(contact_email__icontains=search) |
                Q(vendor_id__icontains=search)
            )
        status = self.request.GET.get('status')
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Vendors')
        context['search_query'] = self.request.GET.get('search', '')
        context['current_status'] = self.request.GET.get('status', '')
        return context


class VendorDetailView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    """Admin view for vendor details."""

    model = VendorProfile
    template_name = 'dashboard/vendors/detail.html'
    context_object_name = 'vendor'
    pk_url_kwarg = 'pk'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Vendor Details')
        # Get audit logs for this vendor
        context['audit_logs'] = AuditLog.objects.filter(
            target_vendor=self.object
        ).select_related('user')[:20]
        return context


class VendorUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Vendor self-service profile update."""

    model = VendorProfile
    form_class = VendorProfileForm
    template_name = 'vendors/profile_edit.html'

    def get_object(self, queryset=None):
        if hasattr(self.request.user, 'vendor_profile'):
            return self.request.user.vendor_profile
        return None

    def test_func(self):
        return bool(
            self.request.user.is_authenticated
            and self.request.user.is_vendor()
            and hasattr(self.request.user, 'vendor_profile')
        )

    def handle_no_permission(self):
        messages.error(self.request, _('You do not have permission to edit this vendor profile.'))
        return redirect('accounts:login')

    def get_success_url(self):
        return reverse('vendors:profile')

    def form_valid(self, form):
        messages.success(self.request, _('Your profile has been updated successfully.'))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Edit Vendor Profile')
        return context


class VendorProfileView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Vendor self-service profile view."""

    model = VendorProfile
    template_name = 'vendors/profile.html'
    context_object_name = 'vendor'

    def test_func(self):
        return bool(
            self.request.user.is_authenticated
            and self.request.user.is_vendor()
            and hasattr(self.request.user, 'vendor_profile')
        )

    def handle_no_permission(self):
        messages.error(self.request, _('You do not have permission to access the vendor portal.'))
        return redirect('accounts:login')

    def get_object(self):
        return self.request.user.vendor_profile

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('My Vendor Profile')
        return context