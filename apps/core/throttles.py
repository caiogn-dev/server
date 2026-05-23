"""
Custom DRF throttle classes for the platform.
"""
from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """
    Throttle specifically for login/register endpoints.
    Uses the 'auth' rate defined in DEFAULT_THROTTLE_RATES (default: 10/minute).
    Applied per-IP so credential stuffing attacks are slowed down.
    """
    scope = 'auth'


class RegisterRateThrottle(AnonRateThrottle):
    """
    Throttle for user registration endpoint.
    Uses the 'register' rate (default: 5/minute).
    """
    scope = 'register'
