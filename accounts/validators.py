"""
Custom password validators for ShopSense.
"""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class CustomPasswordValidator:
    """
    Validates that the password meets additional security requirements:
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    - Not a commonly used password
    """

    def __init__(self):
        self.common_passwords = {
            'password', 'password123', 'admin123', '1234567890',
            'qwerty123', 'welcome123', 'shopsense', 'shopsense123',
        }

    def validate(self, password, user=None):
        errors = []

        if len(password) < 10:
            errors.append(_('Password must be at least 10 characters long.'))

        if not any(c.isupper() for c in password):
            errors.append(_('Password must contain at least one uppercase letter.'))

        if not any(c.islower() for c in password):
            errors.append(_('Password must contain at least one lowercase letter.'))

        if not any(c.isdigit() for c in password):
            errors.append(_('Password must contain at least one digit.'))

        if not any(not c.isalnum() for c in password):
            errors.append(_('Password must contain at least one special character.'))

        if password.lower() in self.common_passwords:
            errors.append(_('This password is too common. Please choose a different one.'))

        if user and user.email and user.email.split('@')[0].lower() in password.lower():
            errors.append(_('Password cannot contain your email username.'))

        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _(
            'Password must be at least 10 characters long and contain '
            'uppercase, lowercase, digit, and special character.'
        )