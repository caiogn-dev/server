from .base import DeliveryProvider, DeliveryProviderError, DeliveryQuote, DeliveryResult
from .internal import InternalDeliveryProvider
from .toca_delivery import TocaDeliveryProvider


def get_delivery_provider(store=None) -> DeliveryProvider:
    """
    Return the configured delivery provider for a store.

    Priority:
    1. Store metadata key 'delivery_provider' = 'toca'
    2. Global setting TOCA_DELIVERY_ENABLED = True
    3. Default: InternalDeliveryProvider
    """
    from django.conf import settings

    meta = getattr(store, 'metadata', None) or {}
    store_provider = meta.get('delivery_provider', '')

    if store_provider == 'toca' or getattr(settings, 'TOCA_DELIVERY_ENABLED', False):
        return TocaDeliveryProvider()

    return InternalDeliveryProvider()


__all__ = [
    'DeliveryProvider',
    'DeliveryProviderError',
    'DeliveryQuote',
    'DeliveryResult',
    'InternalDeliveryProvider',
    'TocaDeliveryProvider',
    'get_delivery_provider',
]
