"""
Backward-compatible geo service module.

The project historically imported `HereMapsService` from this path. The
implementation now delegates to the provider-agnostic geo layer backed by
Google Maps, while preserving the old import path and public methods.
"""

from apps.stores.services.checkout_service import CheckoutService
from apps.stores.services.geo.service import GeoService


class HereMapsService(GeoService):
    """Legacy class name preserved for compatibility during the migration."""

    def _get_checkout_service_cls(self):
        return CheckoutService


here_maps_service = HereMapsService()
