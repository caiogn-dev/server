"""Event-driven architecture tests - TDD approach."""
from django.test import TestCase
import logging

logger = logging.getLogger(__name__)


class EventBusTest(TestCase):
    """Test event bus implementation."""

    def test_event_published_to_subscribers(self):
        """
        RED: Event bus should publish events to registered subscribers.

        Requirement: Gradual transition from Celery.delay() to events
        - Publisher emits event
        - Subscribers (consumers) receive it
        - Event contains metadata
        """
        from apps.core.event_bus import EventBus, Event

        bus = EventBus()
        received_events = []

        def on_order_created(event: Event):
            received_events.append(event)

        # Subscribe to event
        bus.subscribe('order.created', on_order_created)

        # Publish event
        event = Event(
            type='order.created',
            data={'order_id': '123', 'status': 'pending'},
        )
        bus.publish(event)

        # Verify subscriber received it
        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0].data['order_id'], '123')

    def test_multiple_subscribers_receive_same_event(self):
        """RED: Multiple subscribers for same event type."""
        from apps.core.event_bus import EventBus, Event

        bus = EventBus()
        events_sub1 = []
        events_sub2 = []

        bus.subscribe('order.created', lambda e: events_sub1.append(e))
        bus.subscribe('order.created', lambda e: events_sub2.append(e))

        event = Event(type='order.created', data={'order_id': '456'})
        bus.publish(event)

        self.assertEqual(len(events_sub1), 1)
        self.assertEqual(len(events_sub2), 1)

    def test_event_metadata_included(self):
        """RED: Event includes timestamp, version, source."""
        from apps.core.event_bus import Event
        from datetime import datetime

        event = Event(
            type='payment.received',
            data={'amount': 100, 'currency': 'BRL'},
            source='payment_gateway',
        )

        self.assertEqual(event.type, 'payment.received')
        self.assertIsNotNone(event.timestamp)
        self.assertEqual(event.source, 'payment_gateway')

    def test_unsubscribe_stops_receiving_events(self):
        """RED: Can unsubscribe from events."""
        from apps.core.event_bus import EventBus, Event

        bus = EventBus()
        events = []

        def handler(event):
            events.append(event)

        subscription_id = bus.subscribe('order.updated', handler)

        # Publish and receive
        event1 = Event(type='order.updated', data={'id': '1'})
        bus.publish(event1)
        self.assertEqual(len(events), 1)

        # Unsubscribe
        bus.unsubscribe(subscription_id)

        # Publish again - should not receive
        event2 = Event(type='order.updated', data={'id': '2'})
        bus.publish(event2)
        self.assertEqual(len(events), 1)  # Still 1, not 2
