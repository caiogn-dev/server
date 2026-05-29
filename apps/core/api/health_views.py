"""Health check endpoint."""
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import connection

@api_view(['GET'])
def health_check(request):
    """Health check with database status."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({'status': 'healthy', 'database': 'ok'})
    except Exception as e:
        return Response({'status': 'unhealthy', 'error': str(e)}, status=503)
