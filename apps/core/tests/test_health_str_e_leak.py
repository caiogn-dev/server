"""
Regressão de segurança: health check (AllowAny) não expõe mensagem interna de erro.

apps/core/health_views.py é montado em /api/v1/core/metrics/ com @permission_classes([AllowAny]).
Qualquer cliente anônimo pode chamar o endpoint. Antes do fix, str(e) de falhas de DB,
Redis e Celery era retornado diretamente — podendo revelar host, porta, credenciais e
strings de conexão da infraestrutura.
"""
import unittest
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase

try:
    import psycopg2  # noqa: F401
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


class HealthViewStrELeakTest(SimpleTestCase):

    def _get_source(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '../health_views.py')
        path = os.path.abspath(path)
        with open(path) as f:
            return f.read()

    def test_health_nao_retorna_str_e_em_falha_de_db(self):
        """health_check não expõe str(e) em falha de DB."""
        source = self._get_source()
        # Após o fix, o campo 'error' do DB deve ser um código genérico, nunca str(e)
        lines = source.splitlines()
        in_db_except = False
        for i, line in enumerate(lines):
            if 'Health check DB failure' in line:
                in_db_except = True
            if in_db_except and "'error': str(e)" in line:
                self.fail("str(e) ainda presente no handler de DB do health check — info-disclosure público")
            if in_db_except and 'database' in line and 'unhealthy' in line:
                break

    def test_health_nao_retorna_str_e_em_falha_de_cache(self):
        """health_check não expõe str(e) em falha de cache/Redis."""
        source = self._get_source()
        lines = source.splitlines()
        in_cache_except = False
        for i, line in enumerate(lines):
            if 'Health check cache failure' in line:
                in_cache_except = True
            if in_cache_except and "'error': str(e)" in line:
                self.fail("str(e) ainda presente no handler de cache do health check — info-disclosure público")
            if in_cache_except and 'cache' in line and 'unhealthy' in line:
                break

    def test_health_nao_retorna_str_e_em_falha_de_celery(self):
        """health_check não expõe str(e) em falha de Celery."""
        source = self._get_source()
        lines = source.splitlines()
        in_celery_except = False
        for i, line in enumerate(lines):
            if 'Health check celery failure' in line:
                in_celery_except = True
            if in_celery_except and "'error': str(e)" in line:
                self.fail("str(e) ainda presente no handler de Celery do health check — info-disclosure público")
            if in_celery_except and 'celery' in line and 'unhealthy' in line:
                break

    def test_health_usa_codigos_genericos(self):
        """Respostas de erro usam códigos genéricos sem dados internos."""
        source = self._get_source()
        self.assertIn('database_unavailable', source,
            "Código genérico 'database_unavailable' não encontrado")
        self.assertIn('cache_unavailable', source,
            "Código genérico 'cache_unavailable' não encontrado")
        self.assertIn('celery_unavailable', source,
            "Código genérico 'celery_unavailable' não encontrado")

    @unittest.skipUnless(HAS_PSYCOPG2, "psycopg2 ausente no ambiente de CI mínimo")
    def test_health_check_db_failure_sem_leak(self):
        """Simula falha de DB — resposta 503 não vaza string de conexão."""
        from apps.core.health_views import health_check
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get('/api/v1/core/metrics/')

        db_error = "connection failed: host='db.internal' password='s3cr3t' user='postgres'"

        with patch('apps.core.health_views.connection') as mock_conn:
            mock_conn.cursor.side_effect = Exception(db_error)
            with patch('apps.core.health_views.cache') as mock_cache:
                mock_cache.set.return_value = True
                mock_cache.get.return_value = 'ok'
                with patch('apps.core.health_views.celery_app') as mock_celery:
                    mock_celery.control.inspect.return_value.ping.return_value = {'worker': 'pong'}
                    with patch('apps.core.health_views._get_celery_queue_depth', return_value=0):
                        response = health_check(request)

        self.assertEqual(response.status_code, 503)
        import json
        body = json.loads(response.content)
        body_str = str(body)
        self.assertNotIn(db_error, body_str,
            "String de conexão DB com credenciais vazou na resposta pública")
        self.assertNotIn('s3cr3t', body_str,
            "Senha presente na resposta pública do health check")
        self.assertNotIn('password', body_str.lower(),
            "Palavra 'password' presente na resposta pública")
        self.assertEqual(body['services']['database']['error'], 'database_unavailable')

    @unittest.skipUnless(HAS_PSYCOPG2, "psycopg2 ausente no ambiente de CI mínimo")
    def test_health_check_cache_failure_sem_leak(self):
        """Simula falha de Redis — resposta não vaza URL de conexão."""
        from apps.core.health_views import health_check
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get('/api/v1/core/metrics/')

        redis_error = "Error connecting to redis://user:senha_redis@redis.internal:6379 — NOAUTH"

        with patch('apps.core.health_views.connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
            with patch('apps.core.health_views._get_db_connection_count', return_value=5):
                with patch('apps.core.health_views.cache') as mock_cache:
                    mock_cache.set.side_effect = Exception(redis_error)
                    with patch('apps.core.health_views.celery_app') as mock_celery:
                        mock_celery.control.inspect.return_value.ping.return_value = {'w': 'p'}
                        with patch('apps.core.health_views._get_celery_queue_depth', return_value=0):
                            response = health_check(request)

        import json
        body = json.loads(response.content)
        body_str = str(body)
        self.assertNotIn(redis_error, body_str,
            "URL de Redis com credenciais vazou na resposta pública")
        self.assertNotIn('senha_redis', body_str)
        self.assertEqual(body['services']['cache']['error'], 'cache_unavailable')
