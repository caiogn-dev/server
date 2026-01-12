"""
WebSocket consumers for real-time updates.
"""
import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

logger = logging.getLogger(__name__)
User = get_user_model()


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for user notifications."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.user = None
        self.user_group = None
        
        # Try to authenticate from query string
        token = self.scope.get('query_string', b'').decode()
        if token.startswith('token='):
            token = token.split('=')[1]
            self.user = await self.get_user_from_token(token)
        
        if self.user:
            self.user_group = f"user_{self.user.id}"
            await self.channel_layer.group_add(self.user_group, self.channel_name)
            await self.accept()
            await self.send_json({
                'type': 'connection_established',
                'message': 'Connected to notification service'
            })
        else:
            await self.close()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if self.user_group:
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
    
    async def receive_json(self, content):
        """Handle incoming WebSocket messages."""
        message_type = content.get('type')
        
        if message_type == 'ping':
            await self.send_json({'type': 'pong'})
        elif message_type == 'subscribe':
            # Handle subscription to specific channels
            channel = content.get('channel')
            if channel:
                await self.channel_layer.group_add(channel, self.channel_name)
                await self.send_json({
                    'type': 'subscribed',
                    'channel': channel
                })
        elif message_type == 'unsubscribe':
            channel = content.get('channel')
            if channel:
                await self.channel_layer.group_discard(channel, self.channel_name)
                await self.send_json({
                    'type': 'unsubscribed',
                    'channel': channel
                })
    
    async def notification_message(self, event):
        """Send notification to WebSocket."""
        await self.send_json({
            'type': 'notification',
            'notification': event['notification']
        })
    
    async def message_update(self, event):
        """Send message update to WebSocket."""
        await self.send_json({
            'type': 'message_update',
            'message': event['message']
        })
    
    async def order_update(self, event):
        """Send order update to WebSocket."""
        await self.send_json({
            'type': 'order_update',
            'order': event['order']
        })
    
    async def conversation_update(self, event):
        """Send conversation update to WebSocket."""
        await self.send_json({
            'type': 'conversation_update',
            'conversation': event['conversation']
        })
    
    @database_sync_to_async
    def get_user_from_token(self, token_key):
        """Get user from auth token."""
        try:
            token = Token.objects.select_related('user').get(key=token_key)
            return token.user
        except Token.DoesNotExist:
            return None


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for real-time chat."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.conversation_id = self.scope['url_route']['kwargs'].get('conversation_id')
        self.room_group_name = f"chat_{self.conversation_id}"
        self.user = None
        
        # Authenticate
        token = self.scope.get('query_string', b'').decode()
        if token.startswith('token='):
            token = token.split('=')[1]
            self.user = await self.get_user_from_token(token)
        
        if self.user and self.conversation_id:
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.accept()
            await self.send_json({
                'type': 'connection_established',
                'conversation_id': self.conversation_id
            })
        else:
            await self.close()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
    
    async def receive_json(self, content):
        """Handle incoming chat messages."""
        message_type = content.get('type')
        
        if message_type == 'typing':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_indicator',
                    'user_id': self.user.id,
                    'is_typing': content.get('is_typing', False)
                }
            )
        elif message_type == 'read':
            message_id = content.get('message_id')
            if message_id:
                await self.mark_message_read(message_id)
    
    async def chat_message(self, event):
        """Send chat message to WebSocket."""
        await self.send_json({
            'type': 'message',
            'message': event['message']
        })
    
    async def typing_indicator(self, event):
        """Send typing indicator to WebSocket."""
        await self.send_json({
            'type': 'typing',
            'user_id': event['user_id'],
            'is_typing': event['is_typing']
        })
    
    async def message_status(self, event):
        """Send message status update to WebSocket."""
        await self.send_json({
            'type': 'message_status',
            'message_id': event['message_id'],
            'status': event['status']
        })
    
    @database_sync_to_async
    def get_user_from_token(self, token_key):
        """Get user from auth token."""
        try:
            token = Token.objects.select_related('user').get(key=token_key)
            return token.user
        except Token.DoesNotExist:
            return None
    
    @database_sync_to_async
    def mark_message_read(self, message_id):
        """Mark a message as read."""
        from apps.whatsapp.models import Message
        try:
            message = Message.objects.get(id=message_id)
            if message.status != 'read':
                message.status = 'read'
                message.save(update_fields=['status'])
        except Message.DoesNotExist:
            pass


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for dashboard real-time updates."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.user = None
        self.account_group = None
        
        # Authenticate
        token = self.scope.get('query_string', b'').decode()
        if token.startswith('token='):
            token = token.split('=')[1]
            self.user = await self.get_user_from_token(token)
        
        if self.user:
            # Join general dashboard group
            await self.channel_layer.group_add("dashboard", self.channel_name)
            
            # Join user-specific group
            await self.channel_layer.group_add(f"user_{self.user.id}", self.channel_name)
            
            await self.accept()
            await self.send_json({
                'type': 'connection_established',
                'message': 'Connected to dashboard service'
            })
        else:
            await self.close()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        await self.channel_layer.group_discard("dashboard", self.channel_name)
        if self.user:
            await self.channel_layer.group_discard(f"user_{self.user.id}", self.channel_name)
        if self.account_group:
            await self.channel_layer.group_discard(self.account_group, self.channel_name)
    
    async def receive_json(self, content):
        """Handle incoming messages."""
        message_type = content.get('type')
        
        if message_type == 'subscribe_account':
            account_id = content.get('account_id')
            if account_id:
                if self.account_group:
                    await self.channel_layer.group_discard(self.account_group, self.channel_name)
                self.account_group = f"account_{account_id}"
                await self.channel_layer.group_add(self.account_group, self.channel_name)
                await self.send_json({
                    'type': 'subscribed',
                    'account_id': account_id
                })
    
    async def stats_update(self, event):
        """Send stats update to WebSocket."""
        await self.send_json({
            'type': 'stats_update',
            'stats': event['stats']
        })
    
    async def new_message(self, event):
        """Send new message notification to WebSocket."""
        await self.send_json({
            'type': 'new_message',
            'message': event['message']
        })
    
    async def new_order(self, event):
        """Send new order notification to WebSocket."""
        await self.send_json({
            'type': 'new_order',
            'order': event['order']
        })
    
    async def new_conversation(self, event):
        """Send new conversation notification to WebSocket."""
        await self.send_json({
            'type': 'new_conversation',
            'conversation': event['conversation']
        })
    
    @database_sync_to_async
    def get_user_from_token(self, token_key):
        """Get user from auth token."""
        try:
            token = Token.objects.select_related('user').get(key=token_key)
            return token.user
        except Token.DoesNotExist:
            return None
