"""
WebSocket Consumers for real-time store updates.
"""
import json
import logging
import asyncio
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
    - pong: Response to ping (heartbeat)
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.store_slug = self.scope['url_route']['kwargs']['store_slug']
        self.room_group_name = f"store_{self.store_slug}_orders"
        self.heartbeat_task = None
        
        logger.info(f"WebSocket connect attempt: store={self.store_slug}, user={self.scope.get('user')}")
        
        # Verify store exists and user has access
        has_access = await self.check_store_access()
        
        if not has_access:
            logger.warning(f"WebSocket access denied: store={self.store_slug}")
            await self.close(code=4003)  # Custom code for access denied
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        logger.info(f"WebSocket connected: store={self.store_slug}, group={self.room_group_name}")
        
        # Send connection confirmation
        await self.send_json({
            'type': 'connection_established',
            'store_slug': self.store_slug,
            'message': 'Connected to order updates',
            'heartbeat_interval': 30  # Tell client to send ping every 30s
        })
        
        # Start server-side heartbeat (optional - mainly for logging)
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeat to keep connection alive."""
        try:
            while True:
                await asyncio.sleep(45)  # Server heartbeat every 45s
                logger.debug(f"WebSocket heartbeat: store={self.store_slug}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"WebSocket heartbeat error: {e}")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        logger.info(f"WebSocket disconnected: store={self.store_slug}, code={close_code}")
        
        # Cancel heartbeat task
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive_json(self, content):
        """Handle incoming messages from client."""
        message_type = content.get('type')
        
        if message_type == 'ping':
            await self.send_json({'type': 'pong', 'timestamp': content.get('timestamp')})
        
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
                logger.debug(f"WebSocket subscribed to order: {order_id}")
    
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
    
    # Alias for order.updated event type
    async def order_updated(self, event):
        """Handle order.updated event (alias for order_update)."""
        await self.order_update(event)
    
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
            
            logger.info(f"WebSocket access check - store: {self.store_slug}, user: {user}, authenticated: {user.is_authenticated if user else False}")
            
            # Check if user is authenticated and has access
            if user and user.is_authenticated:
                # Staff users have access to all stores
                if user.is_staff or user.is_superuser:
                    logger.info(f"WebSocket access granted - staff user: {user.email}")
                    return True
                
                # Store owner has access
                if store.owner == user:
                    logger.info(f"WebSocket access granted - store owner: {user.email}")
                    return True
                
                # Store staff has access
                if hasattr(store, 'staff') and user in store.staff.all():
                    logger.info(f"WebSocket access granted - store staff: {user.email}")
                    return True
                
                # Any authenticated user can access active stores (for dashboard)
                if store.status == 'active':
                    logger.info(f"WebSocket access granted - authenticated user on active store: {user.email}")
                    return True
                
                # FALLBACK: Allow any authenticated user for now (dashboard needs this)
                logger.info(f"WebSocket access granted - authenticated user fallback: {user.email}")
                return True
            
            # Allow anonymous access to active stores for customer tracking
            if store.status == 'active':
                logger.info(f"WebSocket access granted - active store (anonymous)")
                return True
            
            logger.warning(f"WebSocket access denied - store: {self.store_slug}, user: {user}")
            return False
        
        except Store.DoesNotExist:
            logger.error(f"WebSocket access denied - store not found: {self.store_slug}")
            # Try to create default store if it's 'pastita'
            if self.store_slug == 'pastita':
                logger.info("Attempting to create default pastita store...")
                try:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    # Get first superuser or staff
                    owner = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_staff=True).first()
                    if owner:
                        Store.objects.create(
                            name='Pastita',
                            slug='pastita',
                            status='active',
                            owner=owner
                        )
                        logger.info("Created default pastita store")
                        return True
                except Exception as create_error:
                    logger.error(f"Failed to create default store: {create_error}")
            return False
        except Exception as e:
            logger.error(f"WebSocket access check error: {e}")
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
