"""
Regressão de segurança: timing oracle em WhatsAppWebhookView.get (verificação de webhook).

Problema (antes do fix):
  `token == verify_token` usa comparação Python normal, que short-circuits ao
  primeiro byte diferente. Um atacante com acesso de rede dedicado pode medir
  o tempo de resposta e aprender o verify_token carácter a carácter.

  Segundo problema: se WHATSAPP_WEBHOOK_VERIFY_TOKEN não está configurado, o
  resultado é `None == None` → True, verificando o webhook sem autenticação.

Fix: hmac.compare_digest com tempo constante + fail-closed quando token ausente.

Todos os testes são SimpleTestCase (sem DB/Docker).
"""
import hmac
import inspect

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

factory = APIRequestFactory()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _view():
    from apps.whatsapp.webhooks.views import WhatsAppWebhookView
    return WhatsAppWebhookView.as_view()


def _get(token=None, mode='subscribe', challenge='abc123'):
    params = {'hub.mode': mode, 'hub.challenge': challenge}
    if token is not None:
        params['hub.verify_token'] = token
    request = factory.get('/webhooks/v1/whatsapp/', params)
    return _view()(request)


# ---------------------------------------------------------------------------
# 1. Análise estática — hmac.compare_digest presente, == ausente
# ---------------------------------------------------------------------------

class TestWebhookVerifyStaticAnalysis(SimpleTestCase):
    """A implementação de get() deve usar hmac.compare_digest, não ==."""

    def _get_src(self):
        from apps.whatsapp.webhooks.views import WhatsAppWebhookView
        return inspect.getsource(WhatsAppWebhookView.get)

    def test_usa_compare_digest(self):
        src = self._get_src()
        self.assertIn(
            'compare_digest',
            src,
            "WhatsAppWebhookView.get() não usa hmac.compare_digest — "
            "timing oracle permite aprender o verify_token carácter a carácter.",
        )

    def test_nao_usa_igualdade_simples_para_token(self):
        """Não deve haver `token == verify_token` no corpo do método."""
        src = self._get_src()
        self.assertNotIn(
            'token == verify_token',
            src,
            "token == verify_token é timing-oracle; use hmac.compare_digest.",
        )


# ---------------------------------------------------------------------------
# 2. Comportamental — token correto / errado / ausente
# ---------------------------------------------------------------------------

_TOKEN = 'meu-verify-token-secreto'


class TestWebhookVerifyToken(SimpleTestCase):

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN=_TOKEN)
    def test_token_correto_retorna_challenge(self):
        """Token correto em mode=subscribe → 200 com o challenge."""
        resp = _get(token=_TOKEN, challenge='xyz789')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b'xyz789')

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN=_TOKEN)
    def test_token_errado_retorna_403(self):
        """Token errado → 403."""
        resp = _get(token='token-errado')
        self.assertEqual(resp.status_code, 403)

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN=_TOKEN)
    def test_token_ausente_retorna_403(self):
        """Sem hub.verify_token → 403 (Meta sempre manda o token; se não veio, rejeita)."""
        resp = _get(token=None)
        self.assertEqual(resp.status_code, 403)

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN=_TOKEN)
    def test_mode_errado_retorna_403(self):
        """mode != 'subscribe' → 403."""
        resp = _get(token=_TOKEN, mode='unsubscribe')
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# 3. Fail-closed quando verify_token não configurado
# ---------------------------------------------------------------------------

class TestWebhookVerifyNotConfigured(SimpleTestCase):

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN=None)
    def test_token_nulo_rejeita_qualquer_request(self):
        """verify_token=None: qualquer request → 403 (fail-closed).

        Antes do fix: None == None era True → webhook verificado sem autenticação.
        """
        resp = _get(token=None)
        self.assertEqual(
            resp.status_code, 403,
            "WHATSAPP_WEBHOOK_VERIFY_TOKEN=None + hub.verify_token ausente "
            "→ deve rejeitar (fail-closed), não aceitar.",
        )

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN='')
    def test_token_vazio_rejeita_qualquer_request(self):
        """verify_token='': rejeita — token vazio não é token."""
        resp = _get(token='')
        self.assertEqual(resp.status_code, 403)

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN=None)
    def test_token_nulo_rejeita_mesmo_com_token_na_query(self):
        """verify_token=None mesmo com hub.verify_token presente: deve rejeitar."""
        resp = _get(token='qualquer-coisa')
        self.assertEqual(
            resp.status_code, 403,
            "WHATSAPP_WEBHOOK_VERIFY_TOKEN não configurado — deve rejeitar.",
        )
