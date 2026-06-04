"""WebSocket consumers for store real-time updates."""
import json
import asyncio
import logging
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

from apps.core.websocket_auth import validate_websocket_token
from apps.core.websocket_listeners import generate_listener_id
from apps.core.websocket_heartbeat import create_heartbeat_message

logger = logging.getLogger(__name__)
User = get_user_model()


class OrderConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for store order real-time updates.

    Implements:
    - Auth validation BEFORE accept (rejects 4001 if invalid)
    - Heartbeat ping every 30s (prevents proxy timeout)
    - Listener deduplication (one listener per user+store)
    """

    async def connect(self):
        """Handle WebSocket connection - validate auth BEFORE accepting."""
        # Parse store slug from URL
        self.store_slug = self.scope['url_route']['kwargs'].get('store_slug')
        if not self.store_slug:
            await self.close(code=4000)  # Invalid route
            return

        # Get token from query string
        query_params = {}
        if self.scope.get('query_string'):
            query_string = self.scope['query_string'].decode()
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    query_params[key] = value

        token_key = query_params.get('token')
        if not token_key:
            await self.close(code=4001)  # Auth required
            return

        # Validate token synchronously via database
        self.user = await self._validate_token(token_key)
        if not self.user:
            await self.close(code=4001)  # Invalid token
            return

        # Auth successful - accept connection
        await self.accept()

        # Generate dedup listener ID and join group
        self.listener_id = generate_listener_id(self.user.id, self.store_slug)
        self.group_name = f'store_{self.store_slug}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        # Start heartbeat task
        self.heartbeat_task = asyncio.create_task(self._send_heartbeat())

        logger.info(
            f'WebSocket connected',
            extra={
                'user_id': self.user.id,
                'store_slug': self.store_slug,
                'listener_id': self.listener_id,
            }
        )

    async def disconnect(self, close_code):
        """Handle disconnection - cleanup listeners."""
        # Cancel heartbeat
        if hasattr(self, 'heartbeat_task'):
            self.heartbeat_task.cancel()

        # Leave group (dedup listener gone)
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

        logger.info(
            f'WebSocket disconnected',
            extra={
                'user_id': self.user.id if hasattr(self, 'user') else None,
                'store_slug': self.store_slug if hasattr(self, 'store_slug') else None,
                'close_code': close_code,
            }
        )

    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming messages from client."""
        if not text_data:
            return

        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'pong':
                # Client responding to heartbeat
                pass
        except json.JSONDecodeError:
            logger.warning('Invalid JSON received')

    async def order_updated(self, event):
        """Handle order.updated message from group."""
        await self.send(text_data=json.dumps({
            'type': 'order.updated',
            'order_id': event.get('order_id'),
            'status': event.get('status'),
            'timestamp': datetime.now().isoformat(),
        }))

    async def _send_heartbeat(self):
        """Send heartbeat ping every 30 seconds."""
        try:
            while True:
                await asyncio.sleep(30)
                heartbeat = create_heartbeat_message()
                await self.send(text_data=json.dumps(heartbeat))
        except asyncio.CancelledError:
            pass

    @database_sync_to_async
    def _validate_token(self, token_key: str):
        """Validate token synchronously (runs in thread pool)."""
        return validate_websocket_token(token_key)
