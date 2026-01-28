"""
WhatsApp WebSocket consumers for real-time message updates.
"""
import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

logger = logging.getLogger(__name__)
User = get_user_model()


class WhatsAppConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for WhatsApp real-time updates.
    
    Clients connect to: ws/whatsapp/{account_id}/
    
    Events sent to clients:
    - whatsapp_message_received: New inbound message
    - whatsapp_message_sent: Outbound message confirmation
    - whatsapp_status_updated: Message status change (sent, delivered, read)
    - whatsapp_typing: Typing indicator
    """
    
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
            logger.warning(f"WhatsApp WS: Unauthorized connection attempt for account {self.account_id}")
            await self.close(code=4001)
            return
        
        # Verify user has access to this account
        has_access = await self.verify_account_access(self.account_id)
        if not has_access:
            logger.warning(f"WhatsApp WS: User {self.user.id} denied access to account {self.account_id}")
            await self.close(code=4003)
            return
        
        # Join account-specific group
        self.account_group = f"whatsapp_{self.account_id}"
        await self.channel_layer.group_add(self.account_group, self.channel_name)
        
        # Also join user-specific group for cross-account notifications
        await self.channel_layer.group_add(f"user_{self.user.id}_whatsapp", self.channel_name)
        
        await self.accept()
        
        logger.info(f"WhatsApp WS: User {self.user.id} connected to account {self.account_id}")
        
        await self.send_json({
            'type': 'connection_established',
            'account_id': self.account_id,
            'message': 'Connected to WhatsApp real-time service'
        })
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if self.account_group:
            await self.channel_layer.group_discard(self.account_group, self.channel_name)
        
        if self.user:
            await self.channel_layer.group_discard(f"user_{self.user.id}_whatsapp", self.channel_name)
        
        # Leave all conversation groups
        for group in self.conversation_groups:
            await self.channel_layer.group_discard(group, self.channel_name)
        
        logger.info(f"WhatsApp WS: Disconnected from account {self.account_id}")
    
    async def receive_json(self, content):
        """Handle incoming WebSocket messages from client."""
        message_type = content.get('type')
        
        if message_type == 'ping':
            await self.send_json({'type': 'pong'})
        
        elif message_type == 'subscribe_conversation':
            # Subscribe to a specific conversation for typing indicators
            conversation_id = content.get('conversation_id')
            if conversation_id:
                group_name = f"whatsapp_conv_{conversation_id}"
                await self.channel_layer.group_add(group_name, self.channel_name)
                self.conversation_groups.add(group_name)
                await self.send_json({
                    'type': 'subscribed',
                    'conversation_id': conversation_id
                })
        
        elif message_type == 'unsubscribe_conversation':
            conversation_id = content.get('conversation_id')
            if conversation_id:
                group_name = f"whatsapp_conv_{conversation_id}"
                await self.channel_layer.group_discard(group_name, self.channel_name)
                self.conversation_groups.discard(group_name)
                await self.send_json({
                    'type': 'unsubscribed',
                    'conversation_id': conversation_id
                })
        
        elif message_type == 'typing':
            # Broadcast typing indicator to conversation
            conversation_id = content.get('conversation_id')
            is_typing = content.get('is_typing', False)
            if conversation_id:
                await self.channel_layer.group_send(
                    f"whatsapp_conv_{conversation_id}",
                    {
                        'type': 'whatsapp_typing',
                        'user_id': self.user.id,
                        'conversation_id': conversation_id,
                        'is_typing': is_typing
                    }
                )
        
        elif message_type == 'mark_read':
            # Mark messages as read (will be processed by API, this is just for UI sync)
            message_ids = content.get('message_ids', [])
            if message_ids:
                await self.send_json({
                    'type': 'read_receipt_sent',
                    'message_ids': message_ids
                })
    
    # ==================== Event Handlers ====================
    # These are called by channel_layer.group_send from the broadcast service
    
    async def whatsapp_message_received(self, event):
        """Handle new inbound message event."""
        await self.send_json({
            'type': 'message_received',
            'message': event['message'],
            'conversation_id': event.get('conversation_id'),
            'contact': event.get('contact')
        })
    
    async def whatsapp_message_sent(self, event):
        """Handle outbound message confirmation."""
        await self.send_json({
            'type': 'message_sent',
            'message': event['message'],
            'conversation_id': event.get('conversation_id')
        })
    
    async def whatsapp_status_updated(self, event):
        """Handle message status update (sent, delivered, read)."""
        await self.send_json({
            'type': 'status_updated',
            'message_id': event['message_id'],
            'whatsapp_message_id': event.get('whatsapp_message_id'),
            'status': event['status'],
            'timestamp': event.get('timestamp')
        })
    
    async def whatsapp_typing(self, event):
        """Handle typing indicator."""
        # Don't send typing indicator to the user who is typing
        if event.get('user_id') != self.user.id:
            await self.send_json({
                'type': 'typing',
                'conversation_id': event['conversation_id'],
                'is_typing': event['is_typing']
            })
    
    async def whatsapp_conversation_updated(self, event):
        """Handle conversation update (new conversation, status change, etc)."""
        await self.send_json({
            'type': 'conversation_updated',
            'conversation': event['conversation']
        })
    
    async def whatsapp_error(self, event):
        """Handle error event."""
        await self.send_json({
            'type': 'error',
            'error_code': event.get('error_code'),
            'error_message': event.get('error_message'),
            'message_id': event.get('message_id')
        })
    
    # ==================== Helper Methods ====================
    
    def _extract_token(self, query_string: str) -> str:
        """Extract token from query string."""
        if not query_string:
            return ''
        
        params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
        return params.get('token', '')
    
    @database_sync_to_async
    def get_user_from_token(self, token_key: str):
        """Get user from auth token."""
        try:
            token = Token.objects.select_related('user').get(key=token_key)
            return token.user
        except Token.DoesNotExist:
            return None
    
    @database_sync_to_async
    def verify_account_access(self, account_id: str) -> bool:
        """Verify user has access to the WhatsApp account."""
        from .models import WhatsAppAccount
        
        try:
            account = WhatsAppAccount.objects.get(id=account_id)
            # Check if user is owner or has permission
            if account.owner_id == self.user.id:
                return True
            # Staff users have access to all accounts
            if self.user.is_staff:
                return True
            # TODO: Add more granular permission checks if needed
            return False
        except WhatsAppAccount.DoesNotExist:
            return False


class WhatsAppDashboardConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for WhatsApp dashboard overview.
    
    Provides aggregated updates across all accounts the user has access to.
    Clients connect to: ws/whatsapp/dashboard/
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.user = None
        self.account_groups = set()
        
        # Authenticate
        query_string = self.scope.get('query_string', b'').decode()
        token = self._extract_token(query_string)
        
        if token:
            self.user = await self.get_user_from_token(token)
        
        if not self.user:
            await self.close(code=4001)
            return
        
        # Get all accounts user has access to and join their groups
        account_ids = await self.get_user_account_ids()
        
        for account_id in account_ids:
            group_name = f"whatsapp_{account_id}"
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.account_groups.add(group_name)
        
        # Join user-specific group
        await self.channel_layer.group_add(f"user_{self.user.id}_whatsapp", self.channel_name)
        
        await self.accept()
        
        await self.send_json({
            'type': 'connection_established',
            'accounts': account_ids,
            'message': 'Connected to WhatsApp dashboard service'
        })
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        for group in self.account_groups:
            await self.channel_layer.group_discard(group, self.channel_name)
        
        if self.user:
            await self.channel_layer.group_discard(f"user_{self.user.id}_whatsapp", self.channel_name)
    
    async def receive_json(self, content):
        """Handle incoming messages."""
        message_type = content.get('type')
        
        if message_type == 'ping':
            await self.send_json({'type': 'pong'})
    
    # Event handlers - same as WhatsAppConsumer
    async def whatsapp_message_received(self, event):
        await self.send_json({
            'type': 'message_received',
            'message': event['message'],
            'account_id': event.get('account_id'),
            'conversation_id': event.get('conversation_id')
        })
    
    async def whatsapp_status_updated(self, event):
        await self.send_json({
            'type': 'status_updated',
            'message_id': event['message_id'],
            'status': event['status'],
            'account_id': event.get('account_id')
        })
    
    async def whatsapp_conversation_updated(self, event):
        await self.send_json({
            'type': 'conversation_updated',
            'conversation': event['conversation'],
            'account_id': event.get('account_id')
        })
    
    def _extract_token(self, query_string: str) -> str:
        if not query_string:
            return ''
        params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
        return params.get('token', '')
    
    @database_sync_to_async
    def get_user_from_token(self, token_key: str):
        try:
            token = Token.objects.select_related('user').get(key=token_key)
            return token.user
        except Token.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_user_account_ids(self) -> list:
        """Get all WhatsApp account IDs the user has access to."""
        from .models import WhatsAppAccount
        
        if self.user.is_staff:
            # Staff can see all accounts
            return list(WhatsAppAccount.objects.values_list('id', flat=True))
        else:
            # Regular users see only their accounts
            return list(
                WhatsAppAccount.objects.filter(owner=self.user).values_list('id', flat=True)
            )
