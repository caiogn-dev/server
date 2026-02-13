from celery import shared_task
import logging
from datetime import datetime, timedelta
from django.utils import timezone

from .models import MessengerBroadcast, MessengerSponsoredMessage, MessengerMessage, MessengerConversation
from .services import MessengerService, MessengerPlatformService, MessengerBroadcastService

logger = logging.getLogger(__name__)


@shared_task
def send_scheduled_broadcasts():
    """Envia broadcasts agendados"""
    now = timezone.now()
    
    broadcasts = MessengerBroadcast.objects.filter(
        status='SCHEDULED',
        scheduled_at__lte=now
    )
    
    for broadcast in broadcasts:
        try:
            messenger = MessengerService(broadcast.account)
            broadcast_service = MessengerBroadcastService(messenger)
            
            broadcast_service.send_broadcast(str(broadcast.id))
            logger.info(f"Broadcast {broadcast.id} sent successfully")
            
        except Exception as e:
            broadcast.status = 'FAILED'
            broadcast.save()
            logger.error(f"Error sending broadcast {broadcast.id}: {e}")


@shared_task
def update_messenger_accounts():
    """Atualiza informações de páginas do Messenger"""
    from .models import MessengerAccount
    
    accounts = MessengerAccount.objects.filter(is_active=True)
    
    for account in accounts:
        try:
            messenger = MessengerService(account)
            platform = MessengerPlatformService(messenger)
            
            # Obtém informações da página
            page_info = messenger.get(account.page_id)
            account.page_name = page_info.get('name', account.page_name)
            account.category = page_info.get('category', '')
            account.followers_count = page_info.get('followers_count', 0)
            account.last_sync_at = timezone.now()
            account.save()
            
            logger.info(f"Account {account.page_name} updated")
        except Exception as e:
            logger.error(f"Error updating account {account.page_name}: {e}")


@shared_task
def process_messenger_webhook(payload: dict):
    """Processa webhook do Messenger"""
    from .models import MessengerWebhookLog, MessengerAccount
    
    try:
        # Cria log
        log = MessengerWebhookLog.objects.create(
            object_type=payload.get('object'),
            payload=payload
        )
        
        # Processa mensagens
        for entry in payload.get('entry', []):
            page_id = entry.get('id')
            
            try:
                account = MessengerAccount.objects.get(page_id=page_id)
            except MessengerAccount.DoesNotExist:
                logger.warning(f"Account not found for page {page_id}")
                continue
            
            messenger = MessengerService(account)
            platform = MessengerPlatformService(messenger)
            
            for messaging_event in entry.get('messaging', []):
                sender_id = messaging_event.get('sender', {}).get('id')
                
                # Obtém ou cria conversa
                conversation = platform.get_or_create_conversation(sender_id)
                
                # Processa mensagem
                if 'message' in messaging_event:
                    message_data = messaging_event['message']
                    
                    # Atualiza contador de mensagens não lidas
                    if not message_data.get('is_echo', False):
                        conversation.unread_count += 1
                        conversation.save()
                        
                        # Cria mensagem
                        MessengerMessage.objects.create(
                            conversation=conversation,
                            messenger_message_id=message_data.get('mid'),
                            message_type='TEXT' if 'text' in message_data else 'ATTACHMENT',
                            content=message_data.get('text', ''),
                            attachment_url=message_data.get('attachments', [{}])[0].get('payload', {}).get('url'),
                            is_from_page=message_data.get('is_echo', False)
                        )
                
                # Processa delivery
                elif 'delivery' in messaging_event:
                    delivery = messaging_event['delivery']
                    for mid in delivery.get('mids', []):
                        MessengerMessage.objects.filter(
                            messenger_message_id=mid
                        ).update(
                            delivered_at=timezone.now()
                        )
                
                # Processa leitura
                elif 'read' in messaging_event:
                    read = messaging_event['read']
                    conversation.messages.filter(
                        is_from_page=True,
                        is_read=False
                    ).update(
                        is_read=True,
                        read_at=timezone.now()
                    )
                
                # Processa postback
                elif 'postback' in messaging_event:
                    postback = messaging_event['postback']
                    MessengerMessage.objects.create(
                        conversation=conversation,
                        message_type='POSTBACK',
                        content=postback.get('payload', ''),
                        is_from_page=False
                    )
        
        log.is_processed = True
        log.processed_at = timezone.now()
        log.save()
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")


@shared_task
def cleanup_old_messenger_logs():
    """Limpa logs antigos do Messenger"""
    from .models import MessengerWebhookLog
    
    threshold = timezone.now() - timedelta(days=30)
    deleted_count, _ = MessengerWebhookLog.objects.filter(
        created_at__lt=threshold
    ).delete()
    
    logger.info(f"Deleted {deleted_count} old messenger webhook logs")


@shared_task
def sync_messenger_insights():
    """Sincroniza métricas de broadcasts e sponsored messages"""
    # Atualiza métricas de broadcasts em andamento
    active_broadcasts = MessengerBroadcast.objects.filter(
        status__in=['PROCESSING', 'COMPLETED']
    )
    
    for broadcast in active_broadcasts:
        try:
            # Aqui seria feita a atualização real das métricas
            # via API do Facebook
            pass
        except Exception as e:
            logger.error(f"Error syncing insights for broadcast {broadcast.id}: {e}")
    
    # Atualiza métricas de sponsored messages ativas
    active_sponsored = MessengerSponsoredMessage.objects.filter(
        status='ACTIVE'
    )
    
    for sponsored in active_sponsored:
        try:
            # Aqui seria feita a atualização real via Facebook Marketing API
            pass
        except Exception as e:
            logger.error(f"Error syncing insights for sponsored {sponsored.id}: {e}")