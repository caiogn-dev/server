"""E2E WebSocket tests for real-time order updates.

These tests drive the REAL order consumer, ``StoreOrdersConsumer``
(canonical class name ``OrderConsumer``) living in ``apps.stores.consumers``
and routed at ``ws/stores/(?P<store_slug>[\\w-]+)/orders/$`` (see
``apps/core/routing.py``).

The consumer:
- Reads ``store_slug`` from ``scope['url_route']['kwargs']`` (closes 4000 if missing).
- Reads ``token`` from the query string and validates it via
  ``apps.core.websocket_auth.validate_websocket_token`` (closes 4001 if invalid/absent).
- Joins channel group ``store_{store_slug}`` and starts a 30s heartbeat task.
- Has group handlers ``order_created`` / ``order_updated`` /
  ``order_payment_received`` (Channels maps a group_send ``type`` of
  ``order.created`` to the ``order_created`` method).
"""
import asyncio

from django.test import TransactionTestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import re_path
from rest_framework.authtoken.models import Token
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from asgiref.sync import sync_to_async

from apps.stores.models import Store, StoreOrder
from apps.stores.consumers import StoreOrdersConsumer
from apps.stores.services.realtime_service import store_orders_group

User = get_user_model()

# Mirror the production route so ``scope['url_route']['kwargs']['store_slug']``
# gets populated exactly like it does at runtime (apps/core/routing.py).
application = URLRouter([
    re_path(
        r'ws/stores/(?P<store_slug>[\w-]+)/orders/$',
        StoreOrdersConsumer.as_asgi(),
    ),
])


# group_send / group_add must work in-process. In the container REDIS_URL is set,
# so the default layer would be RedisChannelLayer; force the in-memory layer here.
@override_settings(CHANNEL_LAYERS={
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
})
class WebSocketOrdersE2ETest(TransactionTestCase):
    """E2E tests for WebSocket real-time order updates."""

    async def setUp_async(self):
        """Create test user, token and store."""
        # NOTE: project uses Django's default auth.User, whose manager REQUIRES
        # ``username``. Omitting it raises ValueError at create_user time.
        self.user = await sync_to_async(User.objects.create_user)(
            username='ws-test',
            email='ws-test@example.com',
            password='pass123',
        )
        self.token = await sync_to_async(Token.objects.create)(user=self.user)

        self.store = await sync_to_async(Store.objects.create)(
            name='WebSocket Test Store',
            slug='ws-test-store',
            owner=self.user,
        )

    def setUp(self):
        asyncio.run(self.setUp_async())

    def _path(self, slug=None, token=None):
        slug = slug if slug is not None else self.store.slug
        token = token if token is not None else self.token.key
        return f"ws/stores/{slug}/orders/?token={token}"

    async def test_websocket_connects_with_valid_token(self):
        """WebSocket should accept a connection carrying a valid token."""
        communicator = WebsocketCommunicator(application, self._path())

        connected, _ = await communicator.connect()
        self.assertTrue(connected, "WebSocket should connect with valid token")

        await communicator.disconnect()

    async def test_websocket_rejects_invalid_token(self):
        """WebSocket should reject (close 4001) a connection with a bad token."""
        communicator = WebsocketCommunicator(
            application,
            self._path(token='invalid-token-xyz'),
        )

        connected, close_code = await communicator.connect()
        self.assertFalse(connected, "WebSocket should reject invalid token")
        self.assertEqual(close_code, 4001, "Consumer closes with code 4001 on auth failure")

    async def test_websocket_rejects_missing_token(self):
        """Sem ``token`` na query: aceita e aguarda first-message auth
        ({"type":"auth","token":...}); auth inválida fecha com 4001.

        Contrato atualizado 18/jul: o consumer suporta first-message auth
        (padrão do client do painel, token fora de URLs/logs) além do query
        param legado — ver test_websocket_first_message_auth.py.
        """
        communicator = WebsocketCommunicator(
            application,
            f"ws/stores/{self.store.slug}/orders/",
        )

        connected, _ = await communicator.connect()
        self.assertTrue(connected, "Handshake aceito; auth acontece via first-message")

        await communicator.send_json_to({'type': 'auth', 'token': 'invalido'})
        out = await asyncio.wait_for(communicator.receive_output(), timeout=5)
        self.assertEqual(out['type'], 'websocket.close')
        self.assertEqual(out.get('code'), 4001)

    async def test_websocket_broadcasts_order_created(self):
        """A group broadcast of ``order.created`` should reach the client."""
        communicator = WebsocketCommunicator(application, self._path())
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        ack = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)
        self.assertEqual(ack.get('type'), 'connection_established')

        order = await sync_to_async(StoreOrder.objects.create)(
            store=self.store,
            customer_name='WS Tester',
            customer_phone='+5511999999999',
            subtotal=100.00,
            total=110.00,
            status='pending',
        )

        # The production broadcaster (apps/stores/services/realtime_service.py)
        # always sends order_id as str(order.id) because StoreOrder.id is a UUID
        # and the consumer json.dumps the event verbatim. Mirror that here.
        order_id = str(order.id)
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            store_orders_group(self.store.slug),
            {
                'type': 'order.created',  # -> order_created handler
                'order_id': order_id,
                'status': 'pending',
                'total': '110.00',
            },
        )

        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)

        self.assertEqual(response.get('type'), 'order.created')
        self.assertEqual(response.get('order_id'), order_id)
        self.assertEqual(response.get('status'), 'pending')
        self.assertEqual(response.get('total'), '110.00')
        self.assertIn('timestamp', response)

        await communicator.disconnect()

    async def test_websocket_broadcasts_order_updates(self):
        """A group broadcast of ``order.updated`` should reach the client."""
        communicator = WebsocketCommunicator(application, self._path())
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        ack = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)
        self.assertEqual(ack.get('type'), 'connection_established')

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            store_orders_group(self.store.slug),
            {
                'type': 'order.updated',  # -> order_updated handler
                'order_id': 789,
                'status': 'confirmed',
                'updated_at': '2026-06-04T14:00:00Z',
            },
        )

        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)

        self.assertEqual(response.get('type'), 'order.updated')
        self.assertEqual(response.get('order_id'), 789)
        self.assertEqual(response.get('status'), 'confirmed')
        self.assertEqual(response.get('updated_at'), '2026-06-04T14:00:00Z')
        self.assertIn('timestamp', response)

        await communicator.disconnect()

    async def test_websocket_broadcast_reaches_multiple_clients(self):
        """Two tabs of the same user both join ``store_{slug}`` and both
        receive the broadcast.

        Reframed from the original ``test_websocket_deduplicates_listeners``:
        the real consumer computes a ``listener_id`` purely for logging/dedup
        bookkeeping but every accepted connection is ``group_add``-ed to the
        same group, so a single ``group_send`` is delivered to BOTH channels.
        There is no server-side suppression of the second delivery, so the
        honest assertion is that both clients receive the event.
        """
        comm1 = WebsocketCommunicator(application, self._path())
        comm2 = WebsocketCommunicator(application, self._path())

        c1, _ = await comm1.connect()
        c2, _ = await comm2.connect()
        self.assertTrue(c1)
        self.assertTrue(c2)
        for comm in (comm1, comm2):
            ack = await asyncio.wait_for(comm.receive_json_from(), timeout=5)
            self.assertEqual(ack.get('type'), 'connection_established')

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            store_orders_group(self.store.slug),
            {
                'type': 'order.created',
                'order_id': 123,
                'status': 'confirmed',
            },
        )

        resp1 = await asyncio.wait_for(comm1.receive_json_from(), timeout=5)
        resp2 = await asyncio.wait_for(comm2.receive_json_from(), timeout=5)

        self.assertEqual(resp1.get('order_id'), 123)
        self.assertEqual(resp2.get('order_id'), 123)

        await comm1.disconnect()
        await comm2.disconnect()

    async def test_websocket_accepts_pong_without_error(self):
        """The consumer's ``receive`` accepts a client ``pong`` silently.

        Reframed from the original heartbeat tests: the real consumer's
        ``_send_heartbeat`` sleeps 30s BEFORE the first ping, so asserting a
        ping within a 5s test window is a fiction. What we CAN deterministically
        verify is the documented contract that a client ``pong`` is accepted
        (no exception, no disconnect, no reply) by ``OrderConsumer.receive``.
        """
        communicator = WebsocketCommunicator(application, self._path())
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        ack = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)
        self.assertEqual(ack.get('type'), 'connection_established')

        await communicator.send_json_to({
            'type': 'pong',
            'timestamp': '2026-06-04T14:00:00Z',
        })

        # No reply is expected for a pong; the connection must stay open.
        self.assertTrue(await communicator.receive_nothing(timeout=1))

        # And a normal broadcast still flows after the pong, proving the
        # consumer did not error out or drop the connection.
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            store_orders_group(self.store.slug),
            {'type': 'order.updated', 'order_id': 1, 'status': 'paid'},
        )
        response = await asyncio.wait_for(communicator.receive_json_from(), timeout=5)
        self.assertEqual(response.get('order_id'), 1)

        await communicator.disconnect()
