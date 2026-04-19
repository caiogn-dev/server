"""
Abstract base for external delivery providers.

Each provider maps a confirmed StoreOrder to an external delivery run
and reports back status updates.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class DeliveryQuote:
    distance_km: float
    fee: Decimal
    zone_name: Optional[str] = None
    provider: str = 'unknown'


@dataclass
class DeliveryResult:
    external_id: str
    external_code: str          # human-readable tracking code (e.g. TCA-1234)
    external_status: str        # provider-native status string
    tracking_url: Optional[str] = None
    polyline: Optional[str] = None
    extra: dict = field(default_factory=dict)


class DeliveryProvider(ABC):
    """
    Provider-agnostic interface for external delivery dispatch.

    Implementations must be stateless — all state lives on StoreOrder.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short provider identifier, e.g. 'toca', 'internal'."""

    @abstractmethod
    def quote(self, store, order) -> DeliveryQuote:
        """
        Estimate delivery fee and distance without creating a delivery.

        Args:
            store: Store model instance.
            order: StoreOrder model instance (not yet dispatched).

        Returns:
            DeliveryQuote with fee and distance info.
        """

    @abstractmethod
    def create(self, store, order) -> DeliveryResult:
        """
        Dispatch the order to the external delivery provider.

        Args:
            store: Store model instance.
            order: StoreOrder model instance (delivery_address must be populated).

        Returns:
            DeliveryResult with external tracking info.

        Raises:
            DeliveryProviderError on failure.
        """

    @abstractmethod
    def cancel(self, external_id: str, reason: str = '') -> bool:
        """
        Request cancellation of an in-progress delivery.

        Returns True if cancellation was accepted, False otherwise.
        """

    @abstractmethod
    def get_status(self, external_id: str) -> Optional[str]:
        """
        Poll the current external status string.

        Returns None if the delivery is not found or the call fails.
        """

    # ------------------------------------------------------------------
    # Status mapping — implementations should override if needed
    # ------------------------------------------------------------------

    def map_status_to_order(self, external_status: str) -> Optional[str]:
        """
        Translate provider status to a StoreOrder.OrderStatus value.

        Returns None when no order status update should be triggered.
        """
        return None


class DeliveryProviderError(Exception):
    """Raised when a delivery provider call fails unrecoverably."""
