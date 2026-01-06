from django.conf import settings
from rest_framework.authentication import SessionAuthentication, TokenAuthentication, get_authorization_header


class CookieTokenAuthentication(TokenAuthentication):
    """
    Accepts DRF token from Authorization header or HttpOnly cookie.
    Enforces CSRF on unsafe methods to protect cookie-based auth.
    """
    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if auth and auth[0].lower() == self.keyword.lower().encode():
            return super().authenticate(request)

        cookie_name = getattr(settings, 'AUTH_COOKIE_NAME', 'auth_token')
        token = request.COOKIES.get(cookie_name)
        if not token:
            return None

        self.enforce_csrf(request)
        return self.authenticate_credentials(token)

    def enforce_csrf(self, request):
        SessionAuthentication().enforce_csrf(request)
