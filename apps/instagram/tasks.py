from celery import shared_task
import logging
from datetime import datetime, timedelta
from django.utils import timezone

from .models import InstagramScheduledPost, InstagramMedia, InstagramAccount
from .services import InstagramAPI, InstagramGraphService

logger = logging.getLogger(__name__)


@shared_task
def publish_scheduled_posts():
    """Task para publicar posts agendados"""
    now = timezone.now()
    
    # Busca posts que devem ser publicados
    posts = InstagramScheduledPost.objects.filter(
        status='PENDING',
        schedule_time__lte=now
    )
    
    for post in posts:
        try:
            post.status = 'PROCESSING'
            post.save()
            
            # Cria API e serviço
            api = InstagramAPI(post.account)
            graph_service = InstagramGraphService(api)
            
            # Publica a mídia
            result = graph_service.publish_media(
                post.media_type,
                post.media_files[0] if post.media_files else None,
                post.caption
            )
            
            # Atualiza status
            post.status = 'PUBLISHED'
            post.instagram_media_id = result.get('id')
            post.published_at = timezone.now()
            post.save()
            
            # Cria registro de mídia
            InstagramMedia.objects.create(
                account=post.account,
                instagram_media_id=result.get('id'),
                media_type=post.media_type,
                caption=post.caption,
                status='PUBLISHED',
                published_at=timezone.now()
            )
            
            logger.info(f"Scheduled post {post.id} published successfully")
            
        except Exception as e:
            post.status = 'FAILED'
            post.error_message = str(e)
            post.save()
            logger.error(f"Error publishing scheduled post {post.id}: {e}")


@shared_task
def sync_instagram_accounts():
    """Sincroniza informações de todas as contas ativas"""
    accounts = InstagramAccount.objects.filter(is_active=True)
    
    for account in accounts:
        try:
            api = InstagramAPI(account)
            api.sync_account_info()
            logger.info(f"Account {account.username} synced successfully")
        except Exception as e:
            logger.error(f"Error syncing account {account.username}: {e}")


@shared_task
def refresh_instagram_tokens():
    """Renova tokens que estão próximos de expirar"""
    # Tokens que expiram em menos de 7 dias
    expiration_threshold = timezone.now() + timedelta(days=7)
    
    accounts = InstagramAccount.objects.filter(
        is_active=True,
        token_expires_at__lte=expiration_threshold
    )
    
    for account in accounts:
        try:
            api = InstagramAPI(account)
            if api.refresh_token():
                logger.info(f"Token refreshed for {account.username}")
            else:
                logger.warning(f"Failed to refresh token for {account.username}")
        except Exception as e:
            logger.error(f"Error refreshing token for {account.username}: {e}")


@shared_task
def sync_instagram_insights():
    """Sincroniza insights de contas"""
    yesterday = timezone.now() - timedelta(days=1)
    
    accounts = InstagramAccount.objects.filter(is_active=True)
    
    for account in accounts:
        try:
            api = InstagramAPI(account)
            graph_service = InstagramGraphService(api)
            
            graph_service.sync_insights(yesterday, yesterday)
            logger.info(f"Insights synced for {account.username}")
        except Exception as e:
            logger.error(f"Error syncing insights for {account.username}: {e}")


@shared_task
def cleanup_old_webhook_logs():
    """Limpa logs de webhooks antigos (mais de 30 dias)"""
    from .models import InstagramWebhookLog
    
    threshold = timezone.now() - timedelta(days=30)
    deleted_count, _ = InstagramWebhookLog.objects.filter(
        created_at__lt=threshold
    ).delete()
    
    logger.info(f"Deleted {deleted_count} old webhook logs")


@shared_task
def process_instagram_webhook(payload: dict):
    """Processa payload de webhook do Instagram"""
    from .models import InstagramWebhookLog, InstagramConversation, InstagramMessage
    from .services import InstagramDirectService, InstagramAPI
    
    try:
        # Cria log
        log = InstagramWebhookLog.objects.create(
            object_type=payload.get('object'),
            field=payload.get('entry', [{}])[0].get('changes', [{}])[0].get('field'),
            payload=payload
        )
        
        # Processa mensagens
        for entry in payload.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value', {})
                
                if change.get('field') == 'messages':
                    # Processa mensagem
                    sender_id = value.get('sender', {}).get('id')
                    recipient_id = value.get('recipient', {}).get('id')
                    message_data = value.get('message', {})
                    
                    # Encontra a conta
                    try:
                        account = InstagramAccount.objects.get(
                            instagram_business_id=recipient_id
                        )
                        
                        # Cria ou obtém conversa
                        api = InstagramAPI(account)
                        direct_service = InstagramDirectService(api)
                        
                        conversation = direct_service.get_or_create_conversation(
                            participant_id=sender_id,
                            participant_username=value.get('sender', {}).get('username', ''),
                        )
                        
                        # Cria mensagem
                        direct_service.receive_message(
                            conversation=conversation,
                            instagram_message_id=message_data.get('mid'),
                            message_type=message_data.get('attachments', [{}])[0].get('type', 'TEXT').upper() if message_data.get('attachments') else 'TEXT',
                            content=message_data.get('text', ''),
                        )
                        
                    except InstagramAccount.DoesNotExist:
                        logger.warning(f"Account not found for recipient {recipient_id}")
        
        log.is_processed = True
        log.processed_at = timezone.now()
        log.save()
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")