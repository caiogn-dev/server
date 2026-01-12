"""
WebSocket Consumers for real-time store updates.
"""
import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class StoreOrdersConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for real-time order updates.
    
    Connect: ws://host/ws/stores/{store_slug}/orders/
    
    Events sent to client:
    - order.created: New order created
    - order.updated: Order status changed
    - order.paid: Payment confirmed
    - order.cancelled: Order cancelled
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.store_slug = self.scope['url_route']['kwargs']['store_slug']
        self.room_group_name = f"store_{self.store_slug}_orders"
        
        # Verify store exists and user has access
        has_access = await self.check_store_access()
        
        if not has_access:
            await self.close()
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send connection confirmation
        await self.send_json({
            'type': 'connection_established',
            'store_slug': self.store_slug,
            'message': 'Connected to order updates'
        })
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive_json(self, content):
        """Handle incoming messages from client."""
        message_type = content.get('type')
        
        if message_type == 'ping':
            await self.send_json({'type': 'pong'})
        
        elif message_type == 'subscribe_order':
            # Subscribe to specific order updates
            order_id = content.get('order_id')
            if order_id:
                await self.channel_layer.group_add(
                    f"order_{order_id}",
                    self.channel_name
                )
                await self.send_json({
                    'type': 'subscribed',
                    'order_id': order_id
                })
    
    # Event handlers (called by channel_layer.group_send)
    
    async def order_update(self, event):
        """Handle order update event."""
        await self.send_json({
            'type': 'order.updated',
            'order_id': event['order_id'],
            'order_number': event.get('order_number'),
            'status': event['status'],
            'payment_status': event.get('payment_status'),
            'updated_at': event.get('updated_at'),
        })
    
    async def order_created(self, event):
        """Handle new order event."""
        await self.send_json({
            'type': 'order.created',
            'order_id': event['order_id'],
            'order_number': event.get('order_number'),
            'customer_name': event.get('customer_name'),
            'total': event.get('total'),
            'created_at': event.get('created_at'),
        })
    
    async def order_paid(self, event):
        """Handle order paid event."""
        await self.send_json({
            'type': 'order.paid',
            'order_id': event['order_id'],
            'order_number': event.get('order_number'),
            'paid_at': event.get('paid_at'),
        })
    
    async def order_cancelled(self, event):
        """Handle order cancelled event."""
        await self.send_json({
            'type': 'order.cancelled',
            'order_id': event['order_id'],
            'order_number': event.get('order_number'),
            'cancelled_at': event.get('cancelled_at'),
            'reason': event.get('reason'),
        })
    
    @database_sync_to_async
    def check_store_access(self):
        """Check if user has access to store orders."""
        from apps.stores.models import Store
        
        try:
            store = Store.objects.get(slug=self.store_slug)
            user = self.scope.get('user')
            
            # Allow if store is active (for customer tracking)
            if store.status == 'active':
                return True
            
            # Check if user is owner or staff
            if user and user.is_authenticated:
                if user.is_staff or store.owner == user or user in store.staff.all():
                    return True
            
            return False
        
        except Store.DoesNotExist:
            return False


class CustomerOrderConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for customer order tracking.
    
    Connect: ws://host/ws/orders/{order_id}/
    
    Events sent to client:
    - status_update: Order status changed
    - location_update: Delivery location update (if available)
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.room_group_name = f"order_{self.order_id}"
        
        # Verify order exists
        order_exists = await self.check_order_exists()
        
        if not order_exists:
            await self.close()
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send current order status
        order_data = await self.get_order_data()
        await self.send_json({
            'type': 'connection_established',
            'order': order_data
        })
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive_json(self, content):
        """Handle incoming messages from client."""
        message_type = content.get('type')
        
        if message_type == 'ping':
            await self.send_json({'type': 'pong'})
        
        elif message_type == 'get_status':
            order_data = await self.get_order_data()
            await self.send_json({
                'type': 'status_update',
                'order': order_data
            })
    
    async def order_update(self, event):
        """Handle order update event."""
        await self.send_json({
            'type': 'status_update',
            'order_id': event['order_id'],
            'status': event['status'],
            'payment_status': event.get('payment_status'),
            'updated_at': event.get('updated_at'),
        })
    
    @database_sync_to_async
    def check_order_exists(self):
        """Check if order exists."""
        from apps.stores.models import StoreOrder
        return StoreOrder.objects.filter(id=self.order_id).exists()
    
    @database_sync_to_async
    def get_order_data(self):
        """Get current order data."""
        from apps.stores.models import StoreOrder
        
        try:
            order = StoreOrder.objects.select_related('store').get(id=self.order_id)
            return {
                'id': str(order.id),
                'order_number': order.order_number,
                'store_name': order.store.name,
                'status': order.status,
                'payment_status': order.payment_status,
                'total': float(order.total),
                'delivery_method': order.delivery_method,
                'created_at': order.created_at.isoformat(),
                'updated_at': order.updated_at.isoformat(),
                'estimated_delivery': order.metadata.get('estimated_minutes'),
            }
        except StoreOrder.DoesNotExist:
            return None
