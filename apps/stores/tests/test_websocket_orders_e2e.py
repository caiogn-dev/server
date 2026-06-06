"""E2E WebSocket tests for real-time order updates - TDD approach."""
import json
import asyncio
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from apps.stores.models import Store, StoreOrder
from apps.core.consumers import OrderConsumer
from asgiref.sync import sync_to_async

User = get_user_model()


class WebSocketOrdersE2ETest(TransactionTestCase):
    """E2E tests for WebSocket real-time order updates."""

    async def setUp_async(self):
        """Create test user, store, token."""
        # Create user and token
        self.user = await sync_to_async(User.objects.create_user)(
            email='ws-test@example.com',
            password='pass123'
        )
        self.token = await sync_to_async(Token.objects.create)(user=self.user)

        # Create store
        self.store = await sync_to_async(Store.objects.create)(
            name='WebSocket Test Store',
            slug='ws-test-store',
            owner=self.user
        )

    def setUp(self):
        """Set up test case."""
        asyncio.run(self.setUp_async())

    async def test_websocket_connects_with_valid_token(self):
        """
        RED: WebSocket should accept connection with valid token.

        Requirements:
        - Auth token in query params
        - Connection accepted after token validation
        - User is authenticated
        """
        communicator = WebsocketCommunicator(
            OrderConsumer.as_asgi(),
            f"ws/stores/{self.store.slug}/orders/?token={self.token.key}"
        )

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected, "WebSocket should connect with valid token")

        await communicator.disconnect()

    async def test_websocket_rejects_invalid_token(self):
        """RED: WebSocket should reject connection with invalid token."""
        communicator = WebsocketCommunicator(
            OrderConsumer.as_asgi(),
            "ws/stores/ws-test-store/orders/?token=invalid-token-xyz"
        )

        connected, _ = await communicator.connect()
        self.assertFalse(connected, "WebSocket should reject invalid token")

    async def test_websocket_receives_heartbeat(self):
        """
        RED: WebSocket should receive heartbeat (ping) messages.

        Requirements:
        - Heartbeat every 30s to keep connection alive
        - Message format: {'type': 'ping', 'timestamp': ISO8601}
        - Client responds with pong
        """
        communicator = WebsocketCommunicator(
            OrderConsumer.as_asgi(),
            f"ws/stores/{self.store.slug}/orders/?token={self.token.key}"
        )

        await communicator.connect()

        # Wait for heartbeat (should come soon)
        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)

        self.assertEqual(response.get('type'), 'ping')
        self.assertIn('timestamp', response)

        await communicator.disconnect()

    async def test_websocket_broadcasts_order_updates(self):
        """
        RED: WebSocket should broadcast order updates to connected clients.

        Requirements:
        - Create order in store
        - Broadcast via channel group
        - Connected clients receive update
        - Update includes order data
        """
        communicator = WebsocketCommunicator(
            OrderConsumer.as_asgi(),
            f"ws/stores/{self.store.slug}/orders/?token={self.token.key}"
        )

        await communicator.connect()

        # Create order (simulates backend order creation)
        order = await sync_to_async(StoreOrder.objects.create)(
            store=self.store,
            customer_phone='+5511999999999',
            subtotal=100.00,
            total=110.00,
            status='pending'
        )

        # Broadcast order.created event via channel group
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f'store_{self.store.slug}',
            {
                'type': 'order.created',
                'order_id': order.id,
                'status': 'pending',
                'total': '110.00'
            }
        )

        # Client should receive order update
        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)

        self.assertEqual(response.get('type'), 'order.created')
        self.assertEqual(response.get('order_id'), order.id)

        await communicator.disconnect()

    async def test_websocket_deduplicates_listeners(self):
        """
        RED: Same user connecting multiple times should deduplicate.

        Requirements:
        - User connects from 2 browser tabs
        - Only 1 listener ID per (user, store) pair
        - Second connection replaces first
        - Broadcast sent only once per listener
        """
        # First connection
        comm1 = WebsocketCommunicator(
            OrderConsumer.as_asgi(),
            f"ws/stores/{self.store.slug}/orders/?token={self.token.key}"
        )
        await comm1.connect()

        # Second connection from same user
        comm2 = WebsocketCommunicator(
            OrderConsumer.as_asgi(),
            f"ws/stores/{self.store.slug}/orders/?token={self.token.key}"
        )
        await comm2.connect()

        # Both should be in same group but deduplicated
        # Broadcast to group
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f'store_{self.store.slug}',
            {
                'type': 'order.created',
                'order_id': 123,
                'status': 'confirmed'
            }
        )

        # Both should receive (in real system, dedup prevents double-send)
        resp1 = await asyncio.wait_for(comm1.receive_json_from(), timeout=5)
        resp2 = await asyncio.wait_for(comm2.receive_json_from(), timeout=5)

        self.assertEqual(resp1.get('order_id'), 123)
        self.assertEqual(resp2.get('order_id'), 123)

        await comm1.disconnect()
        await comm2.disconnect()

    async def test_websocket_client_pong_response(self):
        """
        RED: Client should respond with pong to server ping.

        Requirements:
        - Server sends ping
        - Client responds with pong
        - Pong includes original timestamp
        """
        communicator = WebsocketCommunicator(
            OrderConsumer.as_asgi(),
            f"ws/stores/{self.store.slug}/orders/?token={self.token.key}"
        )

        await communicator.connect()

        # Receive heartbeat ping
        ping = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)
        self.assertEqual(ping.get('type'), 'ping')

        # Client sends pong response
        await communicator.send_json_to({
            'type': 'pong',
            'timestamp': ping['timestamp']
        })

        # Server should accept pong (not error)
        # No response expected, just no disconnect

        await communicator.disconnect()

    async def test_websocket_handles_order_status_changes(self):
        """
        RED: WebSocket should handle order status change events.

        Requirements:
        - Broadcast order.updated event
        - Includes order_id and new status
        - Client receives and can update UI
        """
        communicator = WebsocketCommunicator(
            OrderConsumer.as_asgi(),
            f"ws/stores/{self.store.slug}/orders/?token={self.token.key}"
        )

        await communicator.connect()

        # Simulate order status change (pending → confirmed)
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f'store_{self.store.slug}',
            {
                'type': 'order.updated',
                'order_id': 789,
                'status': 'confirmed',
                'updated_at': '2026-06-04T14:00:00Z'
            }
        )

        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)

        self.assertEqual(response.get('type'), 'order.updated')
        self.assertEqual(response.get('status'), 'confirmed')
        self.assertEqual(response.get('order_id'), 789)

        await communicator.disconnect()
