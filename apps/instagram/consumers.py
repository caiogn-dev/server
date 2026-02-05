"""
Instagram WebSocket consumers for real-time message updates.
"""
import json
import logging
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from apps.core.base_consumer import ThrottledWebSocketConsumer

logger = logging.getLogger(__name__)
User = get_user_model()


class InstagramConsumer(ThrottledWebSocketConsumer):
    """
    WebSocket consumer for Instagram DM real-time updates.
    
    Clients connect to: ws/instagram/{account_id}/
    
    Events sent to clients:
    - instagram_message_received: New inbound message
    - instagram_message_sent: Outbound message confirmation
    - instagram_message_seen: Message read status
    - instagram_typing: Typing indicator
    - instagram_story_mention: Story mention notification
    - instagram_story_reply: Story reply notification
    """
    
    # Throttling: Limit events per second
    THROTTLE_RATE = 5  # Max 5 events per second
    THROTTLE_WINDOW = 1.0  # 1 second window
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event_timestamps = []  # Track recent event times
        self.throttled_count = 0
    
    def _should_throttle(self) -> bool:
        """Check if we should throttle based on recent event rate."""
        import time
        now = time.time()
        
        # Remove old timestamps outside window
        self.event_timestamps = [
            ts for ts in self.event_timestamps 
            if now - ts < self.THROTTLE_WINDOW
        ]
        
        # Check if we exceeded rate
        if len(self.event_timestamps) >= self.THROTTLE_RATE:
            self.throttled_count += 1
            if self.throttled_count % 10 == 1:  # Log every 10th throttle
                logger.warning(
                    f"Instagram WS throttling: {len(self.event_timestamps)} events in {self.THROTTLE_WINDOW}s",
                    extra={'account_id': self.account_id}
                )
            return True
        
        # Add current timestamp
        self.event_timestamps.append(now)
        return False
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.account_id = self.scope['url_route']['kwargs'].get('account_id')
        self.user = None
        self.account_group = None
        self.conversation_groups = set()
        
        # Authenticate via token in query string
        query_string = self.scope.get('query_string', b'').decode()
        token = self._extract_token(query_string)
        
        if token:
            self.user = await self.get_user_from_token(token)
        
        if not self.user:
            logger.warning(f"Instagram WS: Unauthorized connection attempt for account {self.account_id}")
            await self.close(code=4001)
            return
        
        # Verify user has access to this account
        has_access = await self.verify_account_access(self.account_id)
        if not has_access:
            logger.warning(f"Instagram WS: User {self.user.id} denied access to account {self.account_id}")
            await self.close(code=4003)
            return
        
        # Join account-specific group
        self.account_group = f"instagram_{self.account_id}"
        await self.channel_layer.group_add(self.account_group, self.channel_name)
        
        # Also join user-specific group for cross-account notifications
        await self.channel_layer.group_add(f"user_{self.user.id}_instagram", self.channel_name)
        
        await self.accept()
        
        logger.info(f"Instagram WS: User {self.user.id} connected to account {self.account_id}")
        
        await self.send_json({
            'type': 'connection_established',
            'account_id': self.account_id,
            'message': 'Connected to Instagram DM real-time service'
        })
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if self.account_group:
            await self.channel_layer.group_discard(self.account_group, self.channel_name)
        
        if self.user:
            await self.channel_layer.group_discard(f"user_{self.user.id}_instagram", self.channel_name)
        
        # Leave all conversation groups
        for group in self.conversation_groups:
            await self.channel_layer.group_discard(group, self.channel_name)
        
        logger.info(f"Instagram WS: Disconnected from account {self.account_id}")
    
    async def receive_json(self, content):
        """Handle incoming WebSocket messages from client."""
        message_type = content.get('type')
        
        if message_type == 'ping':
            await self.send_json({'type': 'pong'})
        
        elif message_type == 'subscribe_conversation':
            # Subscribe to a specific conversation for typing indicators
            conversation_id = content.get('conversation_id')
            if conversation_id:
                group_name = f"instagram_conv_{conversation_id}"
                await self.channel_layer.group_add(group_name, self.channel_name)
                self.conversation_groups.add(group_name)
                await self.send_json({
                    'type': 'subscribed',
                    'conversation_id': conversation_id
                })
        
        elif message_type == 'unsubscribe_conversation':
            conversation_id = content.get('conversation_id')
            if conversation_id:
                group_name = f"instagram_conv_{conversation_id}"
                await self.channel_layer.group_discard(group_name, self.channel_name)
                self.conversation_groups.discard(group_name)
                await self.send_json({
                    'type': 'unsubscribed',
                    'conversation_id': conversation_id
                })
        
        elif message_type == 'typing_start':
            conversation_id = content.get('conversation_id')
            if conversation_id:
                await self.channel_layer.group_send(
                    f"instagram_conv_{conversation_id}",
                    {
                        'type': 'typing_indicator',
                        'conversation_id': conversation_id,
                        'user_id': str(self.user.id),
                        'is_typing': True
                    }
                )
        
        elif message_type == 'typing_stop':
            conversation_id = content.get('conversation_id')
            if conversation_id:
                await self.channel_layer.group_send(
                    f"instagram_conv_{conversation_id}",
                    {
                        'type': 'typing_indicator',
                        'conversation_id': conversation_id,
                        'user_id': str(self.user.id),
                        'is_typing': False
                    }
                )
    
    # === Event handlers (called by channel_layer.group_send) ===
    
    async def instagram_message_received(self, event):
        """Handle new inbound message."""
        if self._should_throttle():
            return
        
        await self.send_json({
            'type': 'message_received',
            'message': event.get('message'),
            'conversation': event.get('conversation'),
            'sender': event.get('sender'),
        })
    
    async def instagram_message_sent(self, event):
        """Handle outbound message confirmation."""
        if self._should_throttle():
            return
        
        await self.send_json({
            'type': 'message_sent',
            'message': event.get('message'),
            'conversation_id': event.get('conversation_id'),
        })
    
    async def instagram_message_seen(self, event):
        """Handle message read status update."""
        await self.send_json({
            'type': 'message_seen',
            'message_id': event.get('message_id'),
            'conversation_id': event.get('conversation_id'),
            'seen_at': event.get('seen_at'),
        })
    
    async def instagram_story_mention(self, event):
        """Handle story mention notification."""
        await self.send_json({
            'type': 'story_mention',
            'conversation': event.get('conversation'),
            'story_url': event.get('story_url'),
            'sender': event.get('sender'),
        })
    
    async def instagram_story_reply(self, event):
        """Handle story reply notification."""
        await self.send_json({
            'type': 'story_reply',
            'message': event.get('message'),
            'conversation': event.get('conversation'),
            'story_url': event.get('story_url'),
            'sender': event.get('sender'),
        })
    
    async def typing_indicator(self, event):
        """Handle typing indicator."""
        # Don't send back to the sender
        if event.get('user_id') != str(self.user.id):
            await self.send_json({
                'type': 'typing',
                'conversation_id': event.get('conversation_id'),
                'user_id': event.get('user_id'),
                'is_typing': event.get('is_typing'),
            })
    
    async def conversation_updated(self, event):
        """Handle conversation update (new unread count, status change, etc.)."""
        if self._should_throttle():
            return
        
        await self.send_json({
            'type': 'conversation_updated',
            'conversation': event.get('conversation'),
        })
    
    # === Helper methods ===
    
    def _extract_token(self, query_string: str) -> str:
        """Extract token from query string."""
        params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
        return params.get('token', '')
    
    @database_sync_to_async
    def get_user_from_token(self, token_key: str):
        """Get user from authentication token."""
        try:
            token = Token.objects.select_related('user').get(key=token_key)
            return token.user
        except Token.DoesNotExist:
            return None
    
    @database_sync_to_async
    def verify_account_access(self, account_id: str) -> bool:
        """Verify user has access to the Instagram account."""
        from .models import IGAccount
        
        if not account_id:
            return False
        
        try:
            # Check if user owns the account or is superuser
            account = IGAccount.objects.get(id=account_id)
            return account.owner == self.user or self.user.is_superuser
        except IGAccount.DoesNotExist:
            return False


# Broadcast helper functions (to be called from services)
def broadcast_instagram_message(account_id: str, message_data: dict, conversation_data: dict, sender_data: dict = None):
    """
    Broadcast a new Instagram message to connected WebSocket clients.
    
    Call this from services when a new message is received/sent.
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    channel_layer = get_channel_layer()
    
    async_to_sync(channel_layer.group_send)(
        f"instagram_{account_id}",
        {
            'type': 'instagram_message_received',
            'message': message_data,
            'conversation': conversation_data,
            'sender': sender_data,
        }
    )


def broadcast_instagram_message_sent(account_id: str, message_data: dict, conversation_id: str):
    """
    Broadcast confirmation of sent message.
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    channel_layer = get_channel_layer()
    
    async_to_sync(channel_layer.group_send)(
        f"instagram_{account_id}",
        {
            'type': 'instagram_message_sent',
            'message': message_data,
            'conversation_id': conversation_id,
        }
    )


def broadcast_instagram_message_seen(account_id: str, message_id: str, conversation_id: str, seen_at: str):
    """
    Broadcast message seen status update.
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    channel_layer = get_channel_layer()
    
    async_to_sync(channel_layer.group_send)(
        f"instagram_{account_id}",
        {
            'type': 'instagram_message_seen',
            'message_id': message_id,
            'conversation_id': conversation_id,
            'seen_at': seen_at,
        }
    )


def broadcast_instagram_story_mention(account_id: str, conversation_data: dict, story_url: str, sender_data: dict):
    """
    Broadcast story mention notification.
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    channel_layer = get_channel_layer()
    
    async_to_sync(channel_layer.group_send)(
        f"instagram_{account_id}",
        {
            'type': 'instagram_story_mention',
            'conversation': conversation_data,
            'story_url': story_url,
            'sender': sender_data,
        }
    )


def broadcast_conversation_updated(account_id: str, conversation_data: dict):
    """
    Broadcast conversation update (unread count, status, etc.).
    """
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    channel_layer = get_channel_layer()
    
    async_to_sync(channel_layer.group_send)(
        f"instagram_{account_id}",
        {
            'type': 'conversation_updated',
            'conversation': conversation_data,
        }
    )
