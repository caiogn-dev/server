"""
Signals para sincronização automática de UnifiedUser.

NÃO ALTERA modelos existentes - apenas cria/atualiza UnifiedUser.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum, Count

from .models import UnifiedUser, UnifiedUserActivity

logger = logging.getLogger(__name__)


@receiver(post_save, sender='conversations.Conversation')
def sync_conversation_to_unified_user(sender, instance, created, **kwargs):
    """
    Quando uma conversa é criada/atualizada, sincroniza com UnifiedUser.
    NÃO ALTERA Conversation, apenas lê dados.
    """
    if not instance.phone_number:
        return

    try:
        user, user_created = UnifiedUser.objects.get_or_create(
            phone_number=instance.phone_number,
            defaults={
                'name': instance.contact_name or 'Desconhecido',
            }
        )

        if instance.contact_name and not user.name:
            user.name = instance.contact_name
            user.save(update_fields=['name'])

        if created:
            UnifiedUserActivity.objects.create(
                user=user,
                activity_type=UnifiedUserActivity.ActivityType.WHATSAPP_MESSAGE,
                description=f'Conversa iniciada: {instance.id}',
                metadata={'conversation_id': str(instance.id)}
            )

        logger.info(f"[UnifiedUser] Synced conversation {instance.id} to user {user.id}")

    except Exception as e:
        logger.error(f"[UnifiedUser] Error syncing conversation: {e}")


@receiver(post_save, sender='whatsapp.Message')
def sync_whatsapp_message_to_activity(sender, instance, created, **kwargs):
    """Registra atividade quando mensagem é recebida."""
    if not created or not instance.conversation:
        return

    try:
        phone = instance.conversation.phone_number
        user = UnifiedUser.objects.filter(phone_number=phone).first()

        if user:
            UnifiedUserActivity.objects.create(
                user=user,
                activity_type=UnifiedUserActivity.ActivityType.WHATSAPP_MESSAGE,
                description=f'Mensagem {instance.direction}',
                metadata={
                    'message_id': str(instance.id),
                    'direction': instance.direction,
                    'message_type': instance.message_type,
                }
            )
            user.save(update_fields=['last_seen_at'])

    except Exception as e:
        logger.error(f"[UnifiedUser] Error logging message activity: {e}")


@receiver(post_save, sender='stores.StoreOrder')
def sync_store_order_to_unified_user(sender, instance, created, **kwargs):
    """
    Quando um pedido é criado ou atualizado, sincroniza estatísticas no UnifiedUser.
    Atualiza: total_orders, total_spent, last_order_at.
    Usa o phone do pedido para encontrar o UnifiedUser correspondente.
    """
    phone = (instance.customer_phone or '').strip()
    if not phone:
        return

    try:
        # Normaliza o número removendo caracteres não-numéricos (exceto +)
        normalized = ''.join(c for c in phone if c.isdigit() or c == '+')
        if not normalized:
            return

        # Tenta encontrar UnifiedUser por telefone (com ou sem +55)
        user = (
            UnifiedUser.objects.filter(phone_number=normalized).first()
            or UnifiedUser.objects.filter(phone_number=normalized.lstrip('+')).first()
            or UnifiedUser.objects.filter(phone_number='+' + normalized.lstrip('+')).first()
        )

        if not user:
            return

        # Recalcula os totais a partir de todos os pedidos deste telefone
        from apps.stores.models import StoreOrder
        stats = StoreOrder.objects.filter(
            customer_phone__in=[normalized, normalized.lstrip('+'), '+' + normalized.lstrip('+')],
        ).aggregate(
            total_orders=Count('id'),
            total_spent=Sum('total'),
        )

        last_order = StoreOrder.objects.filter(
            customer_phone__in=[normalized, normalized.lstrip('+'), '+' + normalized.lstrip('+')],
        ).order_by('-created_at').values_list('created_at', flat=True).first()

        update_fields = []

        new_total_orders = stats['total_orders'] or 0
        if user.total_orders != new_total_orders:
            user.total_orders = new_total_orders
            update_fields.append('total_orders')

        new_total_spent = stats['total_spent'] or 0
        if user.total_spent != new_total_spent:
            user.total_spent = new_total_spent
            update_fields.append('total_spent')

        if last_order and user.last_order_at != last_order:
            user.last_order_at = last_order
            update_fields.append('last_order_at')

        if update_fields:
            update_fields.append('last_seen_at')
            user.save(update_fields=update_fields)
            logger.info(f"[UnifiedUser] Updated order stats for {phone}: orders={new_total_orders}, spent={new_total_spent}")

        if created:
            UnifiedUserActivity.objects.create(
                user=user,
                activity_type=UnifiedUserActivity.ActivityType.SITE_ORDER,
                description=f'Pedido #{instance.id}',
                metadata={
                    'order_id': str(instance.id),
                    'store': str(instance.store_id),
                    'total': str(instance.total),
                }
            )

    except Exception as e:
        logger.error(f"[UnifiedUser] Error syncing StoreOrder {instance.id}: {e}")
