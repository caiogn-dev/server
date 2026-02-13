"""
Core middleware for logging, rate limiting, and WebSocket authentication.
"""
import time
import json
import logging
import hashlib
from urllib.parse import parse_qs
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


# ============================================
# WebSocket Token Authentication Middleware
# ============================================

@database_sync_to_async
def get_user_from_token(token_key):
    """Get user from token key."""
    from rest_framework.authtoken.models import Token
    try:
        token = Token.objects.select_related('user').get(key=token_key)
        logger.info(f"WebSocket token auth success: user={token.user.email}")
        return token.user
    except Token.DoesNotExist:
        logger.warning("WebSocket token auth failed: token not found")
        return AnonymousUser()
    except Exception as e:
        logger.error(f"WebSocket token auth error: {e}")
        return AnonymousUser()


class TokenAuthMiddleware(BaseMiddleware):
    """
    Custom middleware that authenticates WebSocket connections using token.
    
    Token can be passed as:
    - Query parameter: ?token=xxx
    - Header: Authorization: Token xxx
    """
    
    async def __call__(self, scope, receive, send):
        # Log connection details for debugging
        path = scope.get('path', 'unknown')
        logger.info(f"WebSocket middleware processing: path={path}")
        
        # Try to get token from query string
        query_string = scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        token_key = None
        
        # Check query parameter
        if 'token' in query_params:
            token_key = query_params['token'][0]
            logger.debug(f"WebSocket token found in query params")
        
        # Check headers if no query param
        if not token_key:
            headers = dict(scope.get('headers', []))
            auth_header = headers.get(b'authorization', b'').decode()
            if auth_header.startswith('Token '):
                token_key = auth_header[6:]
                logger.debug(f"WebSocket token found in Authorization header")
            elif auth_header.startswith('Bearer '):
                token_key = auth_header[7:]
                logger.debug(f"WebSocket token found in Bearer header")
        
        # Authenticate user
        if token_key:
            try:
                scope['user'] = await get_user_from_token(token_key)
                if scope['user'].is_authenticated:
                    logger.info(f"WebSocket authenticated: user={scope['user'].email}, path={path}")
                else:
                    logger.warning(f"WebSocket auth failed: anonymous user, path={path}")
            except Exception as e:
                logger.error(f"WebSocket auth exception: {e}")
                scope['user'] = AnonymousUser()
        else:
            logger.info(f"WebSocket no token provided: path={path}")
            scope['user'] = AnonymousUser()
        
        return await super().__call__(scope, receive, send)


def TokenAuthMiddlewareStack(inner):
    """Convenience function to wrap URLRouter with token auth."""
    return TokenAuthMiddleware(inner)


# ============================================
# HTTP Middleware
# ============================================


class RequestLoggingMiddleware:
    """Middleware for structured request logging."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()
        request_id = hashlib.md5(
            f"{time.time()}{request.path}{request.META.get('REMOTE_ADDR', '')}".encode()
        ).hexdigest()[:12]
        
        request.request_id = request_id

        # Log auth status (not the actual token!) for debugging
        if settings.DEBUG and request.path.startswith('/api/'):
            try:
                auth_hdr = request.META.get('HTTP_AUTHORIZATION', None)
                auth_type = auth_hdr.split()[0] if auth_hdr else None
                logger.debug(f"API request auth type: {auth_type or 'None'}")
            except Exception:
                pass

        response = self.get_response(request)

        duration = time.time() - start_time
        
        log_data = {
            'request_id': request_id,
            'method': request.method,
            'path': request.path,
            'status_code': response.status_code,
            'duration_ms': round(duration * 1000, 2),
            'ip': self.get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
        }

        if hasattr(request, 'user') and request.user.is_authenticated:
            log_data['user_id'] = str(request.user.id)

        if response.status_code >= 400:
            logger.warning("Request completed with error", extra=log_data)
        else:
            logger.info("Request completed", extra=log_data)

        response['X-Request-ID'] = request_id
        return response

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')


class RateLimitMiddleware:
    """Middleware for rate limiting requests."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, 'RATE_LIMIT_ENABLED', True)
        self.max_requests = getattr(settings, 'RATE_LIMIT_REQUESTS', 100)
        self.window = getattr(settings, 'RATE_LIMIT_WINDOW', 60)

    def __call__(self, request):
        if not self.enabled:
            return self.get_response(request)

        if request.path.startswith('/webhooks/'):
            return self.get_response(request)

        if request.path.startswith('/admin/'):
            return self.get_response(request)

        client_ip = self.get_client_ip(request)
        whitelist = getattr(settings, 'RATE_LIMIT_WHITELIST_PATHS', [])
        if any(request.path.startswith(path) for path in whitelist):
            return self.get_response(request)
        cache_key = f"rate_limit:{client_ip}"

        request_count = cache.get(cache_key, 0)

        if request_count >= self.max_requests:
            logger.warning(
                f"Rate limit exceeded for IP: {client_ip}",
                extra={'ip': client_ip, 'count': request_count}
            )
            return JsonResponse(
                {
                    'error': {
                        'code': 'rate_limit_exceeded',
                        'message': 'Too many requests. Please try again later.',
                        'details': {
                            'retry_after': self.window,
                        }
                    }
                },
                status=429
            )

        cache.set(cache_key, request_count + 1, self.window)

        response = self.get_response(request)
        response['X-RateLimit-Limit'] = str(self.max_requests)
        response['X-RateLimit-Remaining'] = str(max(0, self.max_requests - request_count - 1))
        response['X-RateLimit-Reset'] = str(self.window)

        return response

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')


# ============================================
# Multi-Tenant Middleware
# ============================================


class TenantMiddleware:
    """
    Middleware that detects and sets the current tenant for each request.
    
    Tenant detection order:
    1. Subdomain (tenant.pastita.com)
    2. Header (X-Tenant-ID)
    3. Query parameter (?tenant=slug)
    4. Path prefix (/api/v1/stores/{tenant}/)
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        from apps.stores.models import Store
        
        # Detect tenant
        tenant = self._detect_tenant(request, Store)
        
        if tenant:
            request.tenant = tenant
            request.tenant_id = tenant.id
            request.tenant_slug = tenant.slug
        else:
            request.tenant = None
            request.tenant_id = None
            request.tenant_slug = None
        
        response = self.get_response(request)
        
        # Add tenant headers to response
        if hasattr(request, 'tenant_slug') and request.tenant_slug:
            response['X-Tenant-ID'] = request.tenant_slug
        
        return response
    
    def _detect_tenant(self, request, Store):
        """Detect tenant from various sources."""
        from django.core.exceptions import ObjectDoesNotExist
        
        # 1. Check subdomain
        host = request.get_host().split(':')[0]
        if '.' in host and not host.startswith(('localhost', '127.0.0.1', 'web-production')):
            subdomain = host.split('.')[0]
            if subdomain not in ['www', 'api', 'admin', 'app']:
                try:
                    return Store.objects.get(slug=subdomain, is_active=True)
                except ObjectDoesNotExist:
                    pass
        
        # 2. Check header
        tenant_slug = request.headers.get('X-Tenant-ID') or request.headers.get('X-Store-Slug')
        if tenant_slug:
            try:
                return Store.objects.get(slug=tenant_slug, is_active=True)
            except ObjectDoesNotExist:
                pass
        
        # 3. Check query parameter
        tenant_slug = request.GET.get('tenant') or request.GET.get('store')
        if tenant_slug:
            try:
                return Store.objects.get(slug=tenant_slug, is_active=True)
            except ObjectDoesNotExist:
                pass
        
        # 4. Check path (for store-scoped URLs)
        path_parts = request.path.strip('/').split('/')
        if len(path_parts) >= 3 and path_parts[0] == 'api':
            # Check for /api/v1/stores/{slug}/ pattern
            if 'stores' in path_parts:
                store_index = path_parts.index('stores')
                if len(path_parts) > store_index + 1:
                    tenant_slug = path_parts[store_index + 1]
                    try:
                        return Store.objects.get(slug=tenant_slug, is_active=True)
                    except ObjectDoesNotExist:
                        pass
        
        return None


class TenantRequiredMiddleware:
    """
    Middleware that enforces tenant requirement for certain paths.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Paths that don't require tenant
        self.exempt_paths = [
            '/api/v1/auth/',
            '/api/v1/users/',
            '/admin/',
            '/health/',
            '/webhooks/',
        ]
    
    def __call__(self, request):
        # Check if path requires tenant
        requires_tenant = not any(
            request.path.startswith(path) for path in self.exempt_paths
        )
        
        if requires_tenant and not getattr(request, 'tenant', None):
            return JsonResponse(
                {'error': 'Tenant required', 'code': 'TENANT_REQUIRED'},
                status=400
            )
        
        return self.get_response(request)
