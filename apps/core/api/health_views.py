"""Health check endpoint."""
import logging
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import connection

logger = logging.getLogger(__name__)

@api_view(['GET'])
def health_check(request):
    """Health check with database status."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({'status': 'healthy', 'database': 'ok'})
    except Exception as e:
        logger.error(f"Health check DB failure: {e}", exc_info=True)
        return Response({'status': 'unhealthy', 'error': 'database_unavailable'}, status=503)
