import hmac
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission


class IsPostadoAdmin(BasePermission):
    # Raises 401 (not 403) so unauthenticated requests get the correct HTTP status.
    def has_permission(self, request, view):
        token = getattr(settings, 'POSTADO_ADMIN_TOKEN', '')
        auth = request.headers.get('Authorization', '')
        if not token or not auth.startswith('Bearer ') or not hmac.compare_digest(auth[7:], token):
            raise AuthenticationFailed('Invalid or missing admin token.')
        return True
