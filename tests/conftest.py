"""
Pytest configuration and fixtures for ShopSense tests.
"""

import os

import django

# Configure Django settings before importing any Django modules
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Setup Django
django.setup()

# Workaround for Django 5.2 + Python 3.14 test client bug:
# Disable template_rendered signal to avoid copy(context) failure in
# django.test.client.store_rendered_templates (Context.dicts attribute issue)
import django.test.signals

django.test.signals.template_rendered.receivers = []

import factory
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice

User = get_user_model()


class UserFactory(DjangoModelFactory):
    """Factory for creating test users."""
    
    class Meta:
        model = User
        django_get_or_create = ('email',)
    
    email = factory.Sequence(lambda n: f'user{n}@example.com')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    role = FuzzyChoice([User.Role.ADMIN, User.Role.VENDOR, User.Role.CUSTOMER])
    is_active = True
    is_staff = False
    
    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        if create:
            self.set_password(extracted or 'TestPass123!')
            self.save()


class AdminUserFactory(UserFactory):
    """Factory for creating admin users."""
    role = User.Role.ADMIN
    is_staff = True
    is_superuser = True


class VendorUserFactory(UserFactory):
    """Factory for creating vendor users."""
    role = User.Role.VENDOR


class CustomerUserFactory(UserFactory):
    """Factory for creating customer users."""
    role = User.Role.CUSTOMER


@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def admin_user():
    """Create an admin user."""
    return AdminUserFactory()


@pytest.fixture
def vendor_user():
    """Create a vendor user."""
    return VendorUserFactory()


@pytest.fixture
def customer_user():
    """Create a customer user."""
    return CustomerUserFactory()


@pytest.fixture
def authenticated_client(client, admin_user):
    """Client authenticated as admin."""
    client.force_login(admin_user)
    return client


@pytest.fixture
def vendor_client(client, vendor_user):
    """Client authenticated as vendor."""
    client.force_login(vendor_user)
    return client


@pytest.fixture
def customer_client(client, customer_user):
    """Client authenticated as customer."""
    client.force_login(customer_user)
    return client