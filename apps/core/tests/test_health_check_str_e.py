"""
Testes de regressão: HealthCheckView (AllowAny) nunca expõe str(e)
na resposta HTTP — strings de conexao de DB/Redis sao segredos de infra.

Tambem verifica que ThrottledWebSocketConsumer.verify_account_access
nao concede acesso a is_staff sem is_superuser (is_staff = acesso ao
/admin Django, NAO acesso cross-tenant via WebSocket).

Todos SimpleTestCase — sem Docker/PostgreSQL/Redis.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings

_DB_SETTINGS = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': 'db.internal',
        'PORT': '5432',
        'NAME': 'pastita',
    }
}
_CACHE_SETTINGS = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}
}


def _make_health_response(
    conn_side_effect=None,
    cache_side_effect=None,
    cache_get_return='ok',
):
    """Chama HealthCheckView.get() com mocks configuráveis."""
    from apps.core.api import HealthCheckView
    from rest_framework.test import APIRequestFactory

    factory = APIRequestFactory()
    request = factory.get('/health/')
    view = HealthCheckView.as_view()

    with patch('apps.core.api.connection') as mock_conn, \
            patch('apps.core.api.cache') as mock_cache:
        if conn_side_effect is not None:
            mock_conn.cursor.side_effect = conn_side_effect
        else:
            mock_conn.cursor.return_value.__enter__.return_value.execute.return_value = None
        if cache_side_effect is not None:
            mock_cache.set.side_effect = cache_side_effect
        else:
            mock_cache.set.return_value = None
        mock_cache.get.return_value = cache_get_return
        return view(request)


class HealthCheckDbStrETest(SimpleTestCase):
    """DB failure → resposta AllowAny nao deve expor str(e)."""

    @override_settings(DATABASES=_DB_SETTINGS, CACHES=_CACHE_SETTINGS)
    def test_db_error_no_raw_exception_in_body(self):
        """Mensagem de erro de conexao com credenciais nao aparece no JSON de resposta."""
        conn_err = Exception(
            'could not connect to host=db.internal port=5432 dbname=pastita user=admin password=secret123'
        )
        response = _make_health_response(conn_side_effect=conn_err)
        body = json.dumps(response.data)
        self.assertNotIn('host=', body)
        self.assertNotIn('password=', body)
        self.assertNotIn('could not connect', body)

    @override_settings(DATABASES=_DB_SETTINGS, CACHES=_CACHE_SETTINGS)
    def test_db_error_returns_200(self):
        """Falha de DB: Railway healthcheck continua recebendo 200."""
        response = _make_health_response(conn_side_effect=Exception('connection refused'))
        self.assertEqual(response.status_code, 200)

    @override_settings(DATABASES=_DB_SETTINGS, CACHES=_CACHE_SETTINGS)
    def test_db_error_checks_database_is_dict(self):
        """Falha de DB: checks.database e dict estruturado, nao str(e) plano."""
        response = _make_health_response(conn_side_effect=Exception('internal db error'))
        db_check = response.data['checks']['database']
        self.assertIsInstance(db_check, dict, "checks.database deve ser dict, nao string")
        self.assertEqual(db_check['status'], 'error')
        self.assertNotIn('internal db error', json.dumps(db_check))

    @override_settings(DATABASES=_DB_SETTINGS, CACHES=_CACHE_SETTINGS)
    def test_db_error_overall_status_degraded(self):
        """Falha de DB: status geral do health check e 'degraded'."""
        response = _make_health_response(conn_side_effect=Exception('db down'))
        self.assertEqual(response.data['status'], 'degraded')


class HealthCheckCacheStrETest(SimpleTestCase):
    """Cache failure → resposta AllowAny nao deve expor str(e)."""

    @override_settings(DATABASES=_DB_SETTINGS, CACHES=_CACHE_SETTINGS)
    def test_cache_error_no_redis_credentials_in_body(self):
        """URL do Redis com credenciais nao vaza no JSON de resposta."""
        cache_err = Exception(
            'redis://user:password@redis.internal:6379/0 connection refused'
        )
        response = _make_health_response(cache_side_effect=cache_err)
        body = json.dumps(response.data)
        self.assertNotIn('redis://', body)
        self.assertNotIn('password@', body)
        self.assertNotIn('connection refused', body)

    @override_settings(DATABASES=_DB_SETTINGS, CACHES=_CACHE_SETTINGS)
    def test_cache_error_returns_200(self):
        """Falha de cache: Railway healthcheck continua recebendo 200."""
        response = _make_health_response(cache_side_effect=Exception('redis down'))
        self.assertEqual(response.status_code, 200)

    @override_settings(DATABASES=_DB_SETTINGS, CACHES=_CACHE_SETTINGS)
    def test_cache_error_checks_cache_is_dict(self):
        """Falha de cache: checks.cache e dict estruturado, nao str(e) plano."""
        response = _make_health_response(cache_side_effect=Exception('internal cache error'))
        cache_check = response.data['checks']['cache']
        self.assertIsInstance(cache_check, dict, "checks.cache deve ser dict, nao string")
        self.assertEqual(cache_check['status'], 'error')
        self.assertNotIn('internal cache error', json.dumps(cache_check))

    @override_settings(DATABASES=_DB_SETTINGS, CACHES=_CACHE_SETTINGS)
    def test_cache_not_working_checks_cache_is_dict(self):
        """cache.get() != 'ok' (sem Exception): checks.cache tambem e dict, nao string."""
        response = _make_health_response(cache_get_return=None)  # cache.get() != 'ok'
        cache_check = response.data['checks']['cache']
        self.assertIsInstance(cache_check, dict, "checks.cache deve ser dict mesmo sem Exception")
        self.assertEqual(cache_check['status'], 'error')


class BaseConsumerIsStaffTest(SimpleTestCase):
    """verify_account_access fallback nao deve conceder acesso via is_staff."""

    def _call_verify(self, is_staff=False, is_superuser=False, account_id='acct-1'):
        """Chama a funcao sincrona subjacente diretamente, sem event loop."""
        from apps.core.base_consumer import ThrottledWebSocketConsumer
        fn = ThrottledWebSocketConsumer.verify_account_access
        # database_sync_to_async usa functools.update_wrapper → __wrapped__ é o original
        sync_fn = getattr(fn, '__wrapped__', fn)
        consumer = ThrottledWebSocketConsumer.__new__(ThrottledWebSocketConsumer)
        consumer.user = SimpleNamespace(is_staff=is_staff, is_superuser=is_superuser)
        return sync_fn(consumer, account_id)

    def test_is_staff_only_denied(self):
        """is_staff=True, is_superuser=False → acesso negado (is_staff nao e criterio cross-tenant)."""
        self.assertFalse(self._call_verify(is_staff=True, is_superuser=False))

    def test_is_superuser_allowed(self):
        """is_superuser=True → acesso concedido."""
        self.assertTrue(self._call_verify(is_staff=False, is_superuser=True))

    def test_no_user_denied(self):
        """user=None → acesso negado."""
        from apps.core.base_consumer import ThrottledWebSocketConsumer
        fn = ThrottledWebSocketConsumer.verify_account_access
        sync_fn = getattr(fn, '__wrapped__', fn)
        consumer = ThrottledWebSocketConsumer.__new__(ThrottledWebSocketConsumer)
        consumer.user = None
        self.assertFalse(sync_fn(consumer, 'acct-1'))
