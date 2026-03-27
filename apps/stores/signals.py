"""
Django signals for the stores app.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='stores.StoreOrder')
def on_order_created(sender, instance, created, **kwargs):
    """Trigger push notification when a new order is created."""
    if not created:
        return
    try:
        from apps.stores.tasks import notify_new_order_push
        notify_new_order_push.delay(str(instance.id))
    except Exception as e:
        logger.error(f"on_order_created signal error: {e}")
