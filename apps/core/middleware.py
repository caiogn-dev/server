"""
Core middleware for logging and rate limiting.
"""
import time
import json
import logging
import hashlib
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger(__name__)


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
