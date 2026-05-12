"""
Marketing signals — links Subscriber to UnifiedUser on save.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='marketing.Subscriber')
def link_subscriber_to_unified_user(sender, instance, **kwargs):
    """Resolve UnifiedUser from email or phone and link it to the subscriber."""
    if instance.unified_user_id:
        return  # Already linked

    phone = instance.phone or ''
    email = instance.email or ''

    if not phone and not email:
        return

    try:
        from apps.users.models import UnifiedUser
        user, created = UnifiedUser.resolve(
            phone=phone,
            email=email,
            name=instance.name or '',
        )
        # Use queryset update to avoid triggering this signal again
        sender.objects.filter(pk=instance.pk).update(unified_user=user)
        logger.info(
            '[Subscriber] Linked %s to UnifiedUser %s (created=%s)',
            instance.email,
            user.id,
            created,
        )
    except Exception as exc:
        logger.warning('[Subscriber] Could not link to UnifiedUser: %s', exc)
