"""
WhatsApp provider for messaging dispatcher.
"""
import logging
from typing import Optional

from .base import BaseProvider, ProviderResult
from ..exceptions import ProviderError

logger = logging.getLogger(__name__)


class WhatsAppProvider(BaseProvider):
    """
    WhatsApp messaging provider.
    Wraps the existing WhatsApp services.
    """
    
    channel = 'whatsapp'
    
    def __init__(self):
        self._service = None
    
    @property
    def service(self):
        """Lazy load the WhatsApp service."""
        if self._service is None:
            from apps.whatsapp.services import MessageService
            self._service = MessageService()
        return self._service
    
    def send(self, message, store=None) -> ProviderResult:
        """
        Send WhatsApp message.
        """
        try:
            # Get WhatsApp account for the store
            account = self._get_account(store)
            if not account:
                return ProviderResult(
                    success=False,
                    error_code='NO_ACCOUNT',
                    error_message='No WhatsApp account configured for this store'
                )
            
            content = message.content
            message_type = content.get('type', 'text')
            
            # Send based on message type
            if message_type == 'text' or 'text' in content:
                result = self._send_text(account, message, content)
            elif message_type == 'template' or 'template_name' in content:
                result = self._send_template(account, message, content)
            elif message_type == 'image' or 'image_url' in content:
                result = self._send_image(account, message, content)
            elif message_type == 'document' or 'document_url' in content:
                result = self._send_document(account, message, content)
            elif 'buttons' in content:
                result = self._send_interactive(account, message, content)
            else:
                # Default to text
                result = self._send_text(account, message, content)
            
            return result
            
        except Exception as e:
            logger.exception(f"WhatsApp send error: {e}")
            return ProviderResult(
                success=False,
                error_code='SEND_ERROR',
                error_message=str(e)
            )
    
    def _get_account(self, store) -> Optional['WhatsAppAccount']:
        """Get WhatsApp account for store."""
        if store:
            return store.get_whatsapp_account()
        return None
    
    def _send_text(self, account, message, content) -> ProviderResult:
        """Send text message."""
        try:
            text = content.get('text', content.get('body', ''))
            
            response = self.service.send_text_message(
                account_id=str(account.id),
                to=message.recipient,
                text=text,
                metadata={
                    'message_id': str(message.id),
                    'source': message.source,
                    'source_id': message.source_id
                }
            )
            
            return ProviderResult(
                success=True,
                external_id=response.get('message_id'),
                raw_response=response
            )
        except Exception as e:
            return ProviderResult(
                success=False,
                error_code='TEXT_SEND_ERROR',
                error_message=str(e)
            )
    
    def _send_template(self, account, message, content) -> ProviderResult:
        """Send template message."""
        try:
            template_name = content.get('template_name')
            language = content.get('language', 'pt_BR')
            components = content.get('components', [])
            
            response = self.service.send_template_message(
                account_id=str(account.id),
                to=message.recipient,
                template_name=template_name,
                language_code=language,
                components=components
            )
            
            return ProviderResult(
                success=True,
                external_id=response.get('message_id'),
                raw_response=response
            )
        except Exception as e:
            return ProviderResult(
                success=False,
                error_code='TEMPLATE_SEND_ERROR',
                error_message=str(e)
            )
    
    def _send_image(self, account, message, content) -> ProviderResult:
        """Send image message."""
        try:
            image_url = content.get('image_url') or content.get('media_url')
            caption = content.get('caption', content.get('text', ''))
            
            response = self.service.send_image_message(
                account_id=str(account.id),
                to=message.recipient,
                image_url=image_url,
                caption=caption
            )
            
            return ProviderResult(
                success=True,
                external_id=response.get('message_id'),
                raw_response=response
            )
        except Exception as e:
            return ProviderResult(
                success=False,
                error_code='IMAGE_SEND_ERROR',
                error_message=str(e)
            )
    
    def _send_document(self, account, message, content) -> ProviderResult:
        """Send document message."""
        try:
            document_url = content.get('document_url') or content.get('media_url')
            caption = content.get('caption', '')
            filename = content.get('filename', 'document.pdf')
            
            response = self.service.send_document_message(
                account_id=str(account.id),
                to=message.recipient,
                document_url=document_url,
                caption=caption,
                filename=filename
            )
            
            return ProviderResult(
                success=True,
                external_id=response.get('message_id'),
                raw_response=response
            )
        except Exception as e:
            return ProviderResult(
                success=False,
                error_code='DOCUMENT_SEND_ERROR',
                error_message=str(e)
            )
    
    def _send_interactive(self, account, message, content) -> ProviderResult:
        """Send interactive message with buttons."""
        try:
            body_text = content.get('body_text', content.get('text', ''))
            buttons = content.get('buttons', [])
            
            response = self.service.send_interactive_buttons(
                account_id=str(account.id),
                to=message.recipient,
                body_text=body_text,
                buttons=buttons
            )
            
            return ProviderResult(
                success=True,
                external_id=response.get('message_id'),
                raw_response=response
            )
        except Exception as e:
            return ProviderResult(
                success=False,
                error_code='INTERACTIVE_SEND_ERROR',
                error_message=str(e)
            )
    
    def validate_recipient(self, recipient: str) -> bool:
        """
        Validate phone number.
        Basic validation - should start with + and country code.
        """
        if not recipient:
            return False
        
        # Remove spaces and dashes
        cleaned = recipient.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        
        # Should start with + followed by digits
        return cleaned.startswith('+') and len(cleaned) >= 8 and cleaned[1:].isdigit()
    
    def format_recipient(self, recipient: str) -> str:
        """Format phone number for WhatsApp."""
        # Remove all non-digit characters except +
        cleaned = ''.join(c for c in recipient if c.isdigit() or c == '+')
        
        # Ensure it starts with +
        if not cleaned.startswith('+'):
            # Assume Brazil if no country code
            if len(cleaned) == 11 or len(cleaned) == 10:
                cleaned = '+55' + cleaned
            else:
                cleaned = '+' + cleaned
        
        return cleaned
