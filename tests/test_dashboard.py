"""
Dashboard tests for ShopSense.
"""

import pytest
from django.urls import reverse

from accounts.models import User
from vendors.models import VendorApplication, VendorProfile

User = User


@pytest.mark.django_db
class TestAdminDashboard:
    """Tests for admin dashboard view."""
    
    def test_dashboard_accessible(self, authenticated_client):
        """Test admin dashboard is accessible."""
        response = authenticated_client.get(reverse('dashboard:admin_dashboard'))
        assert response.status_code == 200
        assert 'Dashboard' in response.content.decode()
    
    def test_dashboard_shows_stats(self, authenticated_client):
        """Test dashboard shows statistics."""
        # Create test data
        VendorApplication.objects.create(
            business_name='Business 1',
            contact_email='biz1@test.com',
            status=VendorApplication.Status.PENDING,
        )
        VendorApplication.objects.create(
            business_name='Business 2',
            contact_email='biz2@test.com',
            status=VendorApplication.Status.APPROVED,
        )
        VendorProfile.objects.create(
            user=User.objects.create_user(
                email='vendor@test.com',
                password='VendorPass123!',
                first_name='Vendor',
                last_name='User',
                role=User.Role.VENDOR,
            ),
            vendor_id='VND12345678',
            business_name='Approved Vendor',
            contact_email='vendor@test.com',
            is_active=True,
        )
        
        response = authenticated_client.get(reverse('dashboard:admin_dashboard'))
        assert response.status_code == 200
        
        content = response.content.decode()
        assert 'Total Vendors' in content
        assert 'Approved Vendors' in content
    
    def test_dashboard_recent_applications(self, authenticated_client):
        """Test dashboard shows recent applications."""
        VendorApplication.objects.create(
            business_name='Recent Business',
            contact_email='recent@test.com',
            status=VendorApplication.Status.PENDING,
        )
        
        response = authenticated_client.get(reverse('dashboard:admin_dashboard'))
        assert response.status_code == 200
        assert 'Recent Business' in response.content.decode()
    
    def test_dashboard_pending_approvals(self, authenticated_client):
        """Test dashboard shows pending approvals."""
        VendorApplication.objects.create(
            business_name='Pending Business',
            contact_email='pending@test.com',
            status=VendorApplication.Status.PENDING,
        )
        
        response = authenticated_client.get(reverse('dashboard:admin_dashboard'))
        assert response.status_code == 200
        assert 'Pending Business' in response.content.decode()


@pytest.mark.django_db
class TestAdminSettings:
    """Tests for admin settings view."""
    
    def test_settings_accessible(self, authenticated_client):
        """Test admin settings is accessible."""
        response = authenticated_client.get(reverse('dashboard:admin_settings'))
        assert response.status_code == 200
        assert 'Settings' in response.content.decode()


@pytest.mark.django_db
class TestAdminReports:
    """Tests for admin reports view."""
    
    def test_reports_accessible(self, authenticated_client):
        """Test admin reports is accessible."""
        response = authenticated_client.get(reverse('dashboard:admin_reports'))
        assert response.status_code == 200
        assert 'Reports' in response.content.decode()


@pytest.mark.django_db
class TestVendorListView:
    """Tests for vendor list view."""
    
    def test_vendor_list_accessible(self, authenticated_client):
        """Test vendor list is accessible."""
        VendorProfile.objects.create(
            user=User.objects.create_user(
                email='vendor@test.com',
                password='VendorPass123!',
                first_name='Vendor',
                last_name='User',
                role=User.Role.VENDOR,
            ),
            vendor_id='VND12345678',
            business_name='Test Vendor',
            contact_email='vendor@test.com',
            is_active=True,
        )
        
        response = authenticated_client.get(reverse('dashboard:vendor_list'))
        assert response.status_code == 200
        assert 'Test Vendor' in response.content.decode()
    
    def test_vendor_list_search(self, authenticated_client):
        """Test vendor list search."""
        VendorProfile.objects.create(
            user=User.objects.create_user(
                email='vendor1@test.com',
                password='VendorPass123!',
                first_name='Vendor',
                last_name='One',
                role=User.Role.VENDOR,
            ),
            vendor_id='VND11111111',
            business_name='Electronics Store',
            contact_email='vendor1@test.com',
        )
        VendorProfile.objects.create(
            user=User.objects.create_user(
                email='vendor2@test.com',
                password='VendorPass123!',
                first_name='Vendor',
                last_name='Two',
                role=User.Role.VENDOR,
            ),
            vendor_id='VND22222222',
            business_name='Clothing Shop',
            contact_email='vendor2@test.com',
        )
        
        response = authenticated_client.get(
            reverse('dashboard:vendor_list'),
            {'search': 'Electronics'}
        )
        assert response.status_code == 200
        assert 'Electronics Store' in response.content.decode()
        assert 'Clothing Shop' not in response.content.decode()


@pytest.mark.django_db
class TestVendorDetailView:
    """Tests for vendor detail view."""
    
    def test_vendor_detail_accessible(self, authenticated_client):
        """Test vendor detail is accessible."""
        vendor = VendorProfile.objects.create(
            user=User.objects.create_user(
                email='vendor@test.com',
                password='VendorPass123!',
                first_name='Vendor',
                last_name='User',
                role=User.Role.VENDOR,
            ),
            vendor_id='VND12345678',
            business_name='Detail Vendor',
            contact_email='vendor@test.com',
            is_active=True,
        )
        
        response = authenticated_client.get(
            reverse('dashboard:vendor_detail', kwargs={'pk': vendor.pk})
        )
        assert response.status_code == 200
        assert 'Detail Vendor' in response.content.decode()
        assert 'VND12345678' in response.content.decode()


@pytest.mark.django_db
class TestDashboardRoleBasedAccessControl:
    """Rigorous tests for role-based access control across dashboard views."""

    @pytest.mark.parametrize('view_name', [
        'dashboard:admin_dashboard',
        'dashboard:admin_settings',
        'dashboard:admin_reports',
        'dashboard:vendor_list',
        'dashboard:vendor_applications',
    ])
    def test_unauthenticated_user_denied_admin_dashboard(self, client, view_name):
        response = client.get(reverse(view_name))
        assert response.status_code == 302
        assert reverse('accounts:login') in response.url

    @pytest.mark.parametrize('view_name', [
        'dashboard:admin_dashboard',
        'dashboard:admin_settings',
        'dashboard:admin_reports',
        'dashboard:vendor_list',
        'dashboard:vendor_applications',
    ])
    def test_customer_user_denied_admin_dashboard(self, customer_client, view_name):
        response = customer_client.get(reverse(view_name))
        assert response.status_code == 302
        assert reverse('accounts:login') in response.url

    @pytest.mark.parametrize('view_name', [
        'dashboard:admin_dashboard',
        'dashboard:admin_settings',
        'dashboard:admin_reports',
        'dashboard:vendor_list',
        'dashboard:vendor_applications',
    ])
    def test_vendor_user_denied_admin_dashboard(self, vendor_client, view_name):
        response = vendor_client.get(reverse(view_name))
        assert response.status_code == 302
        assert reverse('accounts:login') in response.url

    def test_customer_denied_vendor_profile(self, customer_client):
        response = customer_client.get(reverse('vendors:profile'))
        assert response.status_code == 302
        assert reverse('accounts:login') in response.url

    def test_customer_denied_vendor_profile_edit(self, customer_client):
        response = customer_client.get(reverse('vendors:profile_edit'))
        assert response.status_code == 302
        assert reverse('accounts:login') in response.url

    def test_vendor_can_access_own_profile_edit(self, vendor_client, vendor_user):
        VendorProfile.objects.create(
            user=vendor_user,
            vendor_id='VND11111111',
            business_name='Vendor One',
            contact_email=vendor_user.email,
        )
        response = vendor_client.get(reverse('vendors:profile_edit'))
        assert response.status_code == 200
