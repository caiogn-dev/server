"""
Celery tasks for Instagram Messaging app.
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='apps.instagram.tasks.cleanup_old_webhook_events')
def cleanup_old_webhook_events():
    """
    Clean up webhook events older than 30 days.
    """
    from .models import InstagramWebhookEvent
    
    cutoff_date = timezone.now() - timedelta(days=30)
    deleted_count, _ = InstagramWebhookEvent.objects.filter(
        created_at__lt=cutoff_date,
        processed=True
    ).delete()
    
    logger.info(f"[Instagram] Cleaned up {deleted_count} old webhook events")
    return deleted_count


@shared_task(name='apps.instagram.tasks.send_message_async')
def send_message_async(account_id: str, recipient_id: str, message_type: str, content: dict):
    """
    Send a message asynchronously via Instagram Messaging API.
    
    Args:
        account_id: UUID of the Instagram account
        recipient_id: Instagram-scoped user ID (IGSID)
        message_type: Type of message (text, image, video, quick_replies, generic_template)
        content: Message content dict
    """
    from .models import InstagramAccount, InstagramMessage, InstagramConversation
    from .services.instagram_api_service import InstagramAPIService
    
    try:
        account = InstagramAccount.objects.get(id=account_id)
        api_service = InstagramAPIService(account)
        
        # Get or create conversation
        conversation, _ = InstagramConversation.objects.get_or_create(
            account=account,
            participant_id=recipient_id,
            defaults={
                'participant_username': content.get('participant_username', ''),
            }
        )
        
        # Send based on message type
        if message_type == 'text':
            result = api_service.send_text_message(recipient_id, content.get('text', ''))
        elif message_type == 'image':
            result = api_service.send_image(recipient_id, content.get('image_url', ''))
        elif message_type == 'video':
            result = api_service.send_video(recipient_id, content.get('video_url', ''))
        elif message_type == 'audio':
            result = api_service.send_audio(recipient_id, content.get('audio_url', ''))
        elif message_type == 'quick_replies':
            result = api_service.send_quick_replies(
                recipient_id, 
                content.get('text', ''), 
                content.get('quick_replies', [])
            )
        elif message_type == 'generic_template':
            result = api_service.send_generic_template(
                recipient_id, 
                content.get('elements', [])
            )
        else:
            raise ValueError(f"Unknown message type: {message_type}")
        
        # Create message record
        message = InstagramMessage.objects.create(
            account=account,
            conversation=conversation,
            ig_message_id=result.get('message_id', ''),
            direction=InstagramMessage.MessageDirection.OUTBOUND,
            message_type=message_type,
            text_content=content.get('text', ''),
            media_url=content.get('image_url') or content.get('video_url') or content.get('audio_url', ''),
            status=InstagramMessage.MessageStatus.SENT,
            sent_at=timezone.now(),
        )
        
        # Update conversation
        conversation.last_message_at = timezone.now()
        conversation.save(update_fields=['last_message_at', 'updated_at'])
        
        logger.info(f"[Instagram] Message sent successfully: {message.id}")
        return {'success': True, 'message_id': str(message.id)}
        
    except InstagramAccount.DoesNotExist:
        logger.error(f"[Instagram] Account not found: {account_id}")
        return {'success': False, 'error': 'Account not found'}
    except Exception as e:
        logger.error(f"[Instagram] Failed to send message: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(name='apps.instagram.tasks.process_webhook_event')
def process_webhook_event(event_id: str):
    """
    Process a webhook event asynchronously.
    
    Args:
        event_id: UUID of the InstagramWebhookEvent to process
    """
    from .models import InstagramWebhookEvent
    from .services.message_service import InstagramMessageService
    
    try:
        event = InstagramWebhookEvent.objects.get(id=event_id)
        
        if event.processed:
            logger.info(f"[Instagram] Event already processed: {event_id}")
            return {'success': True, 'skipped': True}
        
        # Process based on event type
        service = InstagramMessageService()
        payload = event.payload
        
        if event.event_type == 'message':
            service.process_incoming_message(event.account, payload)
        elif event.event_type == 'read':
            service.process_message_read(event.account, payload)
        elif event.event_type == 'postback':
            service.process_postback(event.account, payload)
        elif event.event_type == 'referral':
            service.process_referral(event.account, payload)
        
        # Mark as processed
        event.processed = True
        event.processed_at = timezone.now()
        event.save(update_fields=['processed', 'processed_at'])
        
        logger.info(f"[Instagram] Event processed: {event_id}")
        return {'success': True}
        
    except InstagramWebhookEvent.DoesNotExist:
        logger.error(f"[Instagram] Event not found: {event_id}")
        return {'success': False, 'error': 'Event not found'}
    except Exception as e:
        logger.error(f"[Instagram] Failed to process event: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(name='apps.instagram.tasks.refresh_token_if_needed')
def refresh_token_if_needed():
    """
    Check all Instagram accounts and refresh tokens expiring within 7 days.
    """
    from .models import InstagramAccount
    from .services.instagram_api_service import InstagramAPIService
    
    # Find accounts with tokens expiring within 7 days
    expiry_threshold = timezone.now() + timedelta(days=7)
    accounts = InstagramAccount.objects.filter(
        is_active=True,
        token_expires_at__lt=expiry_threshold,
        token_expires_at__gt=timezone.now()
    )
    
    refreshed = 0
    failed = 0
    
    for account in accounts:
        try:
            api_service = InstagramAPIService(account)
            new_token_data = api_service.refresh_long_lived_token()
            
            if new_token_data:
                account.access_token = new_token_data.get('access_token', '')
                account.token_expires_at = timezone.now() + timedelta(
                    seconds=new_token_data.get('expires_in', 5184000)
                )
                account.save(update_fields=['access_token', 'token_expires_at', 'updated_at'])
                refreshed += 1
                logger.info(f"[Instagram] Token refreshed for account: {account.id}")
        except Exception as e:
            failed += 1
            logger.error(f"[Instagram] Failed to refresh token for {account.id}: {e}")
    
    logger.info(f"[Instagram] Token refresh complete: {refreshed} refreshed, {failed} failed")
    return {'refreshed': refreshed, 'failed': failed}


@shared_task(name='apps.instagram.tasks.sync_conversations')
def sync_conversations(account_id: str):
    """
    Sync conversations for an Instagram account.
    
    Args:
        account_id: UUID of the Instagram account
    """
    from .models import InstagramAccount
    from .services.instagram_api_service import InstagramAPIService
    from .services.message_service import InstagramMessageService
    
    try:
        account = InstagramAccount.objects.get(id=account_id)
        api_service = InstagramAPIService(account)
        message_service = InstagramMessageService()
        
        # Get conversations from API
        conversations_data = api_service.get_conversations(limit=50)
        
        synced = 0
        for conv_data in conversations_data.get('data', []):
            try:
                message_service.sync_conversation(account, conv_data)
                synced += 1
            except Exception as e:
                logger.warning(f"[Instagram] Failed to sync conversation: {e}")
        
        logger.info(f"[Instagram] Synced {synced} conversations for account {account_id}")
        return {'synced': synced}
        
    except InstagramAccount.DoesNotExist:
        logger.error(f"[Instagram] Account not found: {account_id}")
        return {'success': False, 'error': 'Account not found'}
    except Exception as e:
        logger.error(f"[Instagram] Failed to sync conversations: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(name='apps.instagram.tasks.mark_message_seen')
def mark_message_seen(account_id: str, recipient_id: str):
    """
    Mark messages as seen asynchronously.
    
    Args:
        account_id: UUID of the Instagram account
        recipient_id: Instagram-scoped user ID
    """
    from .models import InstagramAccount
    from .services.instagram_api_service import InstagramAPIService
    
    try:
        account = InstagramAccount.objects.get(id=account_id)
        api_service = InstagramAPIService(account)
        api_service.mark_seen(recipient_id)
        
        logger.info(f"[Instagram] Marked messages seen for {recipient_id}")
        return {'success': True}
        
    except InstagramAccount.DoesNotExist:
        logger.error(f"[Instagram] Account not found: {account_id}")
        return {'success': False, 'error': 'Account not found'}
    except Exception as e:
        logger.error(f"[Instagram] Failed to mark seen: {e}")
        return {'success': False, 'error': str(e)}


@shared_task(name='apps.instagram.tasks.send_typing_indicator')
def send_typing_indicator(account_id: str, recipient_id: str):
    """
    Send typing indicator asynchronously.
    
    Args:
        account_id: UUID of the Instagram account
        recipient_id: Instagram-scoped user ID
    """
    from .models import InstagramAccount
    from .services.instagram_api_service import InstagramAPIService
    
    try:
        account = InstagramAccount.objects.get(id=account_id)
        api_service = InstagramAPIService(account)
        api_service.send_typing_indicator(recipient_id)
        
        return {'success': True}
        
    except InstagramAccount.DoesNotExist:
        return {'success': False, 'error': 'Account not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@shared_task(name='apps.instagram.tasks.refresh_access_tokens')
def refresh_access_tokens():
    """
    Refresh Instagram/Facebook Page Access Tokens for all active accounts.
    Should be run daily via Celery Beat.
    """
    from .models import InstagramAccount
    import requests
    
    accounts = InstagramAccount.objects.filter(status='active')
    refreshed = 0
    errors = 0
    
    for account in accounts:
        if not account.app_id or not account.app_secret:
            logger.warning(f"Skipping token refresh for {account.username}: No app credentials")
            continue
        
        try:
            # Exchange current token for new long-lived token
            response = requests.get(
                "https://graph.facebook.com/v21.0/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": account.app_id,
                    "client_secret": account.app_secret,
                    "fb_exchange_token": account.access_token
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                new_token = data.get('access_token')
                
                if new_token:
                    account.access_token = new_token
                    account.save(update_fields=['access_token', 'updated_at'])
                    refreshed += 1
                    
                    expires_in_days = data.get('expires_in', 0) // 86400
                    logger.info(f"Instagram token refreshed for {account.username}", extra={
                        'account_id': account.id,
                        'expires_in_days': expires_in_days
                    })
            else:
                errors += 1
                error = response.json().get('error', {})
                logger.error(f"Failed to refresh token for {account.username}: {error.get('message')}", extra={
                    'account_id': account.id,
                    'error_code': error.get('code')
                })
                
        except Exception as e:
            errors += 1
            logger.error(f"Exception refreshing token for {account.username}: {e}", exc_info=True, extra={
                'account_id': account.id
            })
    
    logger.info(f"Instagram token refresh completed: {refreshed} refreshed, {errors} errors")
    return {'refreshed': refreshed, 'errors': errors}
