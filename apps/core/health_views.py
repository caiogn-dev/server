"""Health check and monitoring endpoints."""
import psycopg2
from django.db import connection
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.core.cache import cache
from celery import current_app as celery_app
import logging

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Health check endpoint for monitoring and load balancers.

    Returns:
    - 200 OK: All systems healthy
    - 503 Service Unavailable: Critical service down
    """
    health_status = {
        'status': 'healthy',
        'services': {}
    }

    # Database health
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        health_status['services']['database'] = {
            'status': 'healthy',
            'connections': _get_db_connection_count()
        }
    except Exception as e:
        logger.error(f'Health check DB failure: {e}', exc_info=True)
        health_status['services']['database'] = {
            'status': 'unhealthy',
            'error': 'database_unavailable',
        }
        health_status['status'] = 'unhealthy'

    # Redis/Cache health
    try:
        cache.set('health_check', 'ok', 10)
        if cache.get('health_check') == 'ok':
            health_status['services']['cache'] = {'status': 'healthy'}
        else:
            health_status['services']['cache'] = {'status': 'unhealthy', 'error': 'cache_miss'}
            health_status['status'] = 'unhealthy'
    except Exception as e:
        logger.error(f'Health check cache failure: {e}', exc_info=True)
        health_status['services']['cache'] = {
            'status': 'unhealthy',
            'error': 'cache_unavailable',
        }
        health_status['status'] = 'unhealthy'

    # Celery health
    try:
        celery_health = celery_app.control.inspect().ping()
        if celery_health:
            queue_depth = _get_celery_queue_depth()
            health_status['services']['celery'] = {
                'status': 'healthy',
                'workers': len(celery_health),
                'queue_depth': queue_depth
            }
            if queue_depth > 100:
                logger.warning(f'Celery queue depth high: {queue_depth}')
        else:
            health_status['services']['celery'] = {'status': 'unhealthy', 'error': 'no_workers'}
            health_status['status'] = 'unhealthy'
    except Exception as e:
        logger.error(f'Health check celery failure: {e}', exc_info=True)
        health_status['services']['celery'] = {
            'status': 'unhealthy',
            'error': 'celery_unavailable',
        }
        health_status['status'] = 'unhealthy'

    http_status = status.HTTP_200_OK if health_status['status'] == 'healthy' else status.HTTP_503_SERVICE_UNAVAILABLE
    return JsonResponse(health_status, status=http_status)


@api_view(['GET'])
@permission_classes([AllowAny])
def metrics(request):
    """
    Prometheus-compatible metrics endpoint.

    Returns metrics in text format for Prometheus scraping.
    """
    metrics_lines = [
        '# HELP pastita_db_connections Database connection count',
        '# TYPE pastita_db_connections gauge',
        f'pastita_db_connections {_get_db_connection_count()}',
        '',
        '# HELP pastita_celery_queue_depth Celery queue depth',
        '# TYPE pastita_celery_queue_depth gauge',
        f'pastita_celery_queue_depth {_get_celery_queue_depth()}',
        '',
    ]

    # Cache stats
    try:
        cache_info = cache.get_backend('default').get_stats()
        if cache_info:
            metrics_lines.extend([
                '# HELP pastita_cache_hits Cache hit count',
                '# TYPE pastita_cache_hits counter',
                f'pastita_cache_hits {cache_info.get("hits", 0)}',
                '',
                '# HELP pastita_cache_misses Cache miss count',
                '# TYPE pastita_cache_misses counter',
                f'pastita_cache_misses {cache_info.get("misses", 0)}',
                '',
            ])
    except:
        pass

    return JsonResponse(
        {'metrics': '\n'.join(metrics_lines)},
        content_type='text/plain'
    )


def _get_db_connection_count():
    """Get current database connection count."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT count(*) FROM pg_stat_activity
                WHERE datname = current_database()
            ''')
            return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f'Failed to get connection count: {e}')
        return 0


def _get_celery_queue_depth():
    """Get approximate Celery queue depth."""
    try:
        from django_celery_beat.models import PeriodicTask
        # Simple approximation: count pending tasks
        from celery import current_app
        inspect = current_app.control.inspect()
        active_tasks = inspect.active()

        if active_tasks:
            return sum(len(tasks) for tasks in active_tasks.values())
        return 0
    except Exception as e:
        logger.error(f'Failed to get queue depth: {e}')
        return 0
