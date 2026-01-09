"""
Webhook Service - Process incoming webhooks from Meta.
"""
import logging
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from apps.core.utils import verify_webhook_signature, generate_idempotency_key
from apps.core.exceptions import WebhookValidationError
from ..models import WhatsAppAccount, WebhookEvent, Message
from ..repositories import WebhookEventRepository, WhatsAppAccountRepository

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for processing Meta webhooks."""

    def __init__(self):
        self.webhook_repo = WebhookEventRepository()
        self.account_repo = WhatsAppAccountRepository()

    def verify_webhook(self, mode: str, token: str, challenge: str) -> str:
        """Verify webhook subscription."""
        verify_token = settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
        
        if mode == 'subscribe' and token == verify_token:
            logger.info("Webhook verification successful")
            return challenge
        
        logger.warning(f"Webhook verification failed: mode={mode}")
        raise WebhookValidationError(message="Webhook verification failed")

    def validate_signature(self, payload: bytes, signature: str) -> bool:
        """Validate webhook signature."""
        app_secret = settings.WHATSAPP_APP_SECRET
        
        if not app_secret:
            logger.warning("WHATSAPP_APP_SECRET not configured, skipping signature validation")
            return True
        
        if not signature:
            logger.warning("No signature provided in webhook request")
            return False
        
        is_valid = verify_webhook_signature(payload, signature, app_secret)
        
        if not is_valid:
            logger.warning("Invalid webhook signature")
        
        return is_valid

    def process_webhook(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> List[WebhookEvent]:
        """Process incoming webhook payload."""
        events = []
        
        entries = payload.get('entry', [])
        
        for entry in entries:
            changes = entry.get('changes', [])
            
            for change in changes:
                if change.get('field') != 'messages':
                    continue
                
                value = change.get('value', {})
                metadata = value.get('metadata', {})
                phone_number_id = metadata.get('phone_number_id')
                
                account = self.account_repo.get_by_phone_number_id(phone_number_id)
                
                if not account:
                    logger.warning(f"Account not found for phone_number_id: {phone_number_id}")
                    continue
                
                messages = value.get('messages', [])
                for message_data in messages:
                    event = self._process_message_event(
                        account=account,
                        message_data=message_data,
                        contacts=value.get('contacts', []),
                        headers=headers
                    )
                    if event:
                        events.append(event)
                
                statuses = value.get('statuses', [])
                for status_data in statuses:
                    event = self._process_status_event(
                        account=account,
                        status_data=status_data,
                        headers=headers
                    )
                    if event:
                        events.append(event)
                
                errors = value.get('errors', [])
                for error_data in errors:
                    event = self._process_error_event(
                        account=account,
                        error_data=error_data,
                        headers=headers
                    )
                    if event:
                        events.append(event)
        
        return events

    def _process_message_event(
        self,
        account: WhatsAppAccount,
        message_data: Dict[str, Any],
        contacts: List[Dict],
        headers: Dict[str, str]
    ) -> Optional[WebhookEvent]:
        """Process a message event."""
        message_id = message_data.get('id')
        event_id = generate_idempotency_key('message', message_id)
        
        if self.webhook_repo.exists_by_event_id(event_id):
            logger.info(f"Duplicate message event: {event_id}")
            return None
        
        contact_info = {}
        if contacts:
            contact = contacts[0]
            contact_info = {
                'wa_id': contact.get('wa_id'),
                'profile': contact.get('profile', {})
            }
        
        event = self.webhook_repo.create(
            account=account,
            event_id=event_id,
            event_type=WebhookEvent.EventType.MESSAGE,
            payload={
                'message': message_data,
                'contact': contact_info
            },
            headers=headers
        )
        
        logger.info(f"Message event created: {event.id}")
        return event

    def _process_status_event(
        self,
        account: WhatsAppAccount,
        status_data: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[WebhookEvent]:
        """Process a status update event."""
        message_id = status_data.get('id')
        status = status_data.get('status')
        timestamp = status_data.get('timestamp')
        
        event_id = generate_idempotency_key('status', message_id, status, timestamp)
        
        if self.webhook_repo.exists_by_event_id(event_id):
            logger.info(f"Duplicate status event: {event_id}")
            return None
        
        event = self.webhook_repo.create(
            account=account,
            event_id=event_id,
            event_type=WebhookEvent.EventType.STATUS,
            payload=status_data,
            headers=headers
        )
        
        logger.info(f"Status event created: {event.id}")
        return event

    def _process_error_event(
        self,
        account: WhatsAppAccount,
        error_data: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[WebhookEvent]:
        """Process an error event."""
        error_code = error_data.get('code')
        error_title = error_data.get('title')
        timestamp = str(timezone.now().timestamp())
        
        event_id = generate_idempotency_key('error', error_code, timestamp)
        
        event = self.webhook_repo.create(
            account=account,
            event_id=event_id,
            event_type=WebhookEvent.EventType.ERROR,
            payload=error_data,
            headers=headers
        )
        
        logger.warning(f"Error event created: {event.id} - {error_code}: {error_title}")
        return event

    def get_pending_events(self, limit: int = 100) -> List[WebhookEvent]:
        """Get pending events for processing."""
        return list(self.webhook_repo.get_pending_events(limit))

    def get_failed_events_for_retry(
        self,
        max_retries: int = 3,
        limit: int = 100
    ) -> List[WebhookEvent]:
        """Get failed events eligible for retry."""
        return list(self.webhook_repo.get_failed_events_for_retry(max_retries, limit))

    def mark_event_processing(self, event: WebhookEvent) -> WebhookEvent:
        """Mark event as processing."""
        return self.webhook_repo.mark_as_processing(event)

    def mark_event_completed(self, event: WebhookEvent) -> WebhookEvent:
        """Mark event as completed."""
        return self.webhook_repo.mark_as_completed(event)

    def mark_event_failed(
        self,
        event: WebhookEvent,
        error_message: str
    ) -> WebhookEvent:
        """Mark event as failed."""
        return self.webhook_repo.mark_as_failed(event, error_message)

    def cleanup_old_events(self, days: int = 30) -> int:
        """Cleanup old processed events."""
        deleted = self.webhook_repo.cleanup_old_events(days)
        logger.info(f"Cleaned up {deleted} old webhook events")
        return deleted
