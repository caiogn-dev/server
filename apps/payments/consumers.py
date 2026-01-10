"""
WebSocket consumers for real-time payment updates.
"""
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

logger = logging.getLogger(__name__)
User = get_user_model()


class PaymentConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for real-time payment status updates."""
    
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
            # Join user-specific payment group
            self.user_group = f"payments_user_{self.user.id}"
            await self.channel_layer.group_add(self.user_group, self.channel_name)
            
            await self.accept()
            await self.send_json({
                'type': 'connection_established',
                'message': 'Connected to payment notification service'
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
                f"payment_order_{order_id}",
                self.channel_name
            )
    
    async def receive_json(self, content):
        """Handle incoming WebSocket messages."""
        message_type = content.get('type')
        
        if message_type == 'ping':
            await self.send_json({'type': 'pong'})
        
        elif message_type == 'subscribe_order':
            # Subscribe to payment updates for a specific order
            order_id = content.get('order_id')
            if order_id and await self.can_access_order(order_id):
                group_name = f"payment_order_{order_id}"
                await self.channel_layer.group_add(group_name, self.channel_name)
                self.subscribed_orders.add(order_id)
                await self.send_json({
                    'type': 'subscribed',
                    'order_id': order_id
                })
        
        elif message_type == 'unsubscribe_order':
            order_id = content.get('order_id')
            if order_id and order_id in self.subscribed_orders:
                group_name = f"payment_order_{order_id}"
                await self.channel_layer.group_discard(group_name, self.channel_name)
                self.subscribed_orders.discard(order_id)
                await self.send_json({
                    'type': 'unsubscribed',
                    'order_id': order_id
                })
    
    async def payment_status(self, event):
        """Send payment status update to WebSocket."""
        await self.send_json({
            'type': 'payment_status',
            'order_id': event.get('order_id'),
            'payment_id': event.get('payment_id'),
            'status': event.get('status'),
            'payment_method': event.get('payment_method'),
            'amount': event.get('amount'),
            'error_code': event.get('error_code'),
            'error_message': event.get('error_message'),
            'timestamp': event.get('timestamp'),
        })
    
    async def payment_created(self, event):
        """Send payment created notification to WebSocket."""
        await self.send_json({
            'type': 'payment_created',
            'order_id': event.get('order_id'),
            'payment_id': event.get('payment_id'),
            'payment_method': event.get('payment_method'),
            'amount': event.get('amount'),
            'checkout_url': event.get('checkout_url'),
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
        from apps.orders.models import Order
        try:
            # For now, allow access if order exists
            # In production, add proper permission checks
            Order.objects.get(id=order_id, is_active=True)
            return True
        except Order.DoesNotExist:
            return False
