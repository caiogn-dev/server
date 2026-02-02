"""
Email provider for messaging dispatcher.
"""
import logging
from typing import Optional

from .base import BaseProvider, ProviderResult
from ..exceptions import ProviderError

logger = logging.getLogger(__name__)


class EmailProvider(BaseProvider):
    """
    Email messaging provider.
    Wraps the existing email services.
    """
    
    channel = 'email'
    
    def __init__(self):
        self._service = None
    
    @property
    def service(self):
        """Lazy load the email service."""
        if self._service is None:
            from apps.marketing.services import EmailMarketingService
            self._service = EmailMarketingService()
        return self._service
    
    def send(self, message, store=None) -> ProviderResult:
        """
        Send email message.
        """
        try:
            content = message.content
            
            # Extract email components
            subject = content.get('subject', 'Notification')
            body = content.get('body') or content.get('text', '')
            html_body = content.get('html') or content.get('html_body')
            
            # Send via Resend/Email service
            result = self.service.send_single_email(
                to_email=message.recipient,
                subject=subject,
                html_content=html_body or body,
                text_content=body if not html_body else None,
                metadata={
                    'message_id': str(message.id),
                    'source': message.source,
                    'source_id': message.source_id
                }
            )
            
            return ProviderResult(
                success=result.get('success', False),
                external_id=result.get('message_id'),
                error_code=result.get('error_code'),
                error_message=result.get('error_message'),
                raw_response=result
            )
            
        except Exception as e:
            logger.exception(f"Email send error: {e}")
            return ProviderResult(
                success=False,
                error_code='SEND_ERROR',
                error_message=str(e)
            )
    
    def validate_recipient(self, recipient: str) -> bool:
        """
        Validate email address.
        Basic email validation.
        """
        import re
        
        if not recipient:
            return False
        
        # Basic email regex
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, recipient))
    
    def format_recipient(self, recipient: str) -> str:
        """Format email address."""
        return recipient.lower().strip()
