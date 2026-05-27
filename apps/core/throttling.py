from rest_framework.throttling import AnonRateThrottle


class AuthRateThrottle(AnonRateThrottle):
    """Stricter throttle for auth endpoints (10 req/min per IP, scope 'auth')."""
    scope = 'auth'
