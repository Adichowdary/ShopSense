"""
Signals for ShopSense Vendors app.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import VendorApplication, VendorProfile


@receiver(post_save, sender=VendorApplication)
def vendor_application_post_save(sender, instance, created, **kwargs):
    """Handle post-save actions for VendorApplication."""
    if created:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f'Vendor application created: {instance.vendor_id} - {instance.business_name}')


@receiver(post_save, sender=VendorProfile)
def vendor_profile_post_save(sender, instance, created, **kwargs):
    """Handle post-save actions for VendorProfile."""
    if created:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f'Vendor profile created: {instance.vendor_id} - {instance.business_name}')