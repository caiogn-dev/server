"""Regressão: race no RateLimitMiddleware deixava chave de rate limit sem TTL.

Sequência do bug (Redis): cache.add(key, 0, window) vê a chave existente e não
faz nada; a chave expira logo em seguida; cache.incr(key) então RECRIA a chave
via INCR do Redis — que cria chaves PERSISTENTES (TTL=-1). O contador nunca
zera e o cliente toma 429 permanente (visto em prod 18/jul: bucket do print
agent em 22.808 e bucket de orders do usuário em 1.454, ambos TTL=-1).

Fix: quando incr devolve 1, a chave acabou de ser criada (pelo add OU pelo
incr pós-race) — cache.touch(key, window) garante o TTL nos dois casos.
"""
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.core.middleware import RateLimitMiddleware


@override_settings(RATE_LIMIT_ENABLED=True)
class RateLimitTTLRaceTest(SimpleTestCase):
    def _middleware(self):
        return RateLimitMiddleware(lambda request: mock.MagicMock(status_code=200, __setitem__=mock.MagicMock()))

    def _request(self, path):
        req = mock.MagicMock()
        req.path = path
        req.method = 'GET'
        req.META = {'REMOTE_ADDR': '10.0.0.1'}
        req.headers = {}
        return req

    def test_global_bucket_touch_quando_incr_cria_chave(self):
        """incr==1 (chave recém-criada, possivelmente sem TTL) → touch obrigatório."""
        mw = self._middleware()
        mw.scoped_limits = []
        with mock.patch('apps.core.middleware.cache') as fake_cache:
            fake_cache.add.return_value = False  # add achou chave... que expirou (race)
            fake_cache.incr.return_value = 1     # incr recriou persistente
            mw(self._request('/api/v1/qualquer/'))
            fake_cache.touch.assert_called_once_with('rate_limit:10.0.0.1', mw.window)

    def test_global_bucket_sem_touch_quando_chave_ja_contava(self):
        mw = self._middleware()
        mw.scoped_limits = []
        with mock.patch('apps.core.middleware.cache') as fake_cache:
            fake_cache.add.return_value = False
            fake_cache.incr.return_value = 5
            mw(self._request('/api/v1/qualquer/'))
            fake_cache.touch.assert_not_called()

    def test_scoped_bucket_touch_quando_incr_cria_chave(self):
        mw = self._middleware()
        mw.scoped_limits = [{
            'prefix': '/api/v1/stores/print/',
            'requests': 1200,
            'window': 60,
            'key_by': 'ip',
        }]
        with mock.patch('apps.core.middleware.cache') as fake_cache:
            fake_cache.add.return_value = False
            fake_cache.incr.return_value = 1
            mw(self._request('/api/v1/stores/print/agent/claim-next/'))
            fake_cache.touch.assert_called_once_with(
                'rate_limit:scoped:/api/v1/stores/print/:ip:10.0.0.1', 60
            )

    def test_webhook_guard_touch_quando_incr_cria_chave(self):
        mw = self._middleware()
        req = self._request('/webhooks/v1/whatsapp/')
        req.method = 'POST'
        with mock.patch('apps.core.middleware.cache') as fake_cache:
            fake_cache.add.return_value = False
            fake_cache.incr.return_value = 1
            mw(req)
            fake_cache.touch.assert_called_once_with('rate_limit:webhook:10.0.0.1', 60)
