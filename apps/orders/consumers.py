"""
WebSocket consumers for real-time order updates.
"""
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

logger = logging.getLogger(__name__)
User = get_user_model()


class OrderConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for real-time order status updates."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.user = None
        self.subscribed_orders = set()
        
        # Authenticate from query string
        token = self.scope.get('query_string', b'').decode()
        if token.startswith('token='):
            token = token.split('=')[1]
            self.user = await self.get_user_from_token(token)
        
        if self.user:
            # Join user-specific order group
            self.user_group = f"orders_user_{self.user.id}"
            await self.channel_layer.group_add(self.user_group, self.channel_name)
            
            await self.accept()
            await self.send_json({
                'type': 'connection_established',
                'message': 'Connected to order notification service'
            })
        else:
            await self.close()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        
        # Unsubscribe from all order groups
        for order_id in self.subscribed_orders:
            await self.channel_layer.group_discard(
                f"order_{order_id}",
                self.channel_name
            )
    
    async def receive_json(self, content):
        """Handle incoming WebSocket messages."""
        message_type = content.get('type')
        
        if message_type == 'ping':
            await self.send_json({'type': 'pong'})
        
        elif message_type == 'subscribe_order':
            # Subscribe to updates for a specific order
            order_id = content.get('order_id')
            if order_id and await self.can_access_order(order_id):
                group_name = f"order_{order_id}"
                await self.channel_layer.group_add(group_name, self.channel_name)
                self.subscribed_orders.add(order_id)
                await self.send_json({
                    'type': 'subscribed',
                    'order_id': order_id
                })
        
        elif message_type == 'unsubscribe_order':
            order_id = content.get('order_id')
            if order_id and order_id in self.subscribed_orders:
                group_name = f"order_{order_id}"
                await self.channel_layer.group_discard(group_name, self.channel_name)
                self.subscribed_orders.discard(order_id)
                await self.send_json({
                    'type': 'unsubscribed',
                    'order_id': order_id
                })
    
    async def order_status(self, event):
        """Send order status update to WebSocket."""
        await self.send_json({
            'type': 'order_status',
            'order_id': event.get('order_id'),
            'order_number': event.get('order_number'),
            'status': event.get('status'),
            'previous_status': event.get('previous_status'),
            'tracking_code': event.get('tracking_code'),
            'carrier': event.get('carrier'),
            'timestamp': event.get('timestamp'),
        })
    
    async def order_created(self, event):
        """Send order created notification to WebSocket."""
        await self.send_json({
            'type': 'order_created',
            'order_id': event.get('order_id'),
            'order_number': event.get('order_number'),
            'total': event.get('total'),
            'customer_name': event.get('customer_name'),
            'timestamp': event.get('timestamp'),
        })
    
    async def order_item_added(self, event):
        """Send order item added notification to WebSocket."""
        await self.send_json({
            'type': 'order_item_added',
            'order_id': event.get('order_id'),
            'item': event.get('item'),
            'timestamp': event.get('timestamp'),
        })
    
    async def order_item_removed(self, event):
        """Send order item removed notification to WebSocket."""
        await self.send_json({
            'type': 'order_item_removed',
            'order_id': event.get('order_id'),
            'item_id': event.get('item_id'),
            'timestamp': event.get('timestamp'),
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
    def can_access_order(self, order_id):
        """Check if user can access the order."""
        from .models import Order
        try:
            # For now, allow access if order exists
            # In production, add proper permission checks
            Order.objects.get(id=order_id, is_active=True)
            return True
        except Order.DoesNotExist:
            return False
