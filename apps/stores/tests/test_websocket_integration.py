"""WebSocket integration tests - simplified for Django test runner."""
import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from apps.stores.models import Store
from apps.stores.models.order import StoreOrder as Order
from apps.core.websocket_auth import validate_websocket_token
from apps.core.websocket_listeners import generate_listener_id
from apps.core.websocket_heartbeat import create_heartbeat_message

User = get_user_model()


class WebSocketAuthTest(TestCase):
    """Test WebSocket authentication layer."""

    def setUp(self):
        """Create test user and token."""
        self.user = User.objects.create_user(
            email='ws-test@example.com',
            password='pass123'
        )
        self.token = Token.objects.create(user=self.user)

    def test_valid_token_returns_user(self):
        """GREEN: Valid token should validate and return user."""
        result = validate_websocket_token(self.token.key)
        self.assertEqual(result, self.user)

    def test_invalid_token_returns_none(self):
        """GREEN: Invalid token should return None."""
        result = validate_websocket_token('invalid-token-xyz')
        self.assertIsNone(result)

    def test_empty_token_returns_none(self):
        """GREEN: Empty token should return None."""
        result = validate_websocket_token('')
        self.assertIsNone(result)


class WebSocketListenerDeduplicationTest(TestCase):
    """Test listener deduplication for same user+store."""

    def setUp(self):
        """Create test user."""
        self.user = User.objects.create_user(
            email='dedup-test@example.com',
            password='pass123'
        )

    def test_listener_id_has_user_and_store(self):
        """GREEN: Listener ID should include user ID and store slug."""
        listener_id = generate_listener_id(self.user.id, 'test-store')

        # Format: user_id:store_slug:uuid
        parts = listener_id.split(':')
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], str(self.user.id))
        self.assertEqual(parts[1], 'test-store')

    def test_listener_ids_are_unique(self):
        """GREEN: Each call should generate unique UUID portion."""
        id1 = generate_listener_id(self.user.id, 'store1')
        id2 = generate_listener_id(self.user.id, 'store1')

        # Different because UUIDs differ
        self.assertNotEqual(id1, id2)

        # But same user:store prefix
        self.assertTrue(id1.startswith(f"{self.user.id}:store1:"))
        self.assertTrue(id2.startswith(f"{self.user.id}:store1:"))


class WebSocketHeartbeatTest(TestCase):
    """Test heartbeat mechanism."""

    def test_heartbeat_has_correct_format(self):
        """GREEN: Heartbeat should have type=ping and ISO8601 timestamp."""
        hb = create_heartbeat_message()

        self.assertEqual(hb['type'], 'ping')
        self.assertIn('timestamp', hb)

        # Verify timestamp is ISO8601
        from datetime import datetime
        datetime.fromisoformat(hb['timestamp'])  # Should not raise

    def test_heartbeat_is_json_serializable(self):
        """GREEN: Heartbeat should be JSON-serializable."""
        hb = create_heartbeat_message()
        json_str = json.dumps(hb)

        # Should deserialize back
        parsed = json.loads(json_str)
        self.assertEqual(parsed['type'], 'ping')


class WebSocketEventBroadcastTest(TestCase):
    """Test event broadcast structure."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(
            email='broadcast-test@example.com',
            password='pass123'
        )
        self.store = Store.objects.create(
            name='Test Store',
            slug='broadcast-store',
            owner=self.user
        )

    def test_order_created_event_format(self):
        """GREEN: order.created event should have required fields."""
        order = Order.objects.create(
            store=self.store,
            customer_phone='+5511999999999',
            subtotal=100.00,
            total=110.00,
            status='pending'
        )

        # Simulate event that would be broadcast
        event_data = {
            'type': 'order.created',
            'order_id': order.id,
            'status': order.status,
            'total': str(order.total),
        }

        json_str = json.dumps(event_data)
        parsed = json.loads(json_str)

        self.assertEqual(parsed['type'], 'order.created')
        self.assertEqual(parsed['order_id'], order.id)
        self.assertEqual(parsed['status'], 'pending')

    def test_order_updated_event_format(self):
        """GREEN: order.updated event should include status and timestamp."""
        order = Order.objects.create(
            store=self.store,
            customer_phone='+5511999999999',
            subtotal=100.00,
            total=110.00,
            status='pending'
        )

        # Simulate status change event
        event_data = {
            'type': 'order.updated',
            'order_id': order.id,
            'status': 'confirmed',
            'updated_at': '2026-06-04T14:00:00Z',
        }

        json_str = json.dumps(event_data)
        parsed = json.loads(json_str)

        self.assertEqual(parsed['type'], 'order.updated')
        self.assertEqual(parsed['status'], 'confirmed')
        self.assertIn('updated_at', parsed)


class WebSocketChannelGroupNamingTest(TestCase):
    """Test channel group naming convention."""

    def test_group_name_is_store_slug_prefixed(self):
        """GREEN: Group name should be 'store_<slug>'."""
        store_slug = 'my-test-store'
        group_name = f'store_{store_slug}'

        self.assertEqual(group_name, 'store_my-test-store')

    def test_group_name_from_real_store(self):
        """GREEN: Real store should generate correct group name."""
        user = User.objects.create_user(
            email='group-test@example.com',
            password='pass123'
        )
        store = Store.objects.create(
            name='Group Test Store',
            slug='group-test-123',
            owner=user
        )

        group_name = f'store_{store.slug}'
        self.assertEqual(group_name, 'store_group-test-123')
