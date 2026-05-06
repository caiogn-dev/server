"""
WebSocket Consumers for real-time store updates.
"""
import json
import logging
import asyncio
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from apps.core.base_consumer import FirstMessageAuthMixin

logger = logging.getLogger(__name__)
User = get_user_model()


def user_can_access_store_orders(user, store_slug: str) -> bool:
    """Return whether a user can subscribe to a store's operational order feed."""
    from apps.stores.models import Store

    try:
        store = Store.objects.get(slug=store_slug)
    except Store.DoesNotExist:
        logger.error(f"WebSocket access denied - store not found: {store_slug}")
        return False

    logger.info(
        "WebSocket access check - store: %s, user: %s, authenticated: %s",
        store_slug,
        user,
        user.is_authenticated if user else False,
    )

    if not user or not user.is_authenticated:
        logger.warning("WebSocket access denied - unauthenticated order dashboard socket")
        return False

    if user.is_staff or user.is_superuser:
        logger.info(f"WebSocket access granted - staff user: {user.email}")
        return True

    if store.owner_id == user.id:
        logger.info(f"WebSocket access granted - store owner: {user.email}")
        return True

    if store.staff.filter(id=user.id).exists():
        logger.info(f"WebSocket access granted - store staff: {user.email}")
        return True

    logger.warning(f"WebSocket access denied - store: {store_slug}, user: {user}")
    return False


def user_can_access_customer_order(user, order_id: str, token: str = '') -> bool:
    """Return whether a socket may track a single customer-facing order."""
    from apps.stores.models import StoreOrder

    try:
        order = StoreOrder.objects.select_related('store').get(id=order_id)
    except StoreOrder.DoesNotExist:
        logger.error("Customer order WebSocket denied - order not found: %s", order_id)
        return False

    if token and order.access_token and token == order.access_token:
        return True

    if user and user.is_authenticated:
        if user.is_staff or user.is_superuser:
            return True
        if order.store.owner_id == user.id:
            return True
        if order.store.staff.filter(id=user.id).exists():
            return True

    logger.warning("Customer order WebSocket denied - order: %s, user: %s", order_id, user)
    return False


class StoreOrdersConsumer(FirstMessageAuthMixin, AsyncJsonWebsocketConsumer):
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

    async def _setup_params(self):
        self.store_slug = self.scope['url_route']['kwargs']['store_slug']
        self.room_group_name = f"store_{self.store_slug}_orders"
        self.heartbeat_task = None

    async def _post_auth_connect(self):
        logger.info("WebSocket connect attempt: store=%s, user=%s", self.store_slug, self.user)

        has_access = await self.check_store_access()
        if not has_access:
            logger.warning("WebSocket access denied: store=%s", self.store_slug)
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        logger.info("WebSocket connected: store=%s, group=%s", self.store_slug, self.room_group_name)
        await self.send_json({
            'type': 'connection_established',
            'store_slug': self.store_slug,
            'message': 'Connected to order updates',
            'heartbeat_interval': 30,
        })

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

    async def handle_message(self, content):
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
        try:
            return user_can_access_store_orders(self.scope.get('user'), self.store_slug)
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
        query_params = parse_qs(self.scope.get('query_string', b'').decode())
        self.access_token = (query_params.get('token') or [''])[0]
        
        # Verify order access. Public clients must present the order access token.
        order_allowed = await self.check_order_access()
        
        if not order_allowed:
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
    def check_order_access(self):
        """Check if the current socket can track this order."""
        return user_can_access_customer_order(
            self.scope.get('user'),
            self.order_id,
            self.access_token,
        )
    
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
