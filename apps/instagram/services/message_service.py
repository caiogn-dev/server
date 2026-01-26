"""
Instagram Message Service - Handles message storage and processing.
"""
import logging
import hashlib
from typing import Optional, Dict, Any, List
from datetime import datetime
from django.utils import timezone
from django.db import transaction

from apps.instagram.models import (
    InstagramAccount,
    InstagramConversation,
    InstagramMessage,
    InstagramWebhookEvent
)
from .instagram_api import InstagramAPIService, InstagramAPIError

logger = logging.getLogger(__name__)


class InstagramMessageService:
    """Service for managing Instagram messages."""
    
    def __init__(self, account: InstagramAccount):
        self.account = account
        self.api = InstagramAPIService(account)
    
    # ==================== Send Messages ====================
    
    def send_text(self, recipient_id: str, text: str) -> InstagramMessage:
        """Send a text message and store it."""
        try:
            # Get or create conversation
            conversation = self._get_or_create_conversation(recipient_id)
            
            # Send via API
            response = self.api.send_text_message(recipient_id, text)
            
            # Store message
            message = InstagramMessage.objects.create(
                account=self.account,
                conversation=conversation,
                instagram_message_id=response.get('message_id', f"out_{timezone.now().timestamp()}"),
                direction=InstagramMessage.MessageDirection.OUTBOUND,
                message_type=InstagramMessage.MessageType.TEXT,
                status=InstagramMessage.MessageStatus.SENT,
                sender_id=self.account.instagram_account_id,
                recipient_id=recipient_id,
                text_content=text,
                sent_at=timezone.now()
            )
            
            # Update conversation
            conversation.last_message_at = timezone.now()
            conversation.last_message_preview = text[:255]
            conversation.message_count += 1
            conversation.save(update_fields=['last_message_at', 'last_message_preview', 'message_count', 'updated_at'])
            
            logger.info(f"Sent Instagram message to {recipient_id}: {message.instagram_message_id}")
            return message
            
        except InstagramAPIError as e:
            logger.error(f"Failed to send Instagram message: {e}")
            raise
    
    def send_image(self, recipient_id: str, image_url: str) -> InstagramMessage:
        """Send an image message."""
        conversation = self._get_or_create_conversation(recipient_id)
        
        response = self.api.send_image(recipient_id, image_url)
        
        message = InstagramMessage.objects.create(
            account=self.account,
            conversation=conversation,
            instagram_message_id=response.get('message_id', f"out_{timezone.now().timestamp()}"),
            direction=InstagramMessage.MessageDirection.OUTBOUND,
            message_type=InstagramMessage.MessageType.IMAGE,
            status=InstagramMessage.MessageStatus.SENT,
            sender_id=self.account.instagram_account_id,
            recipient_id=recipient_id,
            media_url=image_url,
            media_type='image',
            sent_at=timezone.now()
        )
        
        self._update_conversation_last_message(conversation, "📷 Imagem")
        return message
    
    def send_quick_replies(
        self, 
        recipient_id: str, 
        text: str, 
        options: List[Dict[str, str]]
    ) -> InstagramMessage:
        """Send a message with quick reply buttons."""
        conversation = self._get_or_create_conversation(recipient_id)
        
        response = self.api.send_quick_replies(recipient_id, text, options)
        
        message = InstagramMessage.objects.create(
            account=self.account,
            conversation=conversation,
            instagram_message_id=response.get('message_id', f"out_{timezone.now().timestamp()}"),
            direction=InstagramMessage.MessageDirection.OUTBOUND,
            message_type=InstagramMessage.MessageType.TEXT,
            status=InstagramMessage.MessageStatus.SENT,
            sender_id=self.account.instagram_account_id,
            recipient_id=recipient_id,
            text_content=text,
            metadata={'quick_replies': options},
            sent_at=timezone.now()
        )
        
        self._update_conversation_last_message(conversation, text)
        return message
    
    # ==================== Process Incoming ====================
    
    @transaction.atomic
    def process_incoming_message(self, webhook_data: Dict[str, Any]) -> Optional[InstagramMessage]:
        """Process an incoming message from webhook."""
        try:
            messaging = webhook_data.get('messaging', [{}])[0]
            sender_id = messaging.get('sender', {}).get('id')
            recipient_id = messaging.get('recipient', {}).get('id')
            message_data = messaging.get('message', {})
            
            if not sender_id or not message_data:
                logger.warning("Invalid webhook data: missing sender or message")
                return None
            
            # Check for duplicate
            message_id = message_data.get('mid')
            if InstagramMessage.objects.filter(instagram_message_id=message_id).exists():
                logger.debug(f"Duplicate message ignored: {message_id}")
                return None
            
            # Get or create conversation
            conversation = self._get_or_create_conversation(sender_id)
            
            # Determine message type
            message_type = self._determine_message_type(message_data)
            
            # Create message
            message = InstagramMessage.objects.create(
                account=self.account,
                conversation=conversation,
                instagram_message_id=message_id,
                direction=InstagramMessage.MessageDirection.INBOUND,
                message_type=message_type,
                status=InstagramMessage.MessageStatus.DELIVERED,
                sender_id=sender_id,
                recipient_id=recipient_id,
                text_content=message_data.get('text', ''),
                media_url=self._extract_media_url(message_data),
                media_type=self._extract_media_type(message_data),
                reply_to_message_id=message_data.get('reply_to', {}).get('mid', ''),
                metadata={'raw': message_data},
                delivered_at=timezone.now()
            )
            
            # Update conversation
            preview = message_data.get('text', '')[:255] or f"[{message_type}]"
            self._update_conversation_last_message(conversation, preview)
            
            # Try to fetch user profile
            self._update_participant_info(conversation, sender_id)
            
            logger.info(f"Processed incoming Instagram message: {message_id}")
            return message
            
        except Exception as e:
            logger.error(f"Error processing incoming message: {e}", exc_info=True)
            return None
    
    def process_message_seen(self, webhook_data: Dict[str, Any]) -> None:
        """Process message seen/read receipt."""
        try:
            messaging = webhook_data.get('messaging', [{}])[0]
            read_data = messaging.get('read', {})
            watermark = read_data.get('watermark')  # Timestamp
            
            if watermark:
                # Mark all messages before watermark as seen
                watermark_dt = datetime.fromtimestamp(int(watermark) / 1000, tz=timezone.utc)
                
                InstagramMessage.objects.filter(
                    account=self.account,
                    direction=InstagramMessage.MessageDirection.OUTBOUND,
                    sent_at__lte=watermark_dt,
                    status__in=[
                        InstagramMessage.MessageStatus.SENT,
                        InstagramMessage.MessageStatus.DELIVERED
                    ]
                ).update(
                    status=InstagramMessage.MessageStatus.SEEN,
                    seen_at=timezone.now()
                )
                
        except Exception as e:
            logger.error(f"Error processing message seen: {e}")
    
    # ==================== Conversation Management ====================
    
    def _get_or_create_conversation(self, participant_id: str) -> InstagramConversation:
        """Get or create a conversation with a participant."""
        conversation, created = InstagramConversation.objects.get_or_create(
            account=self.account,
            participant_id=participant_id,
            defaults={
                'status': InstagramConversation.ConversationStatus.ACTIVE
            }
        )
        
        if created:
            logger.info(f"Created new Instagram conversation with {participant_id}")
        
        return conversation
    
    def _update_conversation_last_message(self, conversation: InstagramConversation, preview: str):
        """Update conversation with last message info."""
        conversation.last_message_at = timezone.now()
        conversation.last_message_preview = preview[:255]
        conversation.message_count += 1
        conversation.save(update_fields=['last_message_at', 'last_message_preview', 'message_count', 'updated_at'])
    
    def _update_participant_info(self, conversation: InstagramConversation, user_id: str):
        """Try to update participant info from API."""
        if conversation.participant_username:
            return  # Already have info
        
        try:
            profile = self.api.get_user_profile(user_id)
            conversation.participant_username = profile.get('username', '')
            conversation.participant_name = profile.get('name', '')
            conversation.participant_profile_pic = profile.get('profile_pic', '')
            conversation.save(update_fields=[
                'participant_username', 
                'participant_name', 
                'participant_profile_pic',
                'updated_at'
            ])
        except Exception as e:
            logger.debug(f"Could not fetch user profile: {e}")
    
    # ==================== Helpers ====================
    
    def _determine_message_type(self, message_data: Dict) -> str:
        """Determine the message type from webhook data."""
        if message_data.get('text'):
            return InstagramMessage.MessageType.TEXT
        
        attachments = message_data.get('attachments', [])
        if attachments:
            att_type = attachments[0].get('type', 'unknown')
            type_mapping = {
                'image': InstagramMessage.MessageType.IMAGE,
                'video': InstagramMessage.MessageType.VIDEO,
                'audio': InstagramMessage.MessageType.AUDIO,
                'file': InstagramMessage.MessageType.FILE,
                'share': InstagramMessage.MessageType.SHARE,
                'story_mention': InstagramMessage.MessageType.STORY_MENTION,
            }
            return type_mapping.get(att_type, InstagramMessage.MessageType.UNKNOWN)
        
        if message_data.get('is_deleted'):
            return InstagramMessage.MessageType.DELETED
        
        return InstagramMessage.MessageType.UNKNOWN
    
    def _extract_media_url(self, message_data: Dict) -> str:
        """Extract media URL from message data."""
        attachments = message_data.get('attachments', [])
        if attachments:
            payload = attachments[0].get('payload', {})
            return payload.get('url', '')
        return ''
    
    def _extract_media_type(self, message_data: Dict) -> str:
        """Extract media type from message data."""
        attachments = message_data.get('attachments', [])
        if attachments:
            return attachments[0].get('type', '')
        return ''
    
    # ==================== Webhook Event Logging ====================
    
    @staticmethod
    def log_webhook_event(
        account: Optional[InstagramAccount],
        event_type: str,
        payload: Dict,
        headers: Dict = None
    ) -> InstagramWebhookEvent:
        """Log a webhook event for idempotency and debugging."""
        # Generate unique event ID
        payload_str = str(payload)
        event_id = hashlib.sha256(payload_str.encode()).hexdigest()[:32]
        
        # Check for duplicate
        existing = InstagramWebhookEvent.objects.filter(event_id=event_id).first()
        if existing:
            existing.processing_status = InstagramWebhookEvent.ProcessingStatus.DUPLICATE
            existing.save(update_fields=['processing_status', 'updated_at'])
            return existing
        
        return InstagramWebhookEvent.objects.create(
            account=account,
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            headers=headers or {}
        )
    
    # ==================== Bulk Operations ====================
    
    def get_conversation_history(
        self, 
        conversation: InstagramConversation, 
        limit: int = 50,
        before: Optional[datetime] = None
    ) -> List[InstagramMessage]:
        """Get message history for a conversation."""
        queryset = InstagramMessage.objects.filter(
            conversation=conversation
        ).order_by('-created_at')
        
        if before:
            queryset = queryset.filter(created_at__lt=before)
        
        return list(queryset[:limit])
    
    def get_unread_count(self, conversation: InstagramConversation) -> int:
        """Get count of unread messages in a conversation."""
        return InstagramMessage.objects.filter(
            conversation=conversation,
            direction=InstagramMessage.MessageDirection.INBOUND,
            status__in=[
                InstagramMessage.MessageStatus.DELIVERED,
                InstagramMessage.MessageStatus.PENDING
            ]
        ).count()
