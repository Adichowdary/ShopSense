"""
Tests for ShopSense Catalog Product Management (Phase 2).
"""

from decimal import Decimal
import io
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from accounts.models import User
from catalog.forms import (
    InventoryForm,
    ProductForm,
    validate_image_file,
)
from catalog.models import Category, Inventory, Product, ProductImage
from vendors.models import VendorProfile


def create_dummy_image(filename="test.png", format="PNG", size=(100, 100), color="blue"):
    """Create an in-memory image for upload testing."""
    file = io.BytesIO()
    image = Image.new("RGB", size, color=color)
    image.save(file, format=format)
    file.seek(0)
    return SimpleUploadedFile(
        filename,
        file.read(),
        content_type=f"image/{format.lower()}",
    )


@pytest.fixture
def vendor_profile(vendor_user):
    """Create an active VendorProfile for vendor_user."""
    profile, _ = VendorProfile.objects.get_or_create(
        user=vendor_user,
        defaults={
            'vendor_id': 'VND12345678',
            'business_name': 'Tech World Gadgets',
            'contact_email': vendor_user.email,
            'is_active': True,
            'is_verified': True,
        }
    )
    return profile


@pytest.fixture
def second_vendor_user():
    """Create a second vendor user."""
    user = User.objects.create_user(
        email='vendor2@example.com',
        password='TestPass123!',
        role=User.Role.VENDOR,
        is_active=True,
    )
    return user


@pytest.fixture
def second_vendor_profile(second_vendor_user):
    """Create VendorProfile for second vendor user."""
    profile, _ = VendorProfile.objects.get_or_create(
        user=second_vendor_user,
        defaults={
            'vendor_id': 'VND87654321',
            'business_name': 'Style Apparel Co',
            'contact_email': second_vendor_user.email,
            'is_active': True,
            'is_verified': True,
        }
    )
    return profile


@pytest.fixture
def category():
    """Create a test product category."""
    cat, _ = Category.objects.get_or_create(
        slug='electronics',
        defaults={'name': 'Electronics', 'is_active': True}
    )
    return cat


@pytest.fixture
def product(vendor_profile, category):
    """Create a test product with inventory."""
    prod = Product.objects.create(
        vendor=vendor_profile,
        category=category,
        name='Wireless Headphones Pro',
        slug='wireless-headphones-pro',
        sku='WHP-001',
        description='High quality wireless headphones with active noise cancellation.',
        price=Decimal('199.99'),
        compare_at_price=Decimal('249.99'),
        status=Product.Status.ACTIVE,
    )
    Inventory.objects.create(
        product=prod,
        quantity=50,
        low_stock_threshold=10,
        track_quantity=True,
    )
    return prod


@pytest.mark.django_db
class TestProductModels:
    """Tests for Product, Category, Inventory, and ProductImage models."""

    def test_create_category(self):
        cat = Category.objects.create(name='Home & Kitchen', slug='home-kitchen')
        assert str(cat) == 'Home & Kitchen'
        assert cat.is_active is True

    def test_create_product_with_inventory(self, vendor_profile, category):
        prod = Product.objects.create(
            vendor=vendor_profile,
            category=category,
            name='Ergonomic Desk Chair',
            slug='ergonomic-desk-chair',
            sku='EDC-100',
            description='Ergonomic mesh office chair with lumbar support.',
            price=Decimal('299.00'),
            compare_at_price=Decimal('349.00'),
            cost_price=Decimal('150.00'),
            status=Product.Status.ACTIVE,
        )
        inv = Inventory.objects.create(
            product=prod,
            quantity=25,
            reserved_quantity=5,
            low_stock_threshold=10,
        )
        assert str(prod) == 'Ergonomic Desk Chair'
        assert prod.vendor == vendor_profile
        assert prod.category == category
        assert inv.available_quantity == 20
        assert inv.is_low_stock is False
        assert inv.is_out_of_stock is False

    def test_inventory_stock_properties(self, product):
        inv = product.inventory
        inv.quantity = 8
        inv.reserved_quantity = 0
        inv.low_stock_threshold = 10
        inv.save()
        assert inv.is_low_stock is True
        assert inv.is_out_of_stock is False

        inv.quantity = 0
        inv.save()
        assert inv.is_out_of_stock is True

    def test_product_image_model(self, product):
        uploaded = create_dummy_image("headphone.jpg", "JPEG")
        img = ProductImage.objects.create(
            product=product,
            image=uploaded,
            alt_text='Headphone photo',
            is_primary=True,
            sort_order=1,
        )
        assert 'Image 1' in str(img)
        assert img.product == product
        assert img.is_primary is True


@pytest.mark.django_db
class TestProductForms:
    """Tests for form validations."""

    def test_product_form_valid(self, vendor_profile, category):
        form_data = {
            'vendor': vendor_profile.pk,
            'category': category.pk,
            'name': 'Mechanical Keyboard',
            'sku': 'MK-87',
            'description': 'Custom mechanical keyboard with hot-swappable switches.',
            'price': '129.99',
            'compare_at_price': '159.99',
            'cost_price': '70.00',
            'status': Product.Status.ACTIVE,
        }
        form = ProductForm(data=form_data)
        assert form.is_valid(), form.errors
        assert form.cleaned_data['slug'] == 'mechanical-keyboard'

    def test_product_form_invalid_price_zero(self, vendor_profile, category):
        form_data = {
            'vendor': vendor_profile.pk,
            'category': category.pk,
            'name': 'Free Item',
            'sku': 'FREE-001',
            'description': 'Description',
            'price': '0.00',
            'status': Product.Status.ACTIVE,
        }
        form = ProductForm(data=form_data)
        assert not form.is_valid()
        assert 'price' in form.errors

    def test_product_form_invalid_price_negative(self, vendor_profile, category):
        form_data = {
            'vendor': vendor_profile.pk,
            'category': category.pk,
            'name': 'Negative Item',
            'sku': 'NEG-001',
            'description': 'Description',
            'price': '-19.99',
            'status': Product.Status.ACTIVE,
        }
        form = ProductForm(data=form_data)
        assert not form.is_valid()
        assert 'price' in form.errors

    def test_product_form_compare_at_price_less_than_price(self, vendor_profile, category):
        form_data = {
            'vendor': vendor_profile.pk,
            'category': category.pk,
            'name': 'Faulty Discount',
            'sku': 'FAULTY-001',
            'description': 'Description',
            'price': '100.00',
            'compare_at_price': '80.00',  # compare price must be greater than current price
            'status': Product.Status.ACTIVE,
        }
        form = ProductForm(data=form_data)
        assert not form.is_valid()
        assert 'compare_at_price' in form.errors

    def test_product_form_negative_cost_price(self, vendor_profile, category):
        form_data = {
            'vendor': vendor_profile.pk,
            'category': category.pk,
            'name': 'Bad Cost',
            'sku': 'COST-001',
            'description': 'Description',
            'price': '100.00',
            'cost_price': '-10.00',
            'status': Product.Status.ACTIVE,
        }
        form = ProductForm(data=form_data)
        assert not form.is_valid()
        assert 'cost_price' in form.errors

    def test_inventory_form_validation(self):
        # Valid
        form = InventoryForm(data={'quantity': 50, 'low_stock_threshold': 5})
        assert form.is_valid()

        # Negative stock
        form_invalid = InventoryForm(data={'quantity': -5, 'low_stock_threshold': 5})
        assert not form_invalid.is_valid()
        assert 'quantity' in form_invalid.errors

    def test_image_file_validations(self):
        valid_img = create_dummy_image("valid.png", "PNG")
        validate_image_file(valid_img)  # Should not raise

        # Invalid format
        invalid_file = SimpleUploadedFile("bad.txt", b"plain text", content_type="text/plain")
        with pytest.raises(Exception):
            validate_image_file(invalid_file)

        # Oversized file > 5MB
        oversized = SimpleUploadedFile("big.png", b"x" * (6 * 1024 * 1024), content_type="image/png")
        with pytest.raises(Exception):
            validate_image_file(oversized)


@pytest.mark.django_db
class TestProductPermissionsAndScoping:
    """Tests for role-based permissions and access control."""

    def test_unauthenticated_user_redirected_to_login(self, client):
        url = reverse('dashboard:product_list')
        response = client.get(url)
        assert response.status_code == 302
        assert reverse('accounts:login') in response.url

    def test_customer_user_access_denied(self, customer_client):
        url = reverse('dashboard:product_list')
        response = customer_client.get(url)
        assert response.status_code == 302
        assert reverse('accounts:login') in response.url

    def test_vendor_without_profile_cannot_access(self, vendor_client):
        # vendor_user does not have a vendor_profile created yet
        url = reverse('dashboard:product_list')
        response = vendor_client.get(url)
        assert response.status_code == 302

    def test_vendor_with_active_profile_can_access(self, client, vendor_user, vendor_profile):
        client.force_login(vendor_user)
        url = reverse('dashboard:product_list')
        response = client.get(url)
        assert response.status_code == 200

    def test_admin_can_access_product_list(self, authenticated_client):
        url = reverse('dashboard:product_list')
        response = authenticated_client.get(url)
        assert response.status_code == 200

    def test_vendor_sees_only_own_products(
        self, client, vendor_user, vendor_profile, second_vendor_profile, category
    ):
        # Create product for vendor 1
        p1 = Product.objects.create(
            vendor=vendor_profile,
            category=category,
            name='Vendor 1 Product',
            sku='V1-PROD',
            description='Desc 1',
            price=Decimal('10.00'),
        )
        # Create product for vendor 2
        p2 = Product.objects.create(
            vendor=second_vendor_profile,
            category=category,
            name='Vendor 2 Secret Item',
            sku='V2-PROD',
            description='Desc 2',
            price=Decimal('20.00'),
        )

        client.force_login(vendor_user)
        response = client.get(reverse('dashboard:product_list'))
        assert response.status_code == 200
        products_in_view = list(response.context['products'])
        assert p1 in products_in_view
        assert p2 not in products_in_view


@pytest.mark.django_db
class TestProductCRUDOperations:
    """Tests for Create, Read, Update, and Delete views."""

    def test_admin_creates_product_with_inventory(self, authenticated_client, vendor_profile, category):
        url = reverse('dashboard:product_create')
        data = {
            'vendor': vendor_profile.pk,
            'category': category.pk,
            'name': 'Smart Watch Series 7',
            'sku': 'SW-7-001',
            'description': 'Advanced smartwatch with fitness tracking.',
            'price': '349.99',
            'compare_at_price': '399.99',
            'status': Product.Status.ACTIVE,
            'quantity': 100,
            'low_stock_threshold': 15,
            'track_quantity': True,
        }
        response = authenticated_client.post(url, data)
        assert response.status_code == 302
        created = Product.objects.get(sku='SW-7-001')
        assert created.name == 'Smart Watch Series 7'
        assert created.vendor == vendor_profile
        assert hasattr(created, 'inventory')
        assert created.inventory.quantity == 100

    def test_vendor_creates_product_auto_assigns_vendor(
        self, client, vendor_user, vendor_profile, second_vendor_profile, category
    ):
        client.force_login(vendor_user)
        url = reverse('dashboard:product_create')
        data = {
            'vendor': second_vendor_profile.pk,  # Malicious attempt to assign to another vendor
            'category': category.pk,
            'name': 'Wireless Charging Pad',
            'sku': 'WCP-202',
            'description': '15W fast wireless charger.',
            'price': '29.99',
            'status': Product.Status.ACTIVE,
            'quantity': 40,
            'low_stock_threshold': 5,
        }
        response = client.post(url, data)
        assert response.status_code == 302
        created = Product.objects.get(sku='WCP-202')
        # Enforced: must belong to the logged-in vendor, ignoring form manipulation
        assert created.vendor == vendor_profile

    def test_product_detail_view(self, authenticated_client, product):
        url = reverse('dashboard:product_detail', kwargs={'pk': product.pk})
        response = authenticated_client.get(url)
        assert response.status_code == 200
        assert response.context['product'] == product

    def test_vendor_cannot_view_other_vendor_product_detail(
        self, client, second_vendor_user, second_vendor_profile, product
    ):
        # Product belongs to vendor_profile, logging in as second_vendor_user
        client.force_login(second_vendor_user)
        url = reverse('dashboard:product_detail', kwargs={'pk': product.pk})
        response = client.get(url)
        # Should return 404 because get_queryset filters by vendor
        assert response.status_code == 404

    def test_product_update_view(self, authenticated_client, product):
        url = reverse('dashboard:product_edit', kwargs={'pk': product.pk})
        data = {
            'vendor': product.vendor.pk,
            'category': product.category.pk,
            'name': 'Wireless Headphones Pro 2',
            'sku': product.sku,
            'description': 'Updated noise cancellation algorithms.',
            'price': '219.99',
            'status': Product.Status.ACTIVE,
            'quantity': 75,
            'low_stock_threshold': 12,
        }
        response = authenticated_client.post(url, data)
        assert response.status_code == 302
        product.refresh_from_db()
        assert product.name == 'Wireless Headphones Pro 2'
        assert product.price == Decimal('219.99')
        assert product.inventory.quantity == 75

    def test_vendor_cannot_update_other_vendor_product(
        self, client, second_vendor_user, second_vendor_profile, product
    ):
        client.force_login(second_vendor_user)
        url = reverse('dashboard:product_edit', kwargs={'pk': product.pk})
        response = client.get(url)
        assert response.status_code == 404

    def test_product_delete_view(self, authenticated_client, product):
        url = reverse('dashboard:product_delete', kwargs={'pk': product.pk})
        # GET shows confirmation page
        get_res = authenticated_client.get(url)
        assert get_res.status_code == 200
        assert product.name in get_res.content.decode()

        # POST confirms deletion
        post_res = authenticated_client.post(url)
        assert post_res.status_code == 302
        assert not Product.objects.filter(pk=product.pk).exists()

    def test_vendor_cannot_delete_other_vendor_product(
        self, client, second_vendor_user, second_vendor_profile, product
    ):
        client.force_login(second_vendor_user)
        url = reverse('dashboard:product_delete', kwargs={'pk': product.pk})
        response = client.post(url)
        assert response.status_code == 404
        assert Product.objects.filter(pk=product.pk).exists()

    def test_product_image_delete_view(self, authenticated_client, product):
        img_file = create_dummy_image("delete_me.png", "PNG")
        image = ProductImage.objects.create(product=product, image=img_file)
        url = reverse('dashboard:product_image_delete', kwargs={'pk': product.pk, 'image_pk': image.pk})
        response = authenticated_client.post(url)
        assert response.status_code == 302
        assert not ProductImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
class TestProductListAndSearchFilters:
    """Tests for searching, filtering, and empty states."""

    def test_empty_state_rendered_when_no_products(self, authenticated_client):
        Product.objects.all().delete()
        response = authenticated_client.get(reverse('dashboard:product_list'))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'No Products Found' in content
        assert 'Your product catalog is currently empty' in content

    def test_search_by_name_and_sku(self, authenticated_client, product):
        url = reverse('dashboard:product_list')
        # Search by name match
        res1 = authenticated_client.get(f"{url}?search=Wireless")
        assert len(res1.context['products']) == 1

        # Search by SKU match
        res2 = authenticated_client.get(f"{url}?search=WHP-001")
        assert len(res2.context['products']) == 1

        # Non-matching search
        res3 = authenticated_client.get(f"{url}?search=NonExistentGadget")
        assert len(res3.context['products']) == 0

    def test_filter_by_status(self, authenticated_client, product, vendor_profile, category):
        # Create a draft product
        Product.objects.create(
            vendor=vendor_profile,
            category=category,
            name='Draft Prototype',
            sku='DRAFT-001',
            description='Draft item',
            price=Decimal('50.00'),
            status=Product.Status.DRAFT,
        )
        url = reverse('dashboard:product_list')
        active_res = authenticated_client.get(f"{url}?status=ACTIVE")
        assert all(p.status == Product.Status.ACTIVE for p in active_res.context['products'])

        draft_res = authenticated_client.get(f"{url}?status=DRAFT")
        assert all(p.status == Product.Status.DRAFT for p in draft_res.context['products'])

    def test_dashboard_views_product_stats(self, authenticated_client, product):
        url = reverse('dashboard:admin_dashboard')
        response = authenticated_client.get(url)
        assert response.status_code == 200
        stats = response.context['product_stats']
        assert stats['total'] >= 1
        assert stats['active'] >= 1
