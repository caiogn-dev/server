"""
Instagram Webhook Handlers - Process incoming webhooks from Meta.
"""
import logging
import hmac
import hashlib
from typing import Dict, Any, Optional
from django.conf import settings

from apps.instagram.models import InstagramAccount, InstagramWebhookEvent
from apps.instagram.services.message_service import InstagramMessageService

logger = logging.getLogger(__name__)


class InstagramWebhookHandler:
    """Handler for Instagram webhook events."""
    
    def __init__(self):
        self.app_secret = getattr(settings, 'INSTAGRAM_APP_SECRET', '')
    
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify webhook signature from Meta.
        
        Args:
            payload: Raw request body bytes
            signature: X-Hub-Signature-256 header value
        
        Returns:
            True if signature is valid
        """
        if not self.app_secret:
            if getattr(settings, 'DEBUG', False):
                logger.warning("INSTAGRAM_APP_SECRET not configured, skipping signature verification in DEBUG")
                return True
            logger.error("INSTAGRAM_APP_SECRET not configured, rejecting webhook in production")
            return False
        
        if not signature:
            return False
        
        # Signature format: sha256=<hash>
        if not signature.startswith('sha256='):
            return False
        
        expected_signature = signature[7:]  # Remove 'sha256=' prefix
        
        computed_signature = hmac.new(
            self.app_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(computed_signature, expected_signature)
    
    def process_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming webhook payload.
        
        Args:
            payload: Parsed JSON webhook payload
        
        Returns:
            Processing result
        """
        results = {
            'processed': 0,
            'errors': 0,
            'events': []
        }
        
        # Instagram webhooks have 'object' = 'instagram'
        if payload.get('object') != 'instagram':
            logger.warning(f"Unexpected webhook object: {payload.get('object')}")
            return results
        
        entries = payload.get('entry', [])
        
        for entry in entries:
            account_id = entry.get('id')
            account = self._get_account(account_id)
            
            if not account:
                logger.warning(f"Account not found for ID: {account_id}")
                continue
            
            # Process messaging events
            messaging_events = entry.get('messaging', [])
            for messaging in messaging_events:
                event_result = self._process_messaging_event(account, messaging)
                results['events'].append(event_result)
                
                if event_result.get('success'):
                    results['processed'] += 1
                else:
                    results['errors'] += 1
            
            # Process changes (comments, mentions, etc)
            changes = entry.get('changes', [])
            for change in changes:
                event_result = self._process_change_event(account, change)
                results['events'].append(event_result)
                
                if event_result.get('success'):
                    results['processed'] += 1
                else:
                    results['errors'] += 1
        
        return results
    
    def _get_account(self, account_id: str) -> Optional[InstagramAccount]:
        """Get Instagram account by ID."""
        try:
            return InstagramAccount.objects.get(
                instagram_account_id=account_id,
                status=InstagramAccount.AccountStatus.ACTIVE
            )
        except InstagramAccount.DoesNotExist:
            return None
    
    def _process_messaging_event(
        self, 
        account: InstagramAccount, 
        messaging: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process a messaging event (message, read, reaction, etc)."""
        result = {
            'type': 'messaging',
            'success': False,
            'error': None
        }
        
        try:
            service = InstagramMessageService(account)
            
            # Determine event type
            if 'message' in messaging:
                # New message
                event_type = InstagramWebhookEvent.EventType.MESSAGES
                
                # Log event
                event = InstagramMessageService.log_webhook_event(
                    account=account,
                    event_type=event_type,
                    payload={'messaging': [messaging]}
                )
                
                if event.processing_status == InstagramWebhookEvent.ProcessingStatus.DUPLICATE:
                    result['success'] = True
                    result['duplicate'] = True
                    return result
                
                # Process message
                message = service.process_incoming_message({'messaging': [messaging]})
                
                if message:
                    event.related_message = message
                    event.processing_status = InstagramWebhookEvent.ProcessingStatus.COMPLETED
                else:
                    event.processing_status = InstagramWebhookEvent.ProcessingStatus.FAILED
                    event.error_message = "Failed to process message"
                
                event.save()
                result['success'] = message is not None
                result['message_id'] = message.instagram_message_id if message else None
                
            elif 'read' in messaging:
                # Message read/seen
                event_type = InstagramWebhookEvent.EventType.MESSAGING_SEEN
                service.process_message_seen({'messaging': [messaging]})
                result['success'] = True
                
            elif 'postback' in messaging:
                # Postback (button click)
                event_type = InstagramWebhookEvent.EventType.MESSAGING_POSTBACKS
                # TODO: Process postback
                result['success'] = True
                
            elif 'referral' in messaging:
                # Referral (ad click, etc)
                event_type = InstagramWebhookEvent.EventType.MESSAGING_REFERRAL
                # TODO: Process referral
                result['success'] = True
                
            else:
                result['error'] = "Unknown messaging event type"
                logger.warning(f"Unknown messaging event: {list(messaging.keys())}")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Error processing messaging event: {e}", exc_info=True)
        
        return result
    
    def _process_change_event(
        self, 
        account: InstagramAccount, 
        change: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process a change event (comments, mentions, etc)."""
        result = {
            'type': 'change',
            'field': change.get('field'),
            'success': False,
            'error': None
        }
        
        try:
            field = change.get('field')
            value = change.get('value', {})
            
            if field == 'comments':
                # New comment on a post
                event_type = InstagramWebhookEvent.EventType.COMMENTS
                # TODO: Process comment
                result['success'] = True
                
            elif field == 'mentions':
                # Mentioned in a post/story
                # TODO: Process mention
                result['success'] = True
                
            elif field == 'story_insights':
                # Story insights update
                result['success'] = True
                
            else:
                result['error'] = f"Unhandled change field: {field}"
                logger.info(f"Unhandled change event field: {field}")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Error processing change event: {e}", exc_info=True)
        
        return result
