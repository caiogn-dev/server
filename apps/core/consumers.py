"""
WebSocket consumers for real-time updates with caching support.
"""
import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.core.cache import cache

from .base_consumer import FirstMessageAuthMixin
from .consumer_cache import get_cached_user_async

logger = logging.getLogger(__name__)
User = get_user_model()


class NotificationConsumer(FirstMessageAuthMixin, AsyncJsonWebsocketConsumer):
    """WebSocket consumer for user notifications."""

    async def _setup_params(self):
        self.user_group = None

    async def _post_auth_connect(self):
        self.user_group = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.send_json({
            'type': 'connection_established',
            'message': 'Connected to notification service',
            'transport': 'websocket',
            'fallback_available': True,
            'sse_endpoint': '/api/sse/notifications/',
        })

    async def disconnect(self, close_code):
        if self.user_group:
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    async def handle_message(self, content):
        message_type = content.get('type')

        if message_type == 'ping':
            await self.send_json({'type': 'pong', 'timestamp': json.dumps(content.get('timestamp'))})
        elif message_type == 'subscribe':
            channel = content.get('channel')
            if channel:
                await self.channel_layer.group_add(channel, self.channel_name)
                await self.send_json({'type': 'subscribed', 'channel': channel})
        elif message_type == 'unsubscribe':
            channel = content.get('channel')
            if channel:
                await self.channel_layer.group_discard(channel, self.channel_name)
                await self.send_json({'type': 'unsubscribed', 'channel': channel})
        elif message_type == 'check_fallback':
            await self.send_json({
                'type': 'fallback_info',
                'websocket': True,
                'sse': '/api/sse/notifications/',
                'polling': '/api/v1/notifications/',
            })

    async def notification_message(self, event):
        await self.send_json({'type': 'notification', 'notification': event['notification']})

    async def message_update(self, event):
        await self.send_json({'type': 'message_update', 'message': event['message']})

    async def order_update(self, event):
        await self.send_json({'type': 'order_update', 'order': event['order']})

    async def conversation_update(self, event):
        await self.send_json({'type': 'conversation_update', 'conversation': event['conversation']})


class ChatConsumer(FirstMessageAuthMixin, AsyncJsonWebsocketConsumer):
    """WebSocket consumer for real-time chat."""

    async def _setup_params(self):
        self.conversation_id = self.scope['url_route']['kwargs'].get('conversation_id')
        self.room_group_name = f"chat_{self.conversation_id}"

    async def _post_auth_connect(self):
        if not self.conversation_id:
            await self.close(code=4000)
            return
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.send_json({
            'type': 'connection_established',
            'conversation_id': self.conversation_id,
            'transport': 'websocket',
            'fallback_available': True,
            'sse_endpoint': f'/api/sse/whatsapp/?conversation_id={self.conversation_id}',
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def handle_message(self, content):
        message_type = content.get('type')

        if message_type == 'typing':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_indicator',
                    'user_id': self.user.id,
                    'is_typing': content.get('is_typing', False),
                }
            )
        elif message_type == 'read':
            message_id = content.get('message_id')
            if message_id:
                await self.mark_message_read(message_id)
        elif message_type == 'ping':
            await self.send_json({'type': 'pong'})

    async def chat_message(self, event):
        await self.send_json({'type': 'message', 'message': event['message']})

    async def typing_indicator(self, event):
        await self.send_json({
            'type': 'typing',
            'user_id': event['user_id'],
            'is_typing': event['is_typing'],
        })

    async def message_status(self, event):
        await self.send_json({
            'type': 'message_status',
            'message_id': event['message_id'],
            'status': event['status'],
        })

    @database_sync_to_async
    def mark_message_read(self, message_id):
        from apps.whatsapp.models import Message
        try:
            message = Message.objects.get(id=message_id)
            if message.status != 'read':
                message.status = 'read'
                message.save(update_fields=['status'])
        except Message.DoesNotExist:
            pass


class DashboardConsumer(FirstMessageAuthMixin, AsyncJsonWebsocketConsumer):
    """WebSocket consumer for dashboard real-time updates."""

    async def _setup_params(self):
        self.account_group = None

    async def _post_auth_connect(self):
        await self.channel_layer.group_add("dashboard", self.channel_name)
        await self.channel_layer.group_add(f"user_{self.user.id}", self.channel_name)
        await self.send_json({
            'type': 'connection_established',
            'message': 'Connected to dashboard service',
            'transport': 'websocket',
            'fallback_available': True,
            'sse_endpoints': {
                'orders': '/api/sse/orders/',
                'whatsapp': '/api/sse/whatsapp/',
            },
        })

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("dashboard", self.channel_name)
        if self.user:
            await self.channel_layer.group_discard(f"user_{self.user.id}", self.channel_name)
        if self.account_group:
            await self.channel_layer.group_discard(self.account_group, self.channel_name)

    async def handle_message(self, content):
        message_type = content.get('type')

        if message_type == 'subscribe_account':
            account_id = content.get('account_id')
            if account_id:
                if self.account_group:
                    await self.channel_layer.group_discard(self.account_group, self.channel_name)
                self.account_group = f"account_{account_id}"
                await self.channel_layer.group_add(self.account_group, self.channel_name)
                await self.send_json({'type': 'subscribed', 'account_id': account_id})
        elif message_type == 'check_health':
            await self.send_json({
                'type': 'health',
                'websocket': True,
                'timestamp': json.dumps(content.get('timestamp')),
            })
        elif message_type == 'ping':
            await self.send_json({'type': 'pong'})

    async def stats_update(self, event):
        await self.send_json({'type': 'stats_update', 'stats': event['stats']})

    async def new_message(self, event):
        await self.send_json({'type': 'new_message', 'message': event['message']})

    async def new_order(self, event):
        await self.send_json({'type': 'new_order', 'order': event['order']})

    async def new_conversation(self, event):
        await self.send_json({'type': 'new_conversation', 'conversation': event['conversation']})
