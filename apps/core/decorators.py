"""API decorators for common patterns."""
import hashlib
import logging
from functools import wraps
from django.core.cache import cache
from rest_framework.response import Response
from rest_framework import status as http_status

logger = logging.getLogger(__name__)


def idempotent(idempotency_key_header='Idempotency-Key', timeout=3600):
    """
    Decorator for making endpoints idempotent.

    Prevents duplicate processing of the same request. If the same request
    (identified by Idempotency-Key) is made multiple times, returns the same
    response without re-processing.

    Usage:
        @api_view(['POST'])
        @idempotent()
        def create_order(request):
            # This will only be executed once per unique Idempotency-Key
            order = Order.objects.create(...)
            return Response({'id': order.id})

    Frontend usage:
        import { v4 as uuid } from 'uuid';

        const response = await fetch('/api/v1/orders/', {
            method: 'POST',
            headers: {
                'Idempotency-Key': uuid(),  // New UUID per request
                'Authorization': `Token ${token}`,
            },
            body: JSON.stringify(data),
        });

    Args:
        idempotency_key_header: Name of header containing the key (default: Idempotency-Key)
        timeout: How long to cache response (seconds, default: 1 hour)

    Returns:
        - First request with key: Execute view, cache response
        - Same key again: Return cached response immediately
    """

    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # Skip idempotency for non-mutating methods
            if request.method not in ['POST', 'PUT', 'PATCH', 'DELETE']:
                return func(request, *args, **kwargs)

            # Get idempotency key from header
            idempotency_key = request.headers.get(idempotency_key_header)

            if not idempotency_key:
                # No idempotency key = always execute
                return func(request, *args, **kwargs)

            # Build cache key: hash(user_id + endpoint + idempotency_key)
            user_id = request.user.id if request.user and request.user.is_authenticated else 'anon'
            endpoint = request.path
            cache_key = f'idempotent:{user_id}:{endpoint}:{idempotency_key}'

            # Check if we've seen this request before
            cached_response = cache.get(cache_key)
            if cached_response is not None:
                logger.info(
                    f'Idempotent request (cached)',
                    extra={
                        'idempotency_key': idempotency_key,
                        'user_id': user_id,
                        'endpoint': endpoint,
                    }
                )
                return cached_response

            # First time seeing this key: execute the view
            response = func(request, *args, **kwargs)

            # Cache the response
            if hasattr(response, 'data'):
                # DRF Response
                cache.set(cache_key, response, timeout)
            else:
                # Django Response
                cache.set(cache_key, response, timeout)

            logger.info(
                f'Idempotent request (new)',
                extra={
                    'idempotency_key': idempotency_key,
                    'user_id': user_id,
                    'endpoint': endpoint,
                    'timeout': timeout,
                }
            )
            return response

        return wrapper

    return decorator


def require_idempotency_key(func):
    """
    Decorator that requires Idempotency-Key header for safety-critical endpoints.

    If header is missing, returns 400 Bad Request.

    Usage:
        @api_view(['POST'])
        @require_idempotency_key
        def process_payment(request):
            # Will reject if Idempotency-Key header missing
            ...
    """

    @wraps(func)
    def wrapper(request, *args, **kwargs):
        if request.method not in ['POST', 'PUT', 'PATCH', 'DELETE']:
            return func(request, *args, **kwargs)

        if not request.headers.get('Idempotency-Key'):
            return Response(
                {
                    'error': {
                        'code': 'missing_idempotency_key',
                        'message': 'Idempotency-Key header is required for this operation.',
                        'details': {
                            'header': 'Idempotency-Key',
                            'format': 'UUID v4 (e.g., 550e8400-e29b-41d4-a716-446655440000)',
                        },
                    }
                },
                status=http_status.HTTP_400_BAD_REQUEST
            )

        return func(request, *args, **kwargs)

    return wrapper
