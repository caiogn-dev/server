"""
Instagram provider for messaging dispatcher.
Handles sending direct messages through Instagram DM API.
"""
import logging
from typing import Optional

from .base import BaseProvider, ProviderResult
from ..exceptions import ProviderError

logger = logging.getLogger(__name__)


class InstagramProvider(BaseProvider):
    """
    Instagram messaging provider.
    Wraps the existing Instagram services for sending DMs.
    """
    
    channel = 'instagram'
    
    def __init__(self):
        self._service = None
    
    @property
    def service(self):
        """Lazy load the Instagram service."""
        if self._service is None:
            from apps.instagram.services.message_service import InstagramMessageService
            self._service = InstagramMessageService()
        return self._service
    
    def send(self, message, store=None) -> ProviderResult:
        """
        Send Instagram direct message.
        
        Args:
            message: Message model instance with recipient and content
            store: Optional store context
            
        Returns:
            ProviderResult with send status
        """
        try:
            # Get Instagram account for the store
            account = self._get_account(store, message)
            if not account:
                return ProviderResult(
                    success=False,
                    error_code='NO_ACCOUNT',
                    error_message='No Instagram account configured for this store'
                )
            
            content = message.content
            message_type = content.get('type', 'text')
            
            # Send based on message type
            if message_type == 'text' or 'text' in content:
                result = self._send_text(account, message, content)
            elif message_type == 'image' or 'image_url' in content:
                result = self._send_media(account, message, content, 'image')
            elif message_type == 'video' or 'video_url' in content:
                result = self._send_media(account, message, content, 'video')
            elif message_type == 'like' or content.get('reaction') == 'like':
                result = self._send_reaction(account, message, content)
            elif 'buttons' in content or 'quick_replies' in content:
                result = self._send_quick_replies(account, message, content)
            else:
                # Default to text
                result = self._send_text(account, message, content)
            
            return result
            
        except Exception as e:
            logger.exception(f"Instagram send error: {e}")
            return ProviderResult(
                success=False,
                error_code='SEND_ERROR',
                error_message=str(e)
            )
    
    def _get_account(self, store, message) -> Optional['InstagramAccount']:
        """
        Get Instagram account for store or from message metadata.
        """
        from apps.instagram.models import InstagramAccount
        
        # Try to get from message metadata
        if hasattr(message, 'metadata') and message.metadata:
            account_id = message.metadata.get('account_id')
            if account_id:
                try:
                    return InstagramAccount.objects.get(id=account_id)
                except InstagramAccount.DoesNotExist:
                    pass
        
        # Try to get from store
        if store:
            # Look for Instagram integration
            integration = store.integrations.filter(
                provider='instagram',
                is_enabled=True
            ).first()
            
            if integration and integration.settings.get('account_id'):
                try:
                    return InstagramAccount.objects.get(
                        id=integration.settings['account_id']
                    )
                except InstagramAccount.DoesNotExist:
                    pass
            
            # Try to find by store owner
            return InstagramAccount.objects.filter(
                owner=store.owner,
                is_active=True
            ).first()
        
        return None
    
    def _send_text(self, account, message, content) -> ProviderResult:
        """Send text message via Instagram DM."""
        try:
            text = content.get('text', content.get('body', ''))
            
            response = self.service.send_message(
                account_id=str(account.id),
                recipient_id=message.recipient,
                message_type='text',
                content={'text': text},
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
    
    def _send_media(self, account, message, content, media_type: str) -> ProviderResult:
        """Send media message (image/video) via Instagram DM."""
        try:
            media_url = content.get(f'{media_type}_url') or content.get('media_url')
            
            response = self.service.send_message(
                account_id=str(account.id),
                recipient_id=message.recipient,
                message_type=media_type,
                content={
                    'url': media_url,
                    'caption': content.get('caption', '')
                },
                metadata={
                    'message_id': str(message.id),
                    'source': message.source
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
                error_code=f'{media_type.upper()}_SEND_ERROR',
                error_message=str(e)
            )
    
    def _send_reaction(self, account, message, content) -> ProviderResult:
        """Send reaction (like) to a message."""
        try:
            reply_to = content.get('reply_to_message_id')
            
            if not reply_to:
                return ProviderResult(
                    success=False,
                    error_code='NO_MESSAGE_ID',
                    error_message='reply_to_message_id is required for reactions'
                )
            
            response = self.service.send_reaction(
                account_id=str(account.id),
                message_id=reply_to,
                reaction='heart'  # Instagram supports heart reaction
            )
            
            return ProviderResult(
                success=True,
                external_id=response.get('message_id'),
                raw_response=response
            )
        except Exception as e:
            return ProviderResult(
                success=False,
                error_code='REACTION_SEND_ERROR',
                error_message=str(e)
            )
    
    def _send_quick_replies(self, account, message, content) -> ProviderResult:
        """Send message with quick replies."""
        try:
            text = content.get('text', content.get('body', ''))
            quick_replies = content.get('quick_replies') or content.get('buttons', [])
            
            response = self.service.send_message(
                account_id=str(account.id),
                recipient_id=message.recipient,
                message_type='quick_replies',
                content={
                    'text': text,
                    'quick_replies': [
                        {'content_type': 'text', 'title': qr.get('title', qr), 'payload': qr.get('payload', qr)}
                        for qr in quick_replies
                    ]
                },
                metadata={
                    'message_id': str(message.id),
                    'source': message.source
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
                error_code='QUICK_REPLIES_SEND_ERROR',
                error_message=str(e)
            )
    
    def validate_recipient(self, recipient: str) -> bool:
        """
        Validate Instagram recipient.
        Instagram uses Instagram-scoped user IDs (IGSID).
        """
        if not recipient:
            return False
        
        # Instagram IDs are numeric strings
        # They can be long numbers like "123456789012345"
        cleaned = recipient.strip()
        
        # Should be numeric and reasonable length
        return cleaned.isdigit() and 5 <= len(cleaned) <= 25
    
    def format_recipient(self, recipient: str) -> str:
        """Format Instagram recipient ID."""
        # Just strip whitespace, IDs should be used as-is
        return recipient.strip()
    
    def get_status(self, external_id: str) -> Optional[str]:
        """
        Get message status from Instagram.
        Note: Instagram API has limited status tracking.
        """
        try:
            # Instagram doesn't provide granular message status like WhatsApp
            # We can only check if message was sent/delivered
            return 'sent'
        except Exception:
            return None
