"""Advanced logging middleware for requests."""
import logging
import time
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger('structured')

class StructuredLoggingMiddleware(MiddlewareMixin):
    """Log requests with structured data for monitoring."""
    def process_request(self, request):
        request._start_time = time.time()
        return None
    
    def process_response(self, request, response):
        duration_ms = (time.time() - getattr(request, '_start_time', time.time())) * 1000
        if any(x in request.path for x in ['/api/v1/stores', '/api/v1/orders']):
            logger.info(f"{request.method} {request.path} {response.status_code} {duration_ms:.0f}ms")
        return response
