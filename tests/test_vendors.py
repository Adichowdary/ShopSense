"""
Vendor tests for ShopSense.
"""

import pytest
from django.urls import reverse

from accounts.models import User
from vendors.models import AuditLog, VendorApplication, VendorProfile

User = User


@pytest.mark.django_db
class TestVendorApplicationModel:
    """Tests for VendorApplication model."""
    
    def test_create_vendor_application(self):
        """Test creating a vendor application."""
        application = VendorApplication.objects.create(
            business_name='Test Business',
            business_description='A test business',
            contact_email='vendor@test.com',
            contact_phone='+91 98765 43210',
            business_address='123 Test Street',
            city='Mumbai',
            state='Maharashtra',
            postal_code='400001',
            country='India',
            tax_id='GST123456789',
            website='https://testbusiness.com',
        )
        
        assert application.business_name == 'Test Business'
        assert application.contact_email == 'vendor@test.com'
        assert application.status == VendorApplication.Status.PENDING
        assert application.vendor_id.startswith('VND')
        assert len(application.vendor_id) == 11  # VND + 8 digits
        assert application.submitted_at is not None
    
    def test_vendor_id_generation(self):
        """Test vendor ID is generated automatically."""
        app1 = VendorApplication.objects.create(
            business_name='Business 1',
            contact_email='vendor1@test.com',
        )
        app2 = VendorApplication.objects.create(
            business_name='Business 2',
            contact_email='vendor2@test.com',
        )
        
        assert app1.vendor_id != app2.vendor_id
        assert app1.vendor_id.startswith('VND')
        assert app2.vendor_id.startswith('VND')
    
    def test_approve_application(self):
        """Test approving a vendor application."""
        admin = User.objects.create_superuser(
            email='admin@example.com',
            password='AdminPass123!',
            first_name='Admin',
            last_name='User',
        )
        
        application = VendorApplication.objects.create(
            business_name='Test Business',
            contact_email='vendor@test.com',
        )
        
        application.approve(admin, 'Approved after review')
        
        application.refresh_from_db()
        assert application.status == VendorApplication.Status.APPROVED
        assert application.reviewed_by == admin
        assert application.reviewed_at is not None
        assert application.admin_notes == 'Approved after review'
        
        # Check vendor profile was created
        vendor_profile = VendorProfile.objects.get(vendor_id=application.vendor_id)
        assert vendor_profile.business_name == 'Test Business'
        assert vendor_profile.contact_email == 'vendor@test.com'
        assert vendor_profile.is_active is True
        
        # Check user role was updated
        user = User.objects.get(email='vendor@test.com')
        assert user.role == User.Role.VENDOR
    
    def test_reject_application(self):
        """Test rejecting a vendor application."""
        admin = User.objects.create_superuser(
            email='admin@example.com',
            password='AdminPass123!',
            first_name='Admin',
            last_name='User',
        )
        
        application = VendorApplication.objects.create(
            business_name='Test Business',
            contact_email='vendor@test.com',
        )
        
        application.reject(admin, 'Does not meet requirements')
        
        application.refresh_from_db()
        assert application.status == VendorApplication.Status.REJECTED
        assert application.reviewed_by == admin
        assert application.admin_notes == 'Does not meet requirements'
        
        # No vendor profile should be created
        assert not VendorProfile.objects.filter(vendor_id=application.vendor_id).exists()
    
    def test_request_more_info(self):
        """Test requesting more information."""
        admin = User.objects.create_superuser(
            email='admin@example.com',
            password='AdminPass123!',
            first_name='Admin',
            last_name='User',
        )
        
        application = VendorApplication.objects.create(
            business_name='Test Business',
            contact_email='vendor@test.com',
        )
        
        application.request_more_info(admin, 'Please provide GST certificate')
        
        application.refresh_from_db()
        assert application.status == VendorApplication.Status.MORE_INFO
        assert application.admin_notes == 'Please provide GST certificate'


@pytest.mark.django_db
class TestVendorProfileModel:
    """Tests for VendorProfile model."""
    
    def test_create_vendor_profile(self):
        """Test creating a vendor profile."""
        user = User.objects.create_user(
            email='vendor@example.com',
            password='VendorPass123!',
            first_name='Vendor',
            last_name='User',
            role=User.Role.VENDOR,
        )
        
        vendor = VendorProfile.objects.create(
            user=user,
            vendor_id='VND12345678',
            business_name='Test Vendor',
            contact_email='vendor@example.com',
        )
        
        assert vendor.business_name == 'Test Vendor'
        assert vendor.vendor_id == 'VND12345678'
        assert vendor.is_active is True
        assert vendor.is_verified is False
        assert vendor.commission_rate == 10.00
    
    def test_vendor_profile_str(self):
        """Test vendor profile string representation."""
        user = User.objects.create_user(
            email='vendor@example.com',
            password='VendorPass123!',
            first_name='Vendor',
            last_name='User',
            role=User.Role.VENDOR,
        )
        
        vendor = VendorProfile.objects.create(
            user=user,
            vendor_id='VND12345678',
            business_name='Test Vendor',
            contact_email='vendor@example.com',
        )
        
        assert str(vendor) == 'Test Vendor (VND12345678)'


@pytest.mark.django_db
class TestVendorOnboardingView:
    """Tests for vendor onboarding view."""
    
    def test_onboarding_page_accessible(self, client):
        """Test onboarding page is accessible."""
        response = client.get(reverse('vendors:onboarding'))
        assert response.status_code == 200
        assert 'Become a Vendor' in response.content.decode()
    
    def test_onboarding_submission(self, client):
        """Test successful vendor application submission."""
        response = client.post(reverse('vendors:onboarding'), {
            'business_name': 'New Vendor Business',
            'business_description': 'We sell great products',
            'contact_email': 'newvendor@test.com',
            'contact_phone': '+91 98765 43210',
            'business_address': '456 Vendor Lane',
            'city': 'Delhi',
            'state': 'Delhi',
            'postal_code': '110001',
            'country': 'India',
            'tax_id': 'GST987654321',
            'website': 'https://newvendor.com',
        })
        
        assert response.status_code == 302  # Redirect to success page
        
        application = VendorApplication.objects.get(contact_email='newvendor@test.com')
        assert application.business_name == 'New Vendor Business'
        assert application.status == VendorApplication.Status.PENDING
    
    def test_onboarding_duplicate_pending(self, client):
        """Test duplicate pending application is rejected."""
        VendorApplication.objects.create(
            business_name='Existing Business',
            contact_email='duplicate@test.com',
            status=VendorApplication.Status.PENDING,
        )
        
        response = client.post(reverse('vendors:onboarding'), {
            'business_name': 'New Business',
            'contact_email': 'duplicate@test.com',
        })
        
        assert response.status_code == 200
        assert 'already a pending application' in response.content.decode()


@pytest.mark.django_db
class TestAdminVendorViews:
    """Tests for admin vendor management views."""
    
    def test_admin_applications_list(self, authenticated_client):
        """Test admin vendor applications list."""
        # Create test applications
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
        
        response = authenticated_client.get(reverse('dashboard:vendor_applications'))
        assert response.status_code == 200
        assert 'Business 1' in response.content.decode()
        assert 'Business 2' in response.content.decode()
    
    def test_admin_application_detail(self, authenticated_client):
        """Test admin vendor application detail."""
        application = VendorApplication.objects.create(
            business_name='Detail Business',
            contact_email='detail@test.com',
            status=VendorApplication.Status.PENDING,
        )
        
        response = authenticated_client.get(
            reverse('dashboard:vendor_application_detail', kwargs={'pk': application.pk})
        )
        assert response.status_code == 200
        assert 'Detail Business' in response.content.decode()
        assert 'detail@test.com' in response.content.decode()
    
    def test_admin_approve_application(self, authenticated_client, admin_user):
        """Test admin approving application."""
        application = VendorApplication.objects.create(
            business_name='Approve Business',
            contact_email='approve@test.com',
            status=VendorApplication.Status.PENDING,
        )
        
        response = authenticated_client.post(
            reverse('dashboard:vendor_application_action', kwargs={'pk': application.pk}),
            {
                'action': 'approve',
                'notes': 'Looks good',
            }
        )
        
        assert response.status_code == 302
        application.refresh_from_db()
        assert application.status == VendorApplication.Status.APPROVED
        
        # Check audit log was created
        assert AuditLog.objects.filter(
            action=AuditLog.ActionType.VENDOR_APPROVED,
            target_vendor__isnull=False,
        ).exists()
    
    def test_admin_reject_application(self, authenticated_client, admin_user):
        """Test admin rejecting application."""
        application = VendorApplication.objects.create(
            business_name='Reject Business',
            contact_email='reject@test.com',
            status=VendorApplication.Status.PENDING,
        )
        
        response = authenticated_client.post(
            reverse('dashboard:vendor_application_action', kwargs={'pk': application.pk}),
            {
                'action': 'reject',
                'notes': 'Incomplete information',
            }
        )
        
        assert response.status_code == 302
        application.refresh_from_db()
        assert application.status == VendorApplication.Status.REJECTED
        
        # Check audit log was created
        assert AuditLog.objects.filter(
            action=AuditLog.ActionType.VENDOR_REJECTED,
        ).exists()
    
    def test_admin_request_more_info(self, authenticated_client, admin_user):
        """Test admin requesting more info."""
        application = VendorApplication.objects.create(
            business_name='More Info Business',
            contact_email='moreinfo@test.com',
            status=VendorApplication.Status.PENDING,
        )
        
        response = authenticated_client.post(
            reverse('dashboard:vendor_application_action', kwargs={'pk': application.pk}),
            {
                'action': 'more_info',
                'notes': 'Need GST certificate',
            }
        )
        
        assert response.status_code == 302
        application.refresh_from_db()
        assert application.status == VendorApplication.Status.MORE_INFO


@pytest.mark.django_db
class TestVendorAccessControl:
    """Tests for vendor access control."""
    
    def test_vendor_cannot_access_admin_views(self, vendor_client):
        """Test vendor cannot access admin dashboard."""
        response = vendor_client.get(reverse('dashboard:admin_dashboard'))
        assert response.status_code == 302  # Redirect to login
    
    def test_customer_cannot_access_admin_views(self, customer_client):
        """Test customer cannot access admin dashboard."""
        response = customer_client.get(reverse('dashboard:admin_dashboard'))
        assert response.status_code == 302  # Redirect to login
    
    def test_vendor_can_access_own_profile(self, vendor_client, vendor_user):
        """Test vendor can access own profile."""
        VendorProfile.objects.create(
            user=vendor_user,
            vendor_id='VND12345678',
            business_name='My Vendor',
            contact_email=vendor_user.email,
        )
        
        response = vendor_client.get(reverse('vendors:profile'))
        assert response.status_code == 200
        assert 'My Vendor' in response.content.decode()