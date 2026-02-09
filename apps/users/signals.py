"""
Signals para sincronização automática de UnifiedUser.

NÃO ALTERA modelos existentes - apenas cria/atualiza UnifiedUser.
"""
import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

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
        # Busca ou cria UnifiedUser
        user, user_created = UnifiedUser.objects.get_or_create(
            phone_number=instance.phone_number,
            defaults={
                'name': instance.contact_name or 'Desconhecido',
            }
        )
        
        # Atualiza nome se necessário
        if instance.contact_name and not user.name:
            user.name = instance.contact_name
            user.save(update_fields=['name'])
        
        # Log da atividade
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
    """
    Registra atividade quando mensagem é recebida.
    """
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
            
            # Atualiza last_seen
            user.save(update_fields=['last_seen_at'])
            
    except Exception as e:
        logger.error(f"[UnifiedUser] Error logging message activity: {e}")


# TODO: Adicionar signals para pedidos do site
# @receiver(post_save, sender='orders.Order')
# def sync_order_to_unified_user(sender, instance, created, **kwargs):
#     """Quando um pedido é criado, atualiza UnifiedUser."""
#     pass
