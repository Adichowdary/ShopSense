"""
Signals for ShopSense Accounts app.
"""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def user_post_save(sender, instance, created, **kwargs):
    """Handle post-save actions for User model."""
    if created:
        # Log user creation
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f'New user created: {instance.email} (ID: {instance.id})')