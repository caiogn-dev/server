"""
Rate limit throttles for public storefront endpoints.

These throttles are intentionally stricter than the global DRF defaults
(60/min anon, 300/min user) because storefront endpoints are unauthenticated
and interact with external payment APIs.
"""
from rest_framework.throttling import AnonRateThrottle


class CheckoutRateThrottle(AnonRateThrottle):
    """10 checkout attempts per minute per IP — prevents checkout spam and duplicate orders."""
    scope = 'storefront_checkout'


class CouponValidateRateThrottle(AnonRateThrottle):
    """20 coupon validation requests per minute per IP — prevents brute-force coupon enumeration."""
    scope = 'storefront_coupon'


class StorefrontReadRateThrottle(AnonRateThrottle):
    """120 read requests per minute per IP for catalog/store info (2× global anon)."""
    scope = 'storefront_read'
