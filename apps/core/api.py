"""
Core API views - Health check and system endpoints.
"""
from django.db import connection
from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema
import logging

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """Health check endpoint for monitoring.
    
    IMPORTANT: This endpoint ALWAYS returns 200 for Railway healthcheck.
    Database and cache status are reported but don't affect the HTTP status.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Health Check",
        description="Check if the service is healthy",
        responses={200: dict}
    )
    def get(self, request):
        health_status = {
            'status': 'healthy',
            'checks': {}
        }

        # Check database - but don't fail healthcheck if unavailable
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            health_status['checks']['database'] = 'ok'
        except Exception as e:
            health_status['checks']['database'] = f'error: {str(e)}'
            health_status['status'] = 'degraded'
            logger.warning(f"Database health check failed: {e}")

        # Check cache - but don't fail healthcheck if unavailable
        try:
            cache.set('health_check', 'ok', 10)
            if cache.get('health_check') == 'ok':
                health_status['checks']['cache'] = 'ok'
            else:
                health_status['checks']['cache'] = 'error: cache not working'
                health_status['status'] = 'degraded'
        except Exception as e:
            health_status['checks']['cache'] = f'error: {str(e)}'
            health_status['status'] = 'degraded'
            logger.warning(f"Cache health check failed: {e}")

        # ALWAYS return 200 for Railway healthcheck
        # The application is running, even if DB/cache have issues
        return Response(health_status, status=200)


class SystemInfoView(APIView):
    """System information endpoint."""
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="System Info",
        description="Get system information",
        responses={200: dict}
    )
    def get(self, request):
        return Response({
            'name': 'WhatsApp Business Platform',
            'version': '1.0.0',
            'api_version': 'v1',
        })
