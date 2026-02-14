"""
Message Service - Business logic for message operations.
"""
import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from django.utils import timezone
from django.db import transaction
from apps.core.exceptions import ValidationError, NotFoundError
from ..models import WhatsAppAccount, Message
from ..repositories import MessageRepository, WhatsAppAccountRepository
from .whatsapp_api_service import WhatsAppAPIService
from .broadcast_service import get_broadcast_service

logger = logging.getLogger(__name__)


class MessageService:
    """Service for message operations."""

    def __init__(self):
        self.message_repo = MessageRepository()
        self.account_repo = WhatsAppAccountRepository()
        self.broadcast = get_broadcast_service()

    def send_text_message(
        self,
        account_id: str,
        to: str,
        text: str,
        preview_url: bool = False,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Message:
        """Send a text message."""
        account = self._get_account(account_id)
        api_service = WhatsAppAPIService(account)
        
        message = self._create_outbound_message(
            account=account,
            to=to,
            message_type=Message.MessageType.TEXT,
            content={'text': text, 'preview_url': preview_url},
            text_body=text,
            context_message_id=reply_to or '',
            metadata=metadata or {}
        )
        
        try:
            response = api_service.send_text_message(
                to=to,
                text=text,
                preview_url=preview_url,
                reply_to=reply_to
            )
            
            self._update_message_sent(message, response)
            logger.info(f"Text message sent: {message.id}")
            
        except Exception as e:
            self._update_message_failed(message, str(e))
            raise
        
        return message

    def send_template_message(
        self,
        account_id: str,
        to: str,
        template_name: str,
        language_code: str = 'pt_BR',
        components: Optional[List[Dict]] = None,
        metadata: Optional[Dict] = None
    ) -> Message:
        """Send a template message."""
        account = self._get_account(account_id)
        api_service = WhatsAppAPIService(account)
        
        message = self._create_outbound_message(
            account=account,
            to=to,
            message_type=Message.MessageType.TEMPLATE,
            content={
                'template_name': template_name,
                'language_code': language_code,
                'components': components or []
            },
            template_name=template_name,
            template_language=language_code,
            metadata=metadata or {}
        )
        
        try:
            response = api_service.send_template_message(
                to=to,
                template_name=template_name,
                language_code=language_code,
                components=components
            )
            
            self._update_message_sent(message, response)
            logger.info(f"Template message sent: {message.id}")
            
        except Exception as e:
            self._update_message_failed(message, str(e))
            raise
        
        return message

    def send_interactive_buttons(
        self,
        account_id: str,
        to: str,
        body_text: str,
        buttons: List[Dict[str, str]],
        header: Optional[Dict] = None,
        footer: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Message:
        """Send interactive button message."""
        account = self._get_account(account_id)
        api_service = WhatsAppAPIService(account)
        
        message = self._create_outbound_message(
            account=account,
            to=to,
            message_type=Message.MessageType.INTERACTIVE,
            content={
                'type': 'button',
                'body_text': body_text,
                'buttons': buttons,
                'header': header,
                'footer': footer
            },
            text_body=body_text,
            context_message_id=reply_to or '',
            metadata=metadata or {}
        )
        
        try:
            response = api_service.send_interactive_buttons(
                to=to,
                body_text=body_text,
                buttons=buttons,
                header=header,
                footer=footer,
                reply_to=reply_to
            )
            
            self._update_message_sent(message, response)
            logger.info(f"Interactive button message sent: {message.id}")
            
        except Exception as e:
            self._update_message_failed(message, str(e))
            raise
        
        return message

    def send_interactive_list(
        self,
        account_id: str,
        to: str,
        body_text: str,
        button_text: str,
        sections: List[Dict],
        header: Optional[str] = None,
        footer: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Message:
        """Send interactive list message."""
        account = self._get_account(account_id)
        api_service = WhatsAppAPIService(account)
        
        message = self._create_outbound_message(
            account=account,
            to=to,
            message_type=Message.MessageType.INTERACTIVE,
            content={
                'type': 'list',
                'body_text': body_text,
                'button_text': button_text,
                'sections': sections,
                'header': header,
                'footer': footer
            },
            text_body=body_text,
            context_message_id=reply_to or '',
            metadata=metadata or {}
        )
        
        try:
            response = api_service.send_interactive_list(
                to=to,
                body_text=body_text,
                button_text=button_text,
                sections=sections,
                header=header,
                footer=footer,
                reply_to=reply_to
            )
            
            self._update_message_sent(message, response)
            logger.info(f"Interactive list message sent: {message.id}")
            
        except Exception as e:
            self._update_message_failed(message, str(e))
            raise
        
        return message

    def send_image(
        self,
        account_id: str,
        to: str,
        image_url: Optional[str] = None,
        image_id: Optional[str] = None,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Message:
        """Send an image message."""
        account = self._get_account(account_id)
        api_service = WhatsAppAPIService(account)
        
        message = self._create_outbound_message(
            account=account,
            to=to,
            message_type=Message.MessageType.IMAGE,
            content={
                'image_url': image_url,
                'image_id': image_id,
                'caption': caption
            },
            text_body=caption or '',
            media_url=image_url or '',
            media_id=image_id or '',
            context_message_id=reply_to or '',
            metadata=metadata or {}
        )
        
        try:
            response = api_service.send_image(
                to=to,
                image_url=image_url,
                image_id=image_id,
                caption=caption,
                reply_to=reply_to
            )
            
            self._update_message_sent(message, response)
            logger.info(f"Image message sent: {message.id}")
            
        except Exception as e:
            self._update_message_failed(message, str(e))
            raise
        
        return message

    def send_document(
        self,
        account_id: str,
        to: str,
        document_url: Optional[str] = None,
        document_id: Optional[str] = None,
        filename: Optional[str] = None,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Message:
        """Send a document message."""
        account = self._get_account(account_id)
        api_service = WhatsAppAPIService(account)
        
        message = self._create_outbound_message(
            account=account,
            to=to,
            message_type=Message.MessageType.DOCUMENT,
            content={
                'document_url': document_url,
                'document_id': document_id,
                'filename': filename,
                'caption': caption
            },
            text_body=caption or '',
            media_url=document_url or '',
            media_id=document_id or '',
            context_message_id=reply_to or '',
            metadata=metadata or {}
        )
        
        try:
            response = api_service.send_document(
                to=to,
                document_url=document_url,
                document_id=document_id,
                filename=filename,
                caption=caption,
                reply_to=reply_to
            )
            
            self._update_message_sent(message, response)
            logger.info(f"Document message sent: {message.id}")
            
        except Exception as e:
            self._update_message_failed(message, str(e))
            raise
        
        return message

    def mark_as_read(self, account_id: str, message_id: str) -> bool:
        """Mark a message as read."""
        account = self._get_account(account_id)
        api_service = WhatsAppAPIService(account)
        
        try:
            api_service.mark_as_read(message_id)
            logger.info(f"Message marked as read: {message_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to mark message as read: {str(e)}")
            return False

    def process_inbound_message(
        self,
        account: WhatsAppAccount,
        message_data: Dict[str, Any]
    ) -> Message:
        """Process an inbound message from webhook."""
        whatsapp_message_id = message_data.get('id')
        
        if self.message_repo.exists_by_whatsapp_id(whatsapp_message_id):
            logger.info(f"Duplicate message received: {whatsapp_message_id}")
            return self.message_repo.get_by_whatsapp_id(whatsapp_message_id)
        
        message_type = message_data.get('type', 'unknown')
        from_number = message_data.get('from')
        
        content = {}
        text_body = ''
        media_id = ''
        
        if message_type == 'text':
            text_body = message_data.get('text', {}).get('body', '')
            content = {'text': text_body}
        elif message_type == 'image':
            image_data = message_data.get('image', {})
            media_id = image_data.get('id', '')
            text_body = image_data.get('caption', '')
            content = image_data
        elif message_type == 'video':
            video_data = message_data.get('video', {})
            media_id = video_data.get('id', '')
            text_body = video_data.get('caption', '')
            content = video_data
        elif message_type == 'audio':
            audio_data = message_data.get('audio', {})
            media_id = audio_data.get('id', '')
            content = audio_data
        elif message_type == 'document':
            doc_data = message_data.get('document', {})
            media_id = doc_data.get('id', '')
            text_body = doc_data.get('caption', '')
            content = doc_data
        elif message_type == 'sticker':
            sticker_data = message_data.get('sticker', {})
            media_id = sticker_data.get('id', '')
            content = sticker_data
        elif message_type == 'location':
            content = message_data.get('location', {})
        elif message_type == 'contacts':
            content = {'contacts': message_data.get('contacts', [])}
        elif message_type == 'interactive':
            interactive = message_data.get('interactive', {})
            interactive_type = interactive.get('type')
            if interactive_type == 'button_reply':
                button_reply = interactive.get('button_reply', {})
                text_body = button_reply.get('title', '')
                content = {'button_reply': button_reply}
            elif interactive_type == 'list_reply':
                list_reply = interactive.get('list_reply', {})
                text_body = list_reply.get('title', '')
                content = {'list_reply': list_reply}
            else:
                content = interactive
        elif message_type == 'button':
            button = message_data.get('button', {})
            text_body = button.get('text', '')
            content = button
        elif message_type == 'order':
            content = message_data.get('order', {})
        elif message_type == 'reaction':
            content = message_data.get('reaction', {})
        else:
            content = message_data
        
        context = message_data.get('context', {})
        context_message_id = context.get('id', '')
        
        message = self.message_repo.create(
            account=account,
            whatsapp_message_id=whatsapp_message_id,
            direction=Message.MessageDirection.INBOUND,
            message_type=self._map_message_type(message_type),
            status=Message.MessageStatus.DELIVERED,
            from_number=from_number,
            to_number=account.phone_number,
            content=content,
            text_body=text_body,
            media_id=media_id,
            context_message_id=context_message_id,
            delivered_at=timezone.now()
        )
        
        logger.info(f"Inbound message processed: {message.id}")
        return message

    def update_message_status(
        self,
        whatsapp_message_id: str,
        status: str,
        timestamp: Optional[datetime] = None
    ) -> Optional[Message]:
        """Update message status from webhook."""
        message = self.message_repo.get_by_whatsapp_id(whatsapp_message_id)
        
        if not message:
            logger.warning(f"Message not found for status update: {whatsapp_message_id}")
            return None
        
        status_map = {
            'sent': Message.MessageStatus.SENT,
            'delivered': Message.MessageStatus.DELIVERED,
            'read': Message.MessageStatus.READ,
            'failed': Message.MessageStatus.FAILED,
        }
        
        new_status = status_map.get(status)
        if new_status:
            message = self.message_repo.update_status(message, new_status, timestamp)
            logger.info(f"Message status updated: {message.id} -> {new_status}")
        
        return message

    def update_message_error(
        self,
        whatsapp_message_id: str,
        error_code: str,
        error_message: str
    ) -> Optional[Message]:
        """Update message with error information."""
        message = self.message_repo.get_by_whatsapp_id(whatsapp_message_id)
        
        if not message:
            logger.warning(f"Message not found for error update: {whatsapp_message_id}")
            return None
        
        message = self.message_repo.update_error(message, error_code, error_message)
        logger.info(f"Message error updated: {message.id}")
        
        return message

    def get_message(self, message_id: str) -> Message:
        """Get message by ID."""
        message = self.message_repo.get_by_id(message_id)
        if not message:
            raise NotFoundError(message="Message not found")
        return message

    def get_conversation_history(
        self,
        account_id: str,
        phone_number: str,
        limit: int = 50
    ) -> List[Message]:
        """Get conversation history with a phone number."""
        account = self._get_account(account_id)
        return list(self.message_repo.get_conversation_messages(
            account=account,
            phone_number=phone_number,
            limit=limit
        ))

    def get_message_stats(
        self,
        account_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get message statistics."""
        account = self._get_account(account_id)
        return self.message_repo.get_message_stats(account, start_date, end_date)

    def _get_account(self, account_id: str) -> WhatsAppAccount:
        """Get and validate account."""
        account = self.account_repo.get_by_id(account_id)
        if not account:
            raise NotFoundError(message="WhatsApp account not found")
        if account.status != WhatsAppAccount.AccountStatus.ACTIVE:
            raise ValidationError(message="WhatsApp account is not active")
        return account

    def _create_outbound_message(
        self,
        account: WhatsAppAccount,
        to: str,
        message_type: str,
        content: Dict,
        text_body: str = '',
        template_name: str = '',
        template_language: str = '',
        media_url: str = '',
        media_id: str = '',
        context_message_id: str = '',
        metadata: Dict = None
    ) -> Message:
        """Create an outbound message record."""
        meta = metadata or {}
        
        # Try to get or create conversation, but make it optional for auth messages
        conversation = None
        try:
            conversation = self._get_or_create_conversation(account, to)
            
            # Fill contact name if provided in metadata
            contact_name = meta.get('contact_name') or meta.get('customer_name')
            if contact_name and conversation and not conversation.contact_name:
                conversation.contact_name = contact_name
                conversation.save(update_fields=['contact_name', 'updated_at'])
        except Exception as conv_error:
            # Log but don't fail - conversation is optional for auth messages
            logger.warning(f"Could not create conversation for {to}: {conv_error}")
            conversation = None
        
        message = self.message_repo.create(
            account=account,
            conversation=conversation,
            whatsapp_message_id=f"pending_{uuid.uuid4().hex}",
            direction=Message.MessageDirection.OUTBOUND,
            message_type=message_type,
            status=Message.MessageStatus.PENDING,
            from_number=account.phone_number,
            to_number=to,
            content=content,
            text_body=text_body,
            template_name=template_name,
            template_language=template_language,
            media_url=media_url,
            media_id=media_id,
            context_message_id=context_message_id,
            metadata=meta
        )
        
        # Update conversation last message time if we have one
        if conversation:
            try:
                conversation.last_message_at = timezone.now()
                conversation.last_agent_message_at = timezone.now()
                conversation.save(update_fields=['last_message_at', 'last_agent_message_at', 'updated_at'])
            except Exception as e:
                logger.warning(f"Could not update conversation timestamps: {e}")
        
        return message
    
    def _get_or_create_conversation(self, account: WhatsAppAccount, phone_number: str):
        """Get or create a conversation for a phone number."""
        from apps.conversations.models import Conversation
        
        conversation, created = Conversation.objects.get_or_create(
            account=account,
            phone_number=phone_number,
            defaults={
                'status': Conversation.ConversationStatus.OPEN,
                'mode': Conversation.ConversationMode.AUTO
            }
        )
        
        if created:
            logger.info(f"Created new conversation with {phone_number}")
        
        return conversation

    def _update_message_sent(self, message: Message, response: Dict) -> None:
        """Update message after successful send and broadcast to WebSocket."""
        messages = response.get('messages', [])
        if messages:
            whatsapp_id = messages[0].get('id')
            message.whatsapp_message_id = whatsapp_id
        
        message.status = Message.MessageStatus.SENT
        message.sent_at = timezone.now()
        message.save()
        
        # Broadcast outbound message to WebSocket clients
        try:
            message_data = {
                'id': str(message.id),
                'whatsapp_message_id': message.whatsapp_message_id,
                'direction': message.direction,
                'message_type': message.message_type,
                'status': message.status,
                'from_number': message.from_number,
                'to_number': message.to_number,
                'text_body': message.text_body,
                'sent_at': message.sent_at.isoformat() if message.sent_at else None,
                'created_at': message.created_at.isoformat(),
                'conversation_id': str(message.conversation_id) if message.conversation_id else None,
            }
            self.broadcast.broadcast_message_sent(
                account_id=str(message.account_id),
                message=message_data,
                conversation_id=str(message.conversation_id) if message.conversation_id else None
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast outbound message: {e}")

    def _update_message_failed(self, message: Message, error: str) -> None:
        """Update message after failed send."""
        message.status = Message.MessageStatus.FAILED
        message.failed_at = timezone.now()
        message.error_message = error
        message.save()
        
        # Broadcast failure to WebSocket clients
        try:
            self.broadcast.broadcast_status_update(
                account_id=str(message.account_id),
                message_id=str(message.id),
                status=Message.MessageStatus.FAILED,
                whatsapp_message_id=message.whatsapp_message_id,
                timestamp=message.failed_at
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast message failure: {e}")

    def _map_message_type(self, type_str: str) -> str:
        """Map WhatsApp message type to model type."""
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
        return type_map.get(type_str, Message.MessageType.UNKNOWN)
