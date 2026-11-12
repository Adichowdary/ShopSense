"""
Authentication and Role-Based Access Control (RBAC) dependencies for ShopSense FastAPI.
Seamlessly integrates with Django Authentication and Custom User model.
"""

import os
from typing import Optional
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore

User = get_user_model()


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    sessionid: Optional[str] = Cookie(None),
) -> User:
    """
    Authenticate the request against Django's authentication system.
    Supports session cookies, Bearer tokens, or email/API headers.
    """
    # 1. Check Session Cookie (Browser requests)
    if sessionid:
        try:
            session = SessionStore(session_key=sessionid)
            user_id = session.get('_auth_user_id')
            if user_id:
                user = User.objects.filter(pk=user_id, is_active=True).first()
                if user:
                    return user
        except Exception:
            pass

    # 2. Check Authorization Bearer Token
    if authorization and authorization.startswith('Bearer '):
        token = authorization.split(' ', 1)[1].strip()
        # Token can be user email or raw primary key
        user = User.objects.filter(email__iexact=token, is_active=True).first()
        if not user and token.isdigit():
            user = User.objects.filter(pk=int(token), is_active=True).first()
        if user:
            return user

    # 3. Check X-User-Email header (testing / internal microservices)
    if x_user_email:
        user = User.objects.filter(email__iexact=x_user_email.strip(), is_active=True).first()
        if user:
            return user

    # 4. Check API Key header (admin token)
    api_secret = getattr(settings, 'SECRET_KEY', 'default_insecure_secret')
    if x_api_key and x_api_key == api_secret:
        admin_user = User.objects.filter(role=User.Role.ADMIN, is_active=True).first()
        if admin_user:
            return admin_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please provide a valid session or Bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Enforce Administrator privileges."""
    if not (user.is_authenticated and hasattr(user, 'can_access_admin_dashboard') and user.can_access_admin_dashboard()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Administrative privileges required to access this analytics resource.",
        )
    return user


def require_vendor(user: User = Depends(get_current_user)) -> User:
    """Enforce Active Vendor role and valid profile."""
    if not (user.is_authenticated and hasattr(user, 'can_access_vendor_dashboard') and user.can_access_vendor_dashboard()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Active vendor account required.",
        )
    if not (hasattr(user, 'vendor_profile') and user.vendor_profile and user.vendor_profile.is_active):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Verified vendor profile is required.",
        )
    return user


def require_admin_or_vendor(user: User = Depends(get_current_user)) -> User:
    """Allow access to either Admins or Vendors."""
    is_admin = hasattr(user, 'can_access_admin_dashboard') and user.can_access_admin_dashboard()
    is_vendor = (
        hasattr(user, 'can_access_vendor_dashboard')
        and user.can_access_vendor_dashboard()
        and hasattr(user, 'vendor_profile')
        and user.vendor_profile
        and user.vendor_profile.is_active
    )
    if not (is_admin or is_vendor):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Elevated privileges required.",
        )
    return user

