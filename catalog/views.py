"""
Views for ShopSense Catalog app.
"""

import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
    View,
)

from vendors.models import VendorProfile
from .forms import (
    InventoryForm,
    ProductForm,
    ProductImageForm,
    validate_image_file,
)
from .models import Category, Inventory, Product, ProductImage

logger = logging.getLogger(__name__)


class ProductPermissionMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Mixin enforcing role-based permissions for products:
    - Admin users can manage all marketplace products.
    - Vendor users can only manage products belonging to their own vendor profile.
    - Customers and unauthenticated users are denied access.
    """

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.can_access_admin_dashboard():
            return True
        if user.is_vendor():
            return hasattr(user, 'vendor_profile') and user.vendor_profile.is_active
        return False

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(
            self.request,
            _('You do not have permission to access product management.')
        )
        return redirect('accounts:login')

    def get_queryset(self):
        user = self.request.user
        queryset = Product.objects.select_related(
            'vendor', 'category', 'inventory'
        ).prefetch_related('images')

        if user.can_access_admin_dashboard():
            return queryset
        elif user.is_vendor() and hasattr(user, 'vendor_profile'):
            return queryset.filter(vendor=user.vendor_profile)
        return Product.objects.none()


class ProductListView(ProductPermissionMixin, ListView):
    """List products with search, filter, stats, and role-based scoping."""

    model = Product
    template_name = 'dashboard/products/list.html'
    context_object_name = 'products'
    paginate_by = 15

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.GET

        # Search query
        search = params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(sku__icontains=search) |
                Q(description__icontains=search)
            )

        # Status filter
        status = params.get('status', '').strip()
        if status and status in Product.Status.values:
            queryset = queryset.filter(status=status)

        # Category filter
        category_id = params.get('category', '').strip()
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # Vendor filter (admin only)
        if self.request.user.can_access_admin_dashboard():
            vendor_id = params.get('vendor', '').strip()
            if vendor_id:
                queryset = queryset.filter(vendor_id=vendor_id)

        # Stock filter
        stock = params.get('stock', '').strip()
        if stock == 'in_stock':
            queryset = queryset.filter(inventory__quantity__gt=0)
        elif stock == 'low_stock':
            queryset = queryset.filter(
                inventory__quantity__gt=0,
                inventory__quantity__lte=models.F('inventory__low_stock_threshold')
            ) if hasattr(models, 'F') else queryset
        elif stock == 'out_of_stock':
            queryset = queryset.filter(inventory__quantity__lte=0)

        # Ordering
        order_by = params.get('ordering', '-created_at').strip()
        valid_orderings = {
            'name': 'name',
            '-name': '-name',
            'price': 'price',
            '-price': '-price',
            'created_at': 'created_at',
            '-created_at': '-created_at',
            'sku': 'sku',
            '-sku': '-sku',
        }
        queryset = queryset.order_by(valid_orderings.get(order_by, '-created_at'))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Base queryset for calculating aggregate stats
        base_qs = Product.objects.all()
        if not user.can_access_admin_dashboard() and user.is_vendor() and hasattr(user, 'vendor_profile'):
            base_qs = base_qs.filter(vendor=user.vendor_profile)

        # Aggregate counts
        stats = {
            'total': base_qs.count(),
            'active': base_qs.filter(status=Product.Status.ACTIVE).count(),
            'draft': base_qs.filter(status=Product.Status.DRAFT).count(),
            'inactive': base_qs.filter(status=Product.Status.INACTIVE).count(),
            'out_of_stock': base_qs.filter(
                Q(status=Product.Status.OUT_OF_STOCK) | Q(inventory__quantity__lte=0)
            ).count(),
        }

        context.update({
            'page_title': _('Product Management'),
            'stats': stats,
            'status_choices': Product.Status.choices,
            'categories': Category.objects.filter(is_active=True),
            'vendors': VendorProfile.objects.filter(is_active=True) if user.can_access_admin_dashboard() else None,
            'search_query': self.request.GET.get('search', ''),
            'current_status': self.request.GET.get('status', ''),
            'current_category': self.request.GET.get('category', ''),
            'current_vendor': self.request.GET.get('vendor', ''),
            'current_stock': self.request.GET.get('stock', ''),
            'current_ordering': self.request.GET.get('ordering', '-created_at'),
        })
        return context


class ProductDetailView(ProductPermissionMixin, DetailView):
    """View details of a single product."""

    model = Product
    template_name = 'dashboard/products/detail.html'
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        context['page_title'] = product.name
        context['primary_image'] = product.images.filter(is_primary=True).first() or product.images.first()
        context['gallery_images'] = product.images.all()
        context['has_inventory'] = hasattr(product, 'inventory')
        return context


class ProductCreateView(ProductPermissionMixin, CreateView):
    """Create a new product with inventory tracking and image uploads."""

    model = Product
    form_class = ProductForm
    template_name = 'dashboard/products/create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Add New Product')
        if 'inventory_form' not in context:
            if self.request.POST:
                context['inventory_form'] = InventoryForm(self.request.POST)
            else:
                context['inventory_form'] = InventoryForm(initial={'quantity': 0, 'low_stock_threshold': 10})
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        inventory_form = context['inventory_form']
        user = self.request.user

        if not inventory_form.is_valid():
            return self.form_invalid(form)

        # Validate vendor assignment
        if user.is_vendor() and hasattr(user, 'vendor_profile'):
            form.instance.vendor = user.vendor_profile
        elif user.can_access_admin_dashboard():
            selected_vendor = form.cleaned_data.get('vendor')
            if not selected_vendor:
                # If no vendor chosen, assign first available vendor or error
                first_vendor = VendorProfile.objects.first()
                if first_vendor:
                    form.instance.vendor = first_vendor
                else:
                    form.add_error('vendor', _('At least one vendor must exist to create a product.'))
                    return self.form_invalid(form)
            else:
                form.instance.vendor = selected_vendor

        try:
            with transaction.atomic():
                self.object = form.save()

                # Create or save inventory
                inventory = inventory_form.save(commit=False)
                inventory.product = self.object
                inventory.save()

                # Handle multiple image uploads if provided
                uploaded_images = self.request.FILES.getlist('images')
                # Also check single image field
                single_image = self.request.FILES.get('image')
                if single_image and single_image not in uploaded_images:
                    uploaded_images.append(single_image)

                for index, img_file in enumerate(uploaded_images):
                    try:
                        validate_image_file(img_file)
                        ProductImage.objects.create(
                            product=self.object,
                            image=img_file,
                            alt_text=f"{self.object.name} image {index + 1}",
                            is_primary=(index == 0),
                            sort_order=index,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to upload image {img_file.name}: {e}")
                        messages.warning(
                            self.request,
                            _('Failed to attach image %(name)s: %(error)s') % {
                                'name': img_file.name,
                                'error': str(e),
                            }
                        )

            logger.info(f"Product '{self.object.name}' (SKU: {self.object.sku}) created by {user.email}")
            messages.success(
                self.request,
                _('Product "%(name)s" created successfully.') % {'name': self.object.name}
            )
            return redirect('dashboard:product_detail', pk=self.object.pk)

        except Exception as e:
            logger.exception("Error creating product")
            messages.error(self.request, _('Error creating product: %(error)s') % {'error': str(e)})
            return self.form_invalid(form)


class ProductUpdateView(ProductPermissionMixin, UpdateView):
    """Update an existing product and its inventory."""

    model = Product
    form_class = ProductForm
    template_name = 'dashboard/products/edit.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Edit Product: %(name)s') % {'name': self.object.name}
        if 'inventory_form' not in context:
            inventory = getattr(self.object, 'inventory', None)
            if self.request.POST:
                context['inventory_form'] = InventoryForm(self.request.POST, instance=inventory)
            else:
                context['inventory_form'] = InventoryForm(instance=inventory)
        context['existing_images'] = self.object.images.all()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        inventory_form = context['inventory_form']

        if not inventory_form.is_valid():
            return self.form_invalid(form)

        try:
            with transaction.atomic():
                self.object = form.save()

                # Save inventory
                inventory = inventory_form.save(commit=False)
                inventory.product = self.object
                inventory.save()

                # Handle new image uploads
                uploaded_images = self.request.FILES.getlist('images')
                single_image = self.request.FILES.get('image')
                if single_image and single_image not in uploaded_images:
                    uploaded_images.append(single_image)

                existing_count = self.object.images.count()
                has_primary = self.object.images.filter(is_primary=True).exists()

                for index, img_file in enumerate(uploaded_images):
                    try:
                        validate_image_file(img_file)
                        ProductImage.objects.create(
                            product=self.object,
                            image=img_file,
                            alt_text=f"{self.object.name} image {existing_count + index + 1}",
                            is_primary=(not has_primary and index == 0),
                            sort_order=existing_count + index,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to upload image {img_file.name}: {e}")
                        messages.warning(
                            self.request,
                            _('Failed to attach image %(name)s: %(error)s') % {
                                'name': img_file.name,
                                'error': str(e),
                            }
                        )

            logger.info(f"Product '{self.object.name}' (SKU: {self.object.sku}) updated by {self.request.user.email}")
            messages.success(
                self.request,
                _('Product "%(name)s" updated successfully.') % {'name': self.object.name}
            )
            return redirect('dashboard:product_detail', pk=self.object.pk)

        except Exception as e:
            logger.exception("Error updating product")
            messages.error(self.request, _('Error updating product: %(error)s') % {'error': str(e)})
            return self.form_invalid(form)


class ProductDeleteView(ProductPermissionMixin, DeleteView):
    """Delete a product after confirmation."""

    model = Product
    template_name = 'dashboard/products/delete.html'
    context_object_name = 'product'
    success_url = reverse_lazy('dashboard:product_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Delete Product: %(name)s') % {'name': self.object.name}
        return context

    def form_valid(self, form):
        product_name = self.object.name
        response = super().form_valid(form)
        logger.info(f"Product '{product_name}' deleted by {self.request.user.email}")
        messages.success(
            self.request,
            _('Product "%(name)s" has been successfully deleted.') % {'name': product_name}
        )
        return response


class ProductImageDeleteView(ProductPermissionMixin, View):
    """Delete an individual product image."""

    def post(self, request, pk, image_pk):
        product = get_object_or_404(self.get_queryset(), pk=pk)
        image = get_object_or_404(product.images.all(), pk=image_pk)
        image.delete()
        messages.success(request, _('Product image removed.'))
        return redirect('dashboard:product_edit', pk=product.pk)