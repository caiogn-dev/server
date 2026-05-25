import os
from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import AuthenticationFailed


class IsPostadoAdmin(BasePermission):
    """
    Permission class that validates a static bearer token for Postado admin endpoints.
    Token is read from Django settings (POSTADO_ADMIN_TOKEN) with fallback to os.environ,
    so @override_settings works in tests.
    """

    def has_permission(self, request, view):
        token = getattr(settings, 'POSTADO_ADMIN_TOKEN', os.environ.get('POSTADO_ADMIN_TOKEN', ''))
        auth = request.headers.get('Authorization', '')
        if not token or not auth.startswith('Bearer ') or auth[7:] != token:
            raise AuthenticationFailed('Invalid or missing admin token.')
        return True
