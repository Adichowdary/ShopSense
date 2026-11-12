"""
Authentication tests for ShopSense.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    """Tests for custom User model."""
    
    def test_create_user(self):
        """Test creating a regular user."""
        user = User.objects.create_user(
            email='test@example.com',
            password='TestPass123!',
            first_name='Test',
            last_name='User',
        )
        assert user.email == 'test@example.com'
        assert user.first_name == 'Test'
        assert user.last_name == 'User'
        assert user.check_password('TestPass123!')
        assert user.is_active is True
        assert user.is_staff is False
        assert user.role == User.Role.CUSTOMER
    
    def test_create_superuser(self):
        """Test creating a superuser."""
        admin = User.objects.create_superuser(
            email='admin@example.com',
            password='AdminPass123!',
            first_name='Admin',
            last_name='User',
        )
        assert admin.email == 'admin@example.com'
        assert admin.is_staff is True
        assert admin.is_superuser is True
        assert admin.role == User.Role.ADMIN
        assert admin.is_active is True
    
    def test_email_normalization(self):
        """Test email is normalized to lowercase."""
        user = User.objects.create_user(
            email='TEST@EXAMPLE.COM',
            password='TestPass123!',
            first_name='Test',
            last_name='User',
        )
        assert user.email == 'test@example.com'
    
    def test_get_full_name(self):
        """Test get_full_name method."""
        user = User.objects.create_user(
            email='test@example.com',
            password='TestPass123!',
            first_name='John',
            last_name='Doe',
        )
        assert user.get_full_name() == 'John Doe'
    
    def test_role_check_methods(self):
        """Test role check methods."""
        admin = User.objects.create_superuser(
            email='admin@example.com',
            password='AdminPass123!',
            first_name='Admin',
            last_name='User',
        )
        vendor = User.objects.create_user(
            email='vendor@example.com',
            password='VendorPass123!',
            first_name='Vendor',
            last_name='User',
            role=User.Role.VENDOR,
        )
        customer = User.objects.create_user(
            email='customer@example.com',
            password='CustomerPass123!',
            first_name='Customer',
            last_name='User',
            role=User.Role.CUSTOMER,
        )
        
        assert admin.is_admin() is True
        assert admin.is_vendor() is False
        assert admin.is_customer() is False
        
        assert vendor.is_admin() is False
        assert vendor.is_vendor() is True
        assert vendor.is_customer() is False
        
        assert customer.is_admin() is False
        assert customer.is_vendor() is False
        assert customer.is_customer() is True
    
    def test_failed_login_tracking(self):
        """Test failed login attempt tracking."""
        user = User.objects.create_user(
            email='test@example.com',
            password='TestPass123!',
            first_name='Test',
            last_name='User',
        )
        
        assert user.failed_login_attempts == 0
        assert user.is_locked() is False
        
        user.increment_failed_login()
        assert user.failed_login_attempts == 1
        
        # Lock after 5 attempts
        for _ in range(4):
            user.increment_failed_login()
        assert user.failed_login_attempts == 5
        assert user.is_locked() is True
        
        user.reset_failed_login()
        assert user.failed_login_attempts == 0
        assert user.is_locked() is False
    
    def test_can_access_dashboards(self):
        """Test dashboard access permissions."""
        admin = User.objects.create_superuser(
            email='admin@example.com',
            password='AdminPass123!',
            first_name='Admin',
            last_name='User',
        )
        vendor = User.objects.create_user(
            email='vendor@example.com',
            password='VendorPass123!',
            first_name='Vendor',
            last_name='User',
            role=User.Role.VENDOR,
        )
        customer = User.objects.create_user(
            email='customer@example.com',
            password='CustomerPass123!',
            first_name='Customer',
            last_name='User',
        )
        
        assert admin.can_access_admin_dashboard() is True
        assert admin.can_access_vendor_dashboard() is False
        
        assert vendor.can_access_admin_dashboard() is False
        assert vendor.can_access_vendor_dashboard() is True
        
        assert customer.can_access_admin_dashboard() is False
        assert customer.can_access_vendor_dashboard() is False


@pytest.mark.django_db
class TestLoginView:
    """Tests for login view."""
    
    def test_login_page_accessible(self, client):
        """Test login page is accessible."""
        response = client.get(reverse('accounts:login'))
        assert response.status_code == 200
        assert 'Sign In' in response.content.decode()
    
    def test_login_success(self, client):
        """Test successful login."""
        User.objects.create_user(
            email='test@example.com',
            password='TestPass123!',
            first_name='Test',
            last_name='User',
        )
        
        response = client.post(reverse('accounts:login'), {
            'username': 'test@example.com',
            'password': 'TestPass123!',
        })
        
        assert response.status_code == 302  # Redirect after login
        assert '_auth_user_id' in client.session
    
    def test_login_failure(self, client):
        """Test failed login."""
        User.objects.create_user(
            email='test@example.com',
            password='TestPass123!',
            first_name='Test',
            last_name='User',
        )
        
        response = client.post(reverse('accounts:login'), {
            'username': 'test@example.com',
            'password': 'WrongPassword',
        })
        
        assert response.status_code == 200
        assert 'Invalid email or password' in response.content.decode()
        assert '_auth_user_id' not in client.session
    
    def test_login_nonexistent_user(self, client):
        """Test login with nonexistent user."""
        response = client.post(reverse('accounts:login'), {
            'username': 'nonexistent@example.com',
            'password': 'TestPass123!',
        })
        
        assert response.status_code == 200
        assert 'Invalid email or password' in response.content.decode()
    
    def test_locked_account(self, client):
        """Test locked account cannot login."""
        user = User.objects.create_user(
            email='locked@example.com',
            password='TestPass123!',
            first_name='Locked',
            last_name='User',
        )
        # Lock the account
        user.failed_login_attempts = 5
        user.locked_until = None  # Will be set by increment_failed_login
        user.save()
        
        # Make it locked
        from datetime import timedelta

        from django.utils import timezone
        user.locked_until = timezone.now() + timedelta(minutes=15)
        user.save()
        
        response = client.post(reverse('accounts:login'), {
            'username': 'locked@example.com',
            'password': 'TestPass123!',
        })
        
        assert response.status_code == 200
        assert 'temporarily locked' in response.content.decode()

    def test_login_redirect_by_role(self, client):
        """Test that login redirects users according to their role."""
        # Customer redirect
        User.objects.create_user(
            email='customer@example.com',
            password='CustomerPass123!',
            role=User.Role.CUSTOMER,
        )
        res_customer = client.post(reverse('accounts:login'), {
            'username': 'customer@example.com',
            'password': 'CustomerPass123!',
        })
        assert res_customer.status_code == 302
        assert res_customer.url == reverse('store:home')
        client.logout()

        # Vendor redirect
        User.objects.create_user(
            email='vendor@example.com',
            password='VendorPass123!',
            role=User.Role.VENDOR,
        )
        res_vendor = client.post(reverse('accounts:login'), {
            'username': 'vendor@example.com',
            'password': 'VendorPass123!',
        })
        assert res_vendor.status_code == 302
        assert res_vendor.url == reverse('vendors:profile')
        client.logout()

        # Admin redirect
        User.objects.create_superuser(
            email='admin@example.com',
            password='AdminPass123!',
        )
        res_admin = client.post(reverse('accounts:login'), {
            'username': 'admin@example.com',
            'password': 'AdminPass123!',
        })
        assert res_admin.status_code == 302
        assert res_admin.url == reverse('dashboard:admin_dashboard')
        client.logout()

    def test_customer_login_ignores_unauthorized_dashboard_next(self, client):
        """Test customer logging in with next=/dashboard/ is safely redirected to home."""
        User.objects.create_user(
            email='cust_loop@example.com',
            password='Pass123!Safe',
            role=User.Role.CUSTOMER,
        )
        login_url = f"{reverse('accounts:login')}?next={reverse('dashboard:admin_dashboard')}"
        response = client.post(login_url, {
            'username': 'cust_loop@example.com',
            'password': 'Pass123!Safe',
        })
        assert response.status_code == 302
        assert response.url == reverse('store:home')

    def test_authenticated_dispatch_redirects_safely(self, client):
        """Test authenticated user visiting login page is redirected to portal without loop."""
        cust = User.objects.create_user(
            email='dispatch_cust@example.com',
            password='Pass123!Safe',
            role=User.Role.CUSTOMER,
        )
        client.force_login(cust)
        response = client.get(reverse('accounts:login'))
        assert response.status_code == 302
        assert response.url == reverse('store:home')


@pytest.mark.django_db
class TestLogoutView:
    """Tests for logout view."""
    
    def test_logout(self, authenticated_client):
        """Test logout."""
        response = authenticated_client.get(reverse('accounts:logout'))
        assert response.status_code == 302
        assert '_auth_user_id' not in authenticated_client.session


@pytest.mark.django_db
class TestRegistrationView:
    """Tests for registration view."""
    
    def test_registration_page_accessible(self, client):
        """Test registration page is accessible."""
        response = client.get(reverse('accounts:register'))
        assert response.status_code == 200
        assert 'Create Account' in response.content.decode()
    
    def test_registration_success(self, client):
        """Test successful registration."""
        response = client.post(reverse('accounts:register'), {
            'email': 'newuser@example.com',
            'first_name': 'New',
            'last_name': 'User',
            'password1': 'NewPass123!',
            'password2': 'NewPass123!',
            'role': User.Role.CUSTOMER,
        })
        
        assert response.status_code == 302  # Redirect after registration
        assert User.objects.filter(email='newuser@example.com').exists()
    
    def test_registration_password_mismatch(self, client):
        """Test registration with password mismatch."""
        response = client.post(reverse('accounts:register'), {
            'email': 'newuser@example.com',
            'first_name': 'New',
            'last_name': 'User',
            'password1': 'NewPass123!',
            'password2': 'DifferentPass123!',
            'role': User.Role.CUSTOMER,
        })
        
        assert response.status_code == 200
        assert 'password' in response.content.decode().lower()
    
    def test_registration_duplicate_email(self, client):
        """Test registration with duplicate email."""
        User.objects.create_user(
            email='existing@example.com',
            password='TestPass123!',
            first_name='Existing',
            last_name='User',
        )
        
        response = client.post(reverse('accounts:register'), {
            'email': 'existing@example.com',
            'first_name': 'New',
            'last_name': 'User',
            'password1': 'NewPass123!',
            'password2': 'NewPass123!',
            'role': User.Role.CUSTOMER,
        })
        
        assert response.status_code == 200
        assert 'already exists' in response.content.decode()


@pytest.mark.django_db
class TestPasswordReset:
    """Tests for password reset flow."""
    
    def test_password_reset_request(self, client):
        """Test password reset request."""
        User.objects.create_user(
            email='reset@example.com',
            password='TestPass123!',
            first_name='Reset',
            last_name='User',
        )
        
        response = client.post(reverse('accounts:password_reset'), {
            'email': 'reset@example.com',
        })
        
        assert response.status_code == 302
    
    def test_password_reset_nonexistent(self, client):
        """Test password reset for nonexistent user."""
        response = client.post(reverse('accounts:password_reset'), {
            'email': 'nonexistent@example.com',
        })
        
        # Should not reveal if user exists
        assert response.status_code == 302


@pytest.mark.django_db
class TestProfileView:
    """Tests for profile views."""
    
    def test_profile_view_authenticated(self, authenticated_client):
        """Test profile view requires authentication."""
        response = authenticated_client.get(reverse('accounts:profile'))
        assert response.status_code == 200
    
    def test_profile_view_unauthenticated(self, client):
        """Test profile view redirects unauthenticated users."""
        response = client.get(reverse('accounts:profile'))
        assert response.status_code == 302
    
    def test_profile_update(self, authenticated_client, admin_user):
        """Test profile update."""
        response = authenticated_client.post(reverse('accounts:profile_edit'), {
            'first_name': 'Updated',
            'last_name': 'Name',
            'phone': '+91 98765 43210',
        })
        
        assert response.status_code == 302
        admin_user.refresh_from_db()
        assert admin_user.first_name == 'Updated'
        assert admin_user.last_name == 'Name'
        assert admin_user.phone == '+91 98765 43210'