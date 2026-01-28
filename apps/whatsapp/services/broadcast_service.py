"""
WhatsApp Broadcast Service - Send real-time updates via Django Channels.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

logger = logging.getLogger(__name__)


class WhatsAppBroadcastService:
    """
    Service for broadcasting WhatsApp events to connected WebSocket clients.
    
    Usage:
        broadcast = WhatsAppBroadcastService()
        broadcast.broadcast_new_message(account_id, message_data)
        broadcast.broadcast_status_update(account_id, message_id, 'delivered')
    """
    
    def __init__(self):
        self.channel_layer = get_channel_layer()
    
    def _get_account_group(self, account_id: str) -> str:
        """Get the channel group name for an account."""
        return f"whatsapp_{account_id}"
    
    def _get_conversation_group(self, conversation_id: str) -> str:
        """Get the channel group name for a conversation."""
        return f"whatsapp_conv_{conversation_id}"
    
    def _send_to_group(self, group_name: str, event: Dict[str, Any]) -> bool:
        """Send an event to a channel group."""
        if not self.channel_layer:
            logger.warning("Channel layer not available, skipping broadcast")
            return False
        
        try:
            async_to_sync(self.channel_layer.group_send)(group_name, event)
            logger.debug(f"Broadcast sent to {group_name}: {event.get('type')}")
            return True
        except Exception as e:
            logger.error(f"Failed to broadcast to {group_name}: {e}")
            return False
    
    def broadcast_new_message(
        self,
        account_id: str,
        message: Dict[str, Any],
        conversation_id: Optional[str] = None,
        contact: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Broadcast a new inbound message to connected clients.
        
        Args:
            account_id: WhatsApp account ID
            message: Message data dict with keys: id, whatsapp_message_id, direction,
                     message_type, status, from_number, to_number, text_body, created_at, etc.
            conversation_id: Optional conversation ID
            contact: Optional contact info dict
        
        Returns:
            True if broadcast was successful
        """
        group_name = self._get_account_group(account_id)
        
        event = {
            'type': 'whatsapp_message_received',
            'message': message,
            'account_id': str(account_id),
            'conversation_id': str(conversation_id) if conversation_id else None,
            'contact': contact
        }
        
        success = self._send_to_group(group_name, event)
        
        # Also send to conversation-specific group if available
        if conversation_id:
            conv_group = self._get_conversation_group(conversation_id)
            self._send_to_group(conv_group, event)
        
        logger.info(f"Broadcast new message for account {account_id}: {message.get('id')}")
        return success
    
    def broadcast_message_sent(
        self,
        account_id: str,
        message: Dict[str, Any],
        conversation_id: Optional[str] = None
    ) -> bool:
        """
        Broadcast confirmation of an outbound message.
        
        Args:
            account_id: WhatsApp account ID
            message: Message data dict
            conversation_id: Optional conversation ID
        
        Returns:
            True if broadcast was successful
        """
        group_name = self._get_account_group(account_id)
        
        event = {
            'type': 'whatsapp_message_sent',
            'message': message,
            'account_id': str(account_id),
            'conversation_id': str(conversation_id) if conversation_id else None
        }
        
        success = self._send_to_group(group_name, event)
        
        if conversation_id:
            conv_group = self._get_conversation_group(conversation_id)
            self._send_to_group(conv_group, event)
        
        return success
    
    def broadcast_status_update(
        self,
        account_id: str,
        message_id: str,
        status: str,
        whatsapp_message_id: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Broadcast a message status update (sent, delivered, read, failed).
        
        Args:
            account_id: WhatsApp account ID
            message_id: Internal message ID
            status: New status (sent, delivered, read, failed)
            whatsapp_message_id: WhatsApp's message ID
            timestamp: When the status changed
        
        Returns:
            True if broadcast was successful
        """
        group_name = self._get_account_group(account_id)
        
        event = {
            'type': 'whatsapp_status_updated',
            'message_id': str(message_id),
            'whatsapp_message_id': whatsapp_message_id,
            'status': status,
            'account_id': str(account_id),
            'timestamp': timestamp.isoformat() if timestamp else timezone.now().isoformat()
        }
        
        success = self._send_to_group(group_name, event)
        
        logger.info(f"Broadcast status update for message {message_id}: {status}")
        return success
    
    def broadcast_conversation_update(
        self,
        account_id: str,
        conversation: Dict[str, Any]
    ) -> bool:
        """
        Broadcast a conversation update (new conversation, status change, etc).
        
        Args:
            account_id: WhatsApp account ID
            conversation: Conversation data dict
        
        Returns:
            True if broadcast was successful
        """
        group_name = self._get_account_group(account_id)
        
        event = {
            'type': 'whatsapp_conversation_updated',
            'conversation': conversation,
            'account_id': str(account_id)
        }
        
        return self._send_to_group(group_name, event)
    
    def broadcast_typing_indicator(
        self,
        account_id: str,
        conversation_id: str,
        is_typing: bool,
        user_id: Optional[int] = None
    ) -> bool:
        """
        Broadcast typing indicator to a conversation.
        
        Args:
            account_id: WhatsApp account ID
            conversation_id: Conversation ID
            is_typing: Whether user is typing
            user_id: ID of user who is typing (for agent typing)
        
        Returns:
            True if broadcast was successful
        """
        conv_group = self._get_conversation_group(conversation_id)
        
        event = {
            'type': 'whatsapp_typing',
            'conversation_id': str(conversation_id),
            'is_typing': is_typing,
            'user_id': user_id
        }
        
        return self._send_to_group(conv_group, event)
    
    def broadcast_error(
        self,
        account_id: str,
        error_code: str,
        error_message: str,
        message_id: Optional[str] = None
    ) -> bool:
        """
        Broadcast an error event.
        
        Args:
            account_id: WhatsApp account ID
            error_code: Error code from Meta API
            error_message: Human-readable error message
            message_id: Related message ID if applicable
        
        Returns:
            True if broadcast was successful
        """
        group_name = self._get_account_group(account_id)
        
        event = {
            'type': 'whatsapp_error',
            'error_code': error_code,
            'error_message': error_message,
            'message_id': str(message_id) if message_id else None,
            'account_id': str(account_id)
        }
        
        return self._send_to_group(group_name, event)


# Singleton instance for convenience
_broadcast_service = None


def get_broadcast_service() -> WhatsAppBroadcastService:
    """Get the singleton broadcast service instance."""
    global _broadcast_service
    if _broadcast_service is None:
        _broadcast_service = WhatsAppBroadcastService()
    return _broadcast_service
