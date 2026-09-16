"""Regressão de segurança: _celery_status() expõe str(e) na resposta HTTP.

`WebhookDebugView._celery_status()` retornava `f'error: {str(e)}'` quando a
conexão com o broker Celery falhava. Esse valor chegava intacto na resposta
JSON autenticada (`celery_status` key). Erros de conexão ao broker/Redis podem
incluir a URL completa com credenciais:

    error: [Errno -2] Name or service not known: redis://:senha-secreta@redis:6379/0

Cenários:
  1. Quando Celery falha, `celery_status` é 'error' (genérico, sem detalhes).
  2. Credenciais ou URL do broker não aparecem na string retornada.
  3. Quando Celery funciona (stats não vazio), retorna 'running'.
  4. Quando não há workers (stats vazio/None), retorna 'not running'.
"""
from unittest.mock import patch
from django.test import SimpleTestCase

from apps.whatsapp.webhooks.views import WebhookDebugView


class CeleryStatusDisclosureTest(SimpleTestCase):

    def _call_with_celery_raising(self, exc):
        """Chama _celery_status() com current_app.control.inspect().stats() levantando exc."""
        with patch('celery.current_app') as mock_ca:
            mock_ca.control.inspect.return_value.stats.side_effect = exc
            return WebhookDebugView._celery_status()

    def test_excecao_retorna_error_generico(self):
        """Qualquer exceção deve resultar em 'error', não em str(exc)."""
        resultado = self._call_with_celery_raising(
            Exception('redis://:senha-secreta@redis.interno:6379/0'))
        self.assertEqual(resultado, 'error', resultado)

    def test_credenciais_nao_vazam_na_resposta(self):
        """URL com credenciais do broker não pode aparecer no retorno."""
        url_broker = 'amqp://user:p4ssw0rd@broker.interno/vhost'
        resultado = self._call_with_celery_raising(Exception(url_broker))
        self.assertNotIn(url_broker, resultado)
        self.assertNotIn('p4ssw0rd', resultado)

    def test_celery_running_retorna_running(self):
        with patch('celery.current_app') as mock_ca:
            mock_ca.control.inspect.return_value.stats.return_value = {'worker@host': {}}
            self.assertEqual(WebhookDebugView._celery_status(), 'running')

    def test_celery_sem_workers_retorna_not_running(self):
        with patch('celery.current_app') as mock_ca:
            mock_ca.control.inspect.return_value.stats.return_value = None
            self.assertEqual(WebhookDebugView._celery_status(), 'not running')
