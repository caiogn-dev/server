"""
Webhook Service - Process incoming webhooks from Meta.
"""
import logging
import hashlib
import mimetypes
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from django.db import IntegrityError
from django.db.models import Q
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from django.db import transaction
from celery import current_app
from apps.core.utils import (
    verify_webhook_signature,
    generate_idempotency_key,
    normalize_phone_number,
    build_absolute_media_url
)
from apps.core.exceptions import WebhookValidationError
from ..models import WhatsAppAccount, WebhookEvent, Message
from ..repositories import WebhookEventRepository, WhatsAppAccountRepository
from .broadcast_service import get_broadcast_service
from .whatsapp_api_service import WhatsAppAPIService

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for processing Meta webhooks."""

    def __init__(self):
        self.webhook_repo = WebhookEventRepository()
        self.account_repo = WhatsAppAccountRepository()
        self.broadcast = get_broadcast_service()

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
            waba_id = entry.get('id')
            
            for change in changes:
                if change.get('field') != 'messages':
                    continue
                
                value = change.get('value', {})
                metadata = value.get('metadata', {})
                phone_number_id = metadata.get('phone_number_id')
                display_phone = metadata.get('display_phone_number')
                
                account = self._resolve_account(
                    phone_number_id=phone_number_id,
                    display_phone=display_phone,
                    waba_id=waba_id
                )
                
                if not account:
                    logger.warning(
                        "Account not found for webhook event",
                        extra={
                            'phone_number_id': phone_number_id,
                            'display_phone': display_phone,
                            'waba_id': waba_id,
                        }
                    )
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

    def _resolve_account(
        self,
        phone_number_id: Optional[str],
        display_phone: Optional[str],
        waba_id: Optional[str]
    ) -> Optional[WhatsAppAccount]:
        """Resolve WhatsApp account from webhook metadata with fallbacks."""
        account = None
        
        if phone_number_id:
            account = self.account_repo.get_by_phone_number_id(phone_number_id)
        
        if not account and display_phone:
            normalized = normalize_phone_number(display_phone)
            if normalized:
                account = WhatsAppAccount.objects.filter(
                    is_active=True
                ).filter(
                    Q(display_phone_number__icontains=normalized) |
                    Q(phone_number__icontains=normalized)
                ).first()
        
        if not account and waba_id:
            account = WhatsAppAccount.objects.filter(
                is_active=True,
                waba_id=waba_id
            ).first()
        
        # If we found an account but phone_number_id has changed, update it
        if account and phone_number_id and account.phone_number_id != phone_number_id:
            try:
                account.phone_number_id = phone_number_id
                if display_phone and not account.display_phone_number:
                    account.display_phone_number = display_phone
                account.save(update_fields=['phone_number_id', 'display_phone_number', 'updated_at'])
                logger.warning(
                    f"Updated account phone_number_id from webhook: account={account.id}"
                )
            except IntegrityError:
                logger.error(
                    "Failed to update phone_number_id (unique conflict)",
                    extra={'account_id': str(account.id), 'phone_number_id': phone_number_id}
                )
        
        return account

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

    @transaction.atomic
    def process_event(self, event: WebhookEvent, post_process_inbound: bool = False) -> Optional[Message]:
        """
        Process a webhook event and broadcast updates.
        
        This is called by the Celery task after the event is saved.
        It handles:
        - MESSAGE events: Create/update Message record, broadcast to clients
        - STATUS events: Update message status, broadcast to clients
        - ERROR events: Log error, broadcast to clients
        
        Args:
            event: WebhookEvent to process
            
        Returns:
            Message object if a message was created/updated, None otherwise
        """
        try:
            self.mark_event_processing(event)
            
            if event.event_type == WebhookEvent.EventType.MESSAGE:
                message = self._process_inbound_message(event)
                if post_process_inbound and message:
                    self.post_process_inbound_message(event, message)
                self.mark_event_completed(event)
                return message
            
            elif event.event_type == WebhookEvent.EventType.STATUS:
                message = self._process_status_update(event)
                self.mark_event_completed(event)
                return message
            
            elif event.event_type == WebhookEvent.EventType.ERROR:
                self._process_error(event)
                self.mark_event_completed(event)
                return None
            
            else:
                logger.warning(f"Unknown event type: {event.event_type}")
                self.mark_event_completed(event)
                return None
                
        except Exception as e:
            logger.error(f"Error processing event {event.id}: {e}", exc_info=True)
            self.mark_event_failed(event, str(e))
            raise

    def post_process_inbound_message(self, event: WebhookEvent, message: Message) -> None:
        """
        Processa mensagem recebida com múltiplos níveis de fallback.
        
        Ordem de prioridade:
        1. WhatsAppAutomationService (novo sistema com Intent Detection)
        2. AutomationService (sistema antigo como fallback)
        3. AI Agent (último recurso)
        """
        from apps.conversations.services import ConversationService

        payload = event.payload
        message_data = payload.get('message', {})
        contact_info = payload.get('contact', {})

        # Ensure conversation exists
        if not message.conversation:
            try:
                conversation_service = ConversationService()
                conversation = conversation_service.get_or_create_conversation(
                    account=event.account,
                    phone_number=message.from_number,
                    contact_name=contact_info.get('profile', {}).get('name', '')
                )
                message.conversation = conversation
                message.save(update_fields=['conversation'])
            except Exception as e:
                logger.error(f"[post_process] Failed to create conversation: {e}")

        # Update contact name if missing
        try:
            contact_name = contact_info.get('profile', {}).get('name', '')
            if message.conversation and contact_name and not message.conversation.contact_name:
                message.conversation.contact_name = contact_name
                message.conversation.save(update_fields=['contact_name', 'updated_at'])

            # Extract name from message
            if message.conversation and message.text_body and not message.conversation.contact_name:
                extracted_name = self._extract_name_from_message(message.text_body)
                if extracted_name:
                    message.conversation.contact_name = extracted_name
                    message.conversation.save(update_fields=['contact_name', 'updated_at'])
                    logger.info(f"[post_process] Extracted name: {extracted_name}")
        except Exception as e:
            logger.warning(f"[post_process] Error updating contact name: {e}")

        # ========== NÍVEL 1: WhatsAppAutomationService (novo sistema) ==========
        intent_response = None
        intent_error = None
        
        try:
            import threading
            from apps.whatsapp.services import WhatsAppAutomationService
            
            def run_intent_automation():
                nonlocal intent_response, intent_error
                try:
                    service = WhatsAppAutomationService(
                        account=event.account,
                        conversation=message.conversation,
                        use_llm=True,
                        enable_interactive=True,
                        debug=False
                    )
                    intent_response = service.process_message(message.text_body or '')
                    logger.info(f"[IntentAutomation] Response: {intent_response}")
                except Exception as e:
                    intent_error = e
                    logger.warning(f"[IntentAutomation] Error: {e}")
            
            thread = threading.Thread(target=run_intent_automation)
            thread.start()
            thread.join(timeout=8)
            
            if thread.is_alive():
                logger.warning("[IntentAutomation] Timeout")
                intent_error = TimeoutError("Intent automation timeout")
            
            # Se obteve resposta válida (não None e não comandos internos)
            if intent_response and intent_response not in ['BUTTONS_SENT', 'LIST_SENT', 'INTERACTIVE_SENT', None]:
                logger.info(f"[IntentAutomation] Sending response: {intent_response[:50]}...")
                try:
                    from ..tasks import send_agent_response
                    send_agent_response.delay(
                        str(event.account.id),
                        message.from_number,
                        intent_response,
                        str(message.whatsapp_message_id)
                    )
                    logger.info("[IntentAutomation] Response queued successfully")
                    return  # Sucesso! Mensagem processada.
                except Exception as e:
                    logger.error(f"[IntentAutomation] Failed to queue response: {e}")
                    # Continua para fallback
                    
        except ImportError as e:
            logger.warning(f"[IntentAutomation] Import error (module not ready): {e}")
        except Exception as e:
            logger.warning(f"[IntentAutomation] Unexpected error: {e}")

        # ========== NÍVEL 2: AutomationService (sistema antigo como fallback) ==========
        try:
            from apps.automation.services import AutomationService
            
            automation_response = None
            automation_error = None
            
            def run_automation():
                nonlocal automation_response, automation_error
                try:
                    automation_service = AutomationService()
                    automation_response = automation_service.handle_incoming_message(
                        account_id=str(event.account.id),
                        from_number=message.from_number,
                        message_text=message.text_body or '',
                        message_type=message.message_type,
                        message_data=message_data
                    )
                except Exception as e:
                    automation_error = e
                    logger.warning(f"[AutomationService] Error: {e}")
            
            thread = threading.Thread(target=run_automation)
            thread.start()
            thread.join(timeout=10)
            
            if thread.is_alive():
                logger.warning("[AutomationService] Timeout")
            
            if automation_response:
                logger.info(f"[AutomationService] Sending response: {automation_response[:50]}...")
                try:
                    from ..tasks import send_agent_response
                    send_agent_response.delay(
                        str(event.account.id),
                        message.from_number,
                        automation_response,
                        str(message.whatsapp_message_id)
                    )
                    logger.info("[AutomationService] Response queued successfully")
                    return  # Sucesso!
                except Exception as e:
                    logger.error(f"[AutomationService] Failed to queue response: {e}")
                    # Continua para último fallback
                    
            if automation_error:
                logger.warning(f"[AutomationService] Error occurred: {automation_error}")
                
        except Exception as e:
            logger.warning(f"[AutomationService] Unexpected error: {e}")

        # ========== NÍVEL 3: AI Agent (último recurso) ==========
        if event.account.auto_response_enabled and not message.processed_by_agent:
            try:
                has_agent = hasattr(event.account, 'default_agent') and event.account.default_agent
                
                if has_agent:
                    logger.info(f"[AI Agent] Enqueuing agent processing for message: {message.id}")
                    current_app.send_task(
                        'apps.whatsapp.tasks.process_message_with_agent', 
                        args=[str(message.id)],
                        queue='default',
                        countdown=0
                    )
                    logger.info("[AI Agent] Task enqueued successfully")
                else:
                    logger.debug(f"[AI Agent] No default agent configured for account: {event.account.id}")
            except Exception as e:
                logger.error(f"[AI Agent] Failed to enqueue task: {e}", exc_info=True)

    def _extract_name_from_message(self, text: str) -> str:
        """Extract name from message patterns like 'my name is John', 'sou o Carlos', etc."""
        import re
        
        text_lower = text.lower().strip()
        
        # Patterns to match name introductions
        patterns = [
            r'meu nome [é|e]\s+(.+)',
            r'meu nome eh\s+(.+)',
            r'sou (?:o|a)\s+(.+)',
            r'(?:o|a) meu nome [é|e]\s+(.+)',
            r'pode me chamar de\s+(.+)',
            r'(?:eu sou|sou)\s+(.+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                name = match.group(1).strip()
                # Remove punctuation at the end
                name = re.sub(r'[.!?;,]$', '', name)
                # Capitalize first letter of each word
                name = name.title()
                if len(name) > 1 and len(name) < 50:  # Reasonable name length
                    return name
        
        return ""

    def _process_inbound_message(self, event: WebhookEvent) -> Optional[Message]:
        """Process an inbound message event."""
        payload = event.payload
        message_data = payload.get('message', {})
        contact_data = payload.get('contact', {})
        
        if not message_data:
            logger.warning(f"No message data in event {event.id}")
            return None
        
        # Extract message details
        whatsapp_message_id = message_data.get('id')
        from_number = message_data.get('from')
        timestamp = message_data.get('timestamp')
        message_type = message_data.get('type', 'unknown')
        
        # Check for duplicate message
        existing = Message.objects.filter(whatsapp_message_id=whatsapp_message_id).first()
        if existing:
            logger.info(f"Duplicate message ignored: {whatsapp_message_id}")
            return existing
        
        # Extract text content based on message type
        text_body = ''
        content = {}
        media_id = ''
        media_url = ''
        media_mime_type = ''
        media_sha256 = ''
        
        if message_type == 'text':
            text_body = message_data.get('text', {}).get('body', '')
            content = {'text': text_body}
        elif message_type in ['image', 'video', 'audio', 'document', 'sticker']:
            media_data = message_data.get(message_type, {})
            media_id = media_data.get('id', '')
            media_mime_type = media_data.get('mime_type', '')
            text_body = media_data.get('caption', '')
            content = {message_type: media_data}
            media_url, media_sha256 = self._fetch_and_store_media(event.account, media_id, media_mime_type)
        elif message_type == 'location':
            location = message_data.get('location', {})
            content = {'location': location}
            text_body = f"📍 {location.get('name', 'Location')}"
        elif message_type == 'contacts':
            contacts = message_data.get('contacts', [])
            content = {'contacts': contacts}
            text_body = f"👤 {len(contacts)} contact(s)"
        elif message_type == 'interactive':
            interactive = message_data.get('interactive', {})
            content = {'interactive': interactive}
            # Extract button/list reply
            if 'button_reply' in interactive:
                text_body = interactive['button_reply'].get('title', '')
            elif 'list_reply' in interactive:
                text_body = interactive['list_reply'].get('title', '')
        elif message_type == 'button':
            button = message_data.get('button', {})
            text_body = button.get('text', '')
            content = {'button': button}
        elif message_type == 'reaction':
            reaction = message_data.get('reaction', {})
            content = {'reaction': reaction}
            text_body = reaction.get('emoji', '👍')
        elif message_type == 'order':
            order = message_data.get('order', {})
            content = {'order': order}
            text_body = f"🛒 Order with {len(order.get('product_items', []))} item(s)"
        else:
            content = message_data
        
        # Get or create conversation
        conversation = self._get_or_create_conversation(
            account=event.account,
            phone_number=from_number,
            contact_name=contact_data.get('profile', {}).get('name', '')
        )
        
        # Create message
        message = Message.objects.create(
            account=event.account,
            conversation=conversation,
            whatsapp_message_id=whatsapp_message_id,
            direction=Message.MessageDirection.INBOUND,
            message_type=self._map_message_type(message_type),
            status=Message.MessageStatus.DELIVERED,
            from_number=from_number,
            to_number=event.account.phone_number,
            content=content,
            text_body=text_body,
            media_id=media_id,
            media_url=media_url,
            media_mime_type=media_mime_type,
            media_sha256=media_sha256,
            context_message_id=message_data.get('context', {}).get('id', ''),
            delivered_at=timezone.now(),
            metadata={
                'timestamp': timestamp,
                'contact': contact_data
            }
        )
        
        # Link event to message
        event.related_message = message
        event.save(update_fields=['related_message'])
        
        # Update conversation
        conversation.last_message_at = timezone.now()
        conversation.last_customer_message_at = timezone.now()
        conversation.save(update_fields=['last_message_at', 'last_customer_message_at', 'updated_at'])
        
        # Broadcast to connected clients
        self._broadcast_new_message(event.account, message, conversation, contact_data)
        
        logger.info(f"Processed inbound message: {message.id} from {from_number}")
        return message

    def _process_status_update(self, event: WebhookEvent) -> Optional[Message]:
        """Process a message status update event."""
        payload = event.payload
        
        whatsapp_message_id = payload.get('id')
        status = payload.get('status')
        timestamp = payload.get('timestamp')
        recipient_id = payload.get('recipient_id')
        
        if not whatsapp_message_id or not status:
            logger.warning(f"Invalid status update in event {event.id}")
            return None
        
        # Find the message
        message = Message.objects.filter(whatsapp_message_id=whatsapp_message_id).first()
        
        if not message:
            logger.warning(f"Message not found for status update: {whatsapp_message_id}")
            return None
        
        # Map Meta status to our status
        status_map = {
            'sent': Message.MessageStatus.SENT,
            'delivered': Message.MessageStatus.DELIVERED,
            'read': Message.MessageStatus.READ,
            'failed': Message.MessageStatus.FAILED,
        }
        
        new_status = status_map.get(status)
        if not new_status:
            logger.warning(f"Unknown status: {status}")
            return message
        
        # Only update if status is "higher" (sent < delivered < read)
        status_order = ['pending', 'sent', 'delivered', 'read', 'failed']
        current_idx = status_order.index(message.status) if message.status in status_order else 0
        new_idx = status_order.index(new_status) if new_status in status_order else 0
        
        if new_idx <= current_idx and new_status != 'failed':
            logger.debug(f"Ignoring status update {status} for message {message.id} (current: {message.status})")
            return message
        
        # Update message status
        message.status = new_status
        update_fields = ['status', 'updated_at']
        
        # Set timestamp fields
        status_time = timezone.now()
        if timestamp:
            try:
                status_time = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
            except (ValueError, TypeError):
                pass
        
        if new_status == Message.MessageStatus.SENT:
            message.sent_at = status_time
            update_fields.append('sent_at')
        elif new_status == Message.MessageStatus.DELIVERED:
            message.delivered_at = status_time
            update_fields.append('delivered_at')
        elif new_status == Message.MessageStatus.READ:
            message.read_at = status_time
            update_fields.append('read_at')
        elif new_status == Message.MessageStatus.FAILED:
            message.failed_at = status_time
            update_fields.append('failed_at')
            # Extract error info if available
            errors = payload.get('errors', [])
            if errors:
                message.error_code = str(errors[0].get('code', ''))
                message.error_message = errors[0].get('title', '')
                update_fields.extend(['error_code', 'error_message'])
        
        message.save(update_fields=update_fields)
        
        # Link event to message
        event.related_message = message
        event.save(update_fields=['related_message'])
        
        # Broadcast status update
        self.broadcast.broadcast_status_update(
            account_id=str(event.account.id),
            message_id=str(message.id),
            status=new_status,
            whatsapp_message_id=whatsapp_message_id,
            timestamp=status_time
        )
        
        logger.info(f"Updated message {message.id} status to {new_status}")
        return message

    def _process_error(self, event: WebhookEvent) -> None:
        """Process an error event."""
        payload = event.payload
        
        error_code = str(payload.get('code', ''))
        error_title = payload.get('title', 'Unknown error')
        error_message = payload.get('message', '')
        error_details = payload.get('error_data', {})
        
        logger.error(f"WhatsApp API error: {error_code} - {error_title}: {error_message}")
        
        # Broadcast error to clients
        self.broadcast.broadcast_error(
            account_id=str(event.account.id),
            error_code=error_code,
            error_message=f"{error_title}: {error_message}" if error_message else error_title
        )

    def _get_or_create_conversation(
        self,
        account: WhatsAppAccount,
        phone_number: str,
        contact_name: str = ''
    ):
        """Get or create a conversation for a phone number.
        
        Uses transaction-safe approach to handle race conditions where multiple
        webhook events try to create a conversation for the same phone number simultaneously.
        """
        from apps.conversations.models import Conversation
        from django.db import IntegrityError
        
        try:
            conversation, created = Conversation.objects.get_or_create(
                account=account,
                phone_number=phone_number,
                defaults={
                    'contact_name': contact_name,
                    'status': Conversation.ConversationStatus.OPEN,
                    'mode': Conversation.ConversationMode.AUTO
                }
            )
            
            if created:
                logger.info(f"Created new conversation with {phone_number}")
                # Broadcast new conversation
                self.broadcast.broadcast_conversation_update(
                    account_id=str(account.id),
                    conversation={
                        'id': str(conversation.id),
                        'phone_number': phone_number,
                        'contact_name': contact_name,
                        'status': conversation.status,
                        'mode': conversation.mode,
                        'created_at': conversation.created_at.isoformat()
                    }
                )
            elif contact_name and not conversation.contact_name:
                # Update contact name if we didn't have it
                conversation.contact_name = contact_name
                conversation.save(update_fields=['contact_name', 'updated_at'])
            
            return conversation
            
        except IntegrityError:
            # Race condition: another request created the conversation first
            # This can happen with unique_together constraint on (account, phone_number)
            logger.warning(f"IntegrityError on get_or_create for {phone_number}, retrying get...")
            try:
                conversation = Conversation.objects.get(
                    account=account,
                    phone_number=phone_number
                )
                return conversation
            except Conversation.DoesNotExist:
                # This shouldn't happen but handle it gracefully
                logger.error(f"Conversation not found after IntegrityError for {phone_number}")
                raise

    def _broadcast_new_message(
        self,
        account: WhatsAppAccount,
        message: Message,
        conversation,
        contact_data: Dict[str, Any]
    ) -> None:
        """Broadcast a new message to connected clients."""
        message_dict = {
            'id': str(message.id),
            'whatsapp_message_id': message.whatsapp_message_id,
            'direction': message.direction,
            'message_type': message.message_type,
            'status': message.status,
            'from_number': message.from_number,
            'to_number': message.to_number,
            'text_body': message.text_body,
            'content': message.content,
            'media_id': message.media_id,
            'media_url': message.media_url,
            'media_mime_type': message.media_mime_type,
            'media_sha256': message.media_sha256,
            'created_at': message.created_at.isoformat(),
            'delivered_at': message.delivered_at.isoformat() if message.delivered_at else None,
        }
        
        contact_dict = {
            'wa_id': contact_data.get('wa_id', message.from_number),
            'name': contact_data.get('profile', {}).get('name', ''),
        }
        
        self.broadcast.broadcast_new_message(
            account_id=str(account.id),
            message=message_dict,
            conversation_id=str(conversation.id) if conversation else None,
            contact=contact_dict
        )

    def _map_message_type(self, meta_type: str) -> str:
        """Map Meta message type to our MessageType."""
        type_map = {
            'text': Message.MessageType.TEXT,
            'image': Message.MessageType.IMAGE,
            'video': Message.MessageType.VIDEO,
            'audio': Message.MessageType.AUDIO,
            'document': Message.MessageType.DOCUMENT,
            'sticker': Message.MessageType.STICKER,
            'location': Message.MessageType.LOCATION,
            'contacts': Message.MessageType.CONTACTS,
            'interactive': Message.MessageType.INTERACTIVE,
            'template': Message.MessageType.TEMPLATE,
            'reaction': Message.MessageType.REACTION,
            'button': Message.MessageType.BUTTON,
            'order': Message.MessageType.ORDER,
            'system': Message.MessageType.SYSTEM,
        }
        return type_map.get(meta_type, Message.MessageType.UNKNOWN)

    def _fetch_and_store_media(
        self,
        account: WhatsAppAccount,
        media_id: str,
        mime_type: str
    ) -> Tuple[str, str]:
        """Download media from WhatsApp and store it locally or on the configured storage."""
        if not media_id:
            return '', ''

        try:
            api_service = WhatsAppAPIService(account)
            url = api_service.get_media_url(media_id)
            if not url:
                return '', ''

            media_bytes = api_service.download_media(url)
            sha256 = hashlib.sha256(media_bytes).hexdigest()
            extension = mimetypes.guess_extension(mime_type or '') or ''
            filename = f"whatsapp/{account.id}/{media_id}{extension}"

            if default_storage.exists(filename):
                # Use default_storage.url() to get correct URL (works with S3 and local)
                return default_storage.url(filename), sha256

            saved_path = default_storage.save(filename, ContentFile(media_bytes))
            # Use default_storage.url() to get correct URL (works with S3 and local)
            return default_storage.url(saved_path), sha256

        except Exception as exc:
            logger.warning(f"Failed to persist media {media_id}: {exc}")
            return '', ''
