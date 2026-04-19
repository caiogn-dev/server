"""
InternalDeliveryProvider — no-op provider for stores that manage delivery themselves.

Always reports delivery as handled internally.
Used as the default when no external provider is configured.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from .base import DeliveryProvider, DeliveryQuote, DeliveryResult


class InternalDeliveryProvider(DeliveryProvider):
    @property
    def name(self) -> str:
        return 'internal'

    def quote(self, store, order) -> DeliveryQuote:
        fee = getattr(order, 'delivery_fee', Decimal('0')) or Decimal('0')
        return DeliveryQuote(distance_km=0.0, fee=Decimal(str(fee)), provider=self.name)

    def create(self, store, order) -> DeliveryResult:
        return DeliveryResult(
            external_id='',
            external_code='',
            external_status='internal',
        )

    def cancel(self, external_id: str, reason: str = '') -> bool:
        return True

    def get_status(self, external_id: str) -> Optional[str]:
        return None
