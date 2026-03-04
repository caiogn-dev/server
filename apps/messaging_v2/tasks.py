"""
Celery tasks para messaging_v2 - Processamento assíncrono.
"""
import requests
import json
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.utils import timezone


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_whatsapp_message(self, message_id):
    """Enviar mensagem WhatsApp via API."""
    from apps.messaging_v2.models import UnifiedMessage, PlatformAccount
    
    try:
        message = UnifiedMessage.objects.select_related('conversation').get(id=message_id)
        conversation = message.conversation
        
        # Buscar conta WhatsApp ativa
        account = PlatformAccount.objects.filter(
            platform='whatsapp',
            is_active=True
        ).first()
        
        if not account:
            message.status = UnifiedMessage.Status.FAILED
            message.save(update_fields=['status'])
            return {'error': 'No WhatsApp account configured'}
        
        # Preparar payload para API WhatsApp
        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': conversation.customer_phone,
            'type': 'text',
            'text': {'body': message.text}
        }
        
        # Enviar para API WhatsApp Business
        headers = {
            'Authorization': f'Bearer {account.access_token}',
            'Content-Type': 'application/json'
        }
        
        # Usar phone_number_id da conta
        phone_number_id = account.external_id or account.phone_number
        url = f'https://graph.facebook.com/v18.0/{phone_number_id}/messages'
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response_data = response.json()
        
        if response.status_code == 200:
            message.external_id = response_data.get('messages', [{}])[0].get('id')
            message.status = UnifiedMessage.Status.SENT
            message.sent_at = timezone.now()
            message.save(update_fields=['external_id', 'status', 'sent_at'])
            
            # Broadcast status update via WebSocket
            broadcast_message_status.delay(message_id, 'sent')
            
            return {'success': True, 'message_id': message.external_id}
        else:
            error_msg = response_data.get('error', {}).get('message', 'Unknown error')
            raise self.retry(exc=Exception(error_msg))
            
    except UnifiedMessage.DoesNotExist:
        return {'error': 'Message not found'}
    except MaxRetriesExceededError:
        message.status = UnifiedMessage.Status.FAILED
        message.save(update_fields=['status'])
        return {'error': 'Max retries exceeded'}
    except Exception as e:
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_webhook_event(self, platform, event_data):
    """Processar evento de webhook de forma assíncrona."""
    from apps.messaging_v2.models import Conversation, UnifiedMessage, PlatformAccount
    
    try:
        if platform == 'whatsapp':
            return _process_whatsapp_webhook(event_data)
        elif platform == 'instagram':
            return _process_instagram_webhook(event_data)
        else:
            return {'error': f'Unknown platform: {platform}'}
    except Exception as e:
        raise self.retry(exc=e)


def _process_whatsapp_webhook(event_data):
    """Processar webhook específico do WhatsApp."""
    from apps.messaging_v2.models import Conversation, UnifiedMessage, PlatformAccount
    from apps.commerce.models import Store
    
    entries = event_data.get('entry', [])
    
    for entry in entries:
        changes = entry.get('changes', [])
        
        for change in changes:
            value = change.get('value', {})
            messages = value.get('messages', [])
            statuses = value.get('statuses', [])
            
            # Processar mensagens recebidas
            for msg in messages:
                phone_number = msg.get('from')
                message_text = msg.get('text', {}).get('body', '')
                message_id = msg.get('id')
                timestamp = msg.get('timestamp')
                
                # Buscar ou criar conversa
                conversation, created = Conversation.objects.get_or_create(
                    customer_phone=phone_number,
                    defaults={
                        'customer_name': msg.get('profile', {}).get('name', ''),
                        'platform': 'whatsapp',
                        'store': Store.objects.first()  # Associar à primeira store
                    }
                )
                
                # Criar mensagem
                UnifiedMessage.objects.create(
                    conversation=conversation,
                    direction=UnifiedMessage.Direction.INBOUND,
                    status=UnifiedMessage.Status.DELIVERED,
                    text=message_text,
                    external_id=message_id,
                    created_at=timezone.datetime.fromtimestamp(int(timestamp))
                )
                
                # Atualizar timestamp da conversa
                conversation.last_message_at = timezone.now()
                conversation.save(update_fields=['last_message_at'])
                
                # Broadcast via WebSocket
                broadcast_new_message.delay(conversation.id, message_text)
            
            # Processar atualizações de status
            for status in statuses:
                message_id = status.get('id')
                status_value = status.get('status')
                
                try:
                    message = UnifiedMessage.objects.get(external_id=message_id)
                    
                    if status_value == 'delivered':
                        message.status = UnifiedMessage.Status.DELIVERED
                        message.delivered_at = timezone.now()
                    elif status_value == 'read':
                        message.status = UnifiedMessage.Status.READ
                        message.read_at = timezone.now()
                    
                    message.save(update_fields=['status', 'delivered_at', 'read_at'])
                    
                    # Broadcast status
                    broadcast_message_status.delay(message.id, status_value)
                    
                except UnifiedMessage.DoesNotExist:
                    pass
    
    return {'processed': True}


def _process_instagram_webhook(event_data):
    """Processar webhook do Instagram."""
    # Implementação similar para Instagram
    return {'processed': True, 'platform': 'instagram'}


@shared_task
def broadcast_new_message(conversation_id, message_text):
    """Broadcast nova mensagem via Channel Layer."""
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    from apps.messaging_v2.models import Conversation
    
    try:
        conversation = Conversation.objects.select_related('store').get(id=conversation_id)
        channel_layer = get_channel_layer()
        
        async_to_sync(channel_layer.group_send)(
            f'conversations_{conversation.store.slug}',
            {
                'type': 'conversation_message',
                'message': {
                    'conversation_id': str(conversation_id),
                    'text': message_text,
                    'customer_phone': conversation.customer_phone,
                    'timestamp': timezone.now().isoformat()
                }
            }
        )
    except Exception as e:
        print(f"[BROADCAST] Error: {e}")


@shared_task
def broadcast_message_status(message_id, status):
    """Broadcast atualização de status via Channel Layer."""
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    from apps.messaging_v2.models import UnifiedMessage
    
    try:
        message = UnifiedMessage.objects.select_related('conversation__store').get(id=message_id)
        channel_layer = get_channel_layer()
        
        async_to_sync(channel_layer.group_send)(
            f'conversations_{message.conversation.store.slug}',
            {
                'type': 'message_status_update',
                'message_id': str(message_id),
                'status': status
            }
        )
    except Exception as e:
        print(f"[BROADCAST] Error: {e}")


@shared_task
def sync_whatsapp_templates(account_id):
    """Sincronizar templates do WhatsApp Business API."""
    from apps.messaging_v2.models import PlatformAccount, MessageTemplate
    
    try:
        account = PlatformAccount.objects.get(id=account_id, platform='whatsapp')
        
        headers = {
            'Authorization': f'Bearer {account.access_token}',
            'Content-Type': 'application/json'
        }
        
        business_id = account.external_id
        url = f'https://graph.facebook.com/v18.0/{business_id}/message_templates'
        
        response = requests.get(url, headers=headers, timeout=30)
        data = response.json()
        
        if response.status_code == 200:
            templates = data.get('data', [])
            
            for template_data in templates:
                MessageTemplate.objects.update_or_create(
                    external_id=template_data['id'],
                    defaults={
                        'name': template_data['name'],
                        'category': template_data.get('category', 'UTILITY'),
                        'language': template_data.get('language', 'pt_BR'),
                        'status': template_data.get('status', 'PENDING').lower(),
                        'body': json.dumps(template_data.get('components', []))
                    }
                )
            
            return {'synced': len(templates)}
        
        return {'error': data.get('error', {}).get('message', 'Unknown error')}
        
    except PlatformAccount.DoesNotExist:
        return {'error': 'Account not found'}
    except Exception as e:
        return {'error': str(e)}
