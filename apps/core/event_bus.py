"""Event-driven architecture core - Event Bus implementation."""
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List


class Event:
    """Represents a domain event."""

    def __init__(
        self,
        type: str,
        data: Dict[str, Any],
        source: str = 'app',
        timestamp: str | None = None,
    ):
        """
        Initialize event.

        Args:
            type: Event type (e.g., 'order.created', 'payment.received')
            data: Event payload
            source: Where event originated (default: 'app')
            timestamp: ISO8601 timestamp (auto-generated if not provided)
        """
        self.id = str(uuid.uuid4())
        self.type = type
        self.data = data
        self.source = source
        self.timestamp = timestamp or datetime.now().isoformat()
        self.version = 1


class EventBus:
    """
    Simple event bus for decoupling event publishers from subscribers.

    Enables gradual transition from Celery.delay() to event-driven:
    - Publishers emit events without knowing who consumes them
    - Subscribers react to events they care about
    - No direct coupling between producers/consumers
    """

    def __init__(self):
        """Initialize event bus."""
        self._subscribers: Dict[str, List[Callable]] = {}
        # subscription_id -> (event_type, handler) — precisamos do handler pra
        # remover a inscrição certa no unsubscribe.
        self._subscription_ids: Dict[str, tuple] = {}

    def subscribe(self, event_type: str, handler: Callable) -> str:
        """
        Subscribe to events of a specific type.

        Args:
            event_type: The event type to listen for
            handler: Callable that receives Event object

        Returns:
            subscription_id: Can be used to unsubscribe later
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        subscription_id = str(uuid.uuid4())
        self._subscribers[event_type].append(handler)
        self._subscription_ids[subscription_id] = (event_type, handler)

        return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from an event.

        Args:
            subscription_id: The ID returned from subscribe()

        Returns:
            True if unsubscribed successfully, False if ID not found
        """
        if subscription_id not in self._subscription_ids:
            return False

        event_type, handler = self._subscription_ids.pop(subscription_id)
        # Remove a instância exata do handler dessa inscrição.
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass
        return True

    def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers.

        Args:
            event: The Event to publish
        """
        if event.type not in self._subscribers:
            return

        for handler in self._subscribers[event.type]:
            try:
                handler(event)
            except Exception as e:
                # Log error but don't stop other handlers
                print(f"Error in event handler for {event.type}: {e}")

    def clear(self) -> None:
        """Clear all subscribers (useful for testing)."""
        self._subscribers.clear()
        self._subscription_ids.clear()
