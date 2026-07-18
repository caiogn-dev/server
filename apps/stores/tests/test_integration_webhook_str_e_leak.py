"""
Testes de regressão: str(e) nos endpoints de teste de integração e webhook.

Endpoints cobertos:
  POST /api/v1/stores/{slug}/integrations/{id}/test/   → store_service.test_integration
  POST /api/v1/stores/{slug}/webhooks/{id}/test_webhook/ → webhook_service.test_webhook

Vetor: falha de rede/conexão revelava mensagens internas (SMTP creds, URLs, tokens)
na resposta HTTP para usuários autenticados (donos/staff de loja).
"""
import requests as req_mod
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase

SENSITIVE = "SENSITIVE_INTERNAL_ERROR_xYzAbCd"


def _make_integration(itype):
    m = MagicMock()
    m.integration_type = itype
    m.name = "test-integration"
    m.access_token = "fake_token"
    m.phone_number_id = "123456"
    m.external_id = "789"
    m.webhook_url = "https://example.com/webhook"
    m.api_key = None
    m.settings = {}
    return m


def _make_webhook():
    m = MagicMock()
    m.url = "https://example.com/wh"
    m.secret = None
    m.headers = {}
    m.store.id = "store-uuid"
    m.store.name = "Test Store"
    return m


class StoreServiceIntegrationStrELeakTest(SimpleTestCase):
    """
    str(e) NÃO deve aparecer em nenhum campo do dict retornado por test_integration
    quando a requisição de rede falha.
    """

    def _assert_no_sensitive(self, result):
        result_str = str(result)
        self.assertNotIn(SENSITIVE, result_str,
                         f"str(e) sensível vazou na resposta: {result_str}")
        self.assertFalse(result.get('success'))

    # --- WhatsApp ---

    @patch("requests.get")
    def test_whatsapp_connection_error_no_str_e(self, mock_get):
        from apps.stores.services.store_service import store_service
        mock_get.side_effect = req_mod.RequestException(SENSITIVE)
        result = store_service._test_whatsapp_integration(
            _make_integration("whatsapp"), {"success": False, "message": "", "details": {}}
        )
        self._assert_no_sensitive(result)
        self.assertIn(result.get("message", ""), [
            "Erro de conexão.", "Erro ao testar integração.", ""
        ])

    # --- MercadoPago ---

    @patch("requests.get")
    def test_mercadopago_connection_error_no_str_e(self, mock_get):
        from apps.stores.services.store_service import store_service
        mock_get.side_effect = req_mod.RequestException(SENSITIVE)
        result = store_service._test_mercadopago_integration(
            _make_integration("mercadopago"), {"success": False, "message": "", "details": {}}
        )
        self._assert_no_sensitive(result)

    # --- Instagram ---

    @patch("requests.get")
    def test_instagram_connection_error_no_str_e(self, mock_get):
        from apps.stores.services.store_service import store_service
        mock_get.side_effect = req_mod.RequestException(SENSITIVE)
        result = store_service._test_instagram_integration(
            _make_integration("instagram"), {"success": False, "message": "", "details": {}}
        )
        self._assert_no_sensitive(result)

    # --- Webhook integration ---

    @patch("requests.post")
    def test_webhook_integration_connection_error_no_str_e(self, mock_post):
        from apps.stores.services.store_service import store_service
        mock_post.side_effect = req_mod.RequestException(SENSITIVE)
        integration = _make_integration("webhook")
        integration.webhook_url = "https://target.example.com/"
        integration.webhook_secret = None  # evita HMAC com MagicMock
        result = store_service._test_webhook_integration(
            integration, {"success": False, "message": "", "details": {}}
        )
        self._assert_no_sensitive(result)

    # --- Email (API) ---

    @patch("requests.get")
    def test_email_api_connection_error_no_str_e(self, mock_get):
        from apps.stores.services.store_service import store_service
        mock_get.side_effect = req_mod.RequestException(SENSITIVE)
        integration = _make_integration("email")
        integration.api_key = "resend_key_123"
        integration.settings = {}
        result = store_service._test_email_integration(
            integration, {"success": False, "message": "", "details": {}}
        )
        self._assert_no_sensitive(result)

    # --- Email (SMTP) ---

    @patch("smtplib.SMTP")
    def test_email_smtp_connection_error_no_str_e(self, mock_smtp):
        from apps.stores.services.store_service import store_service
        mock_smtp.side_effect = Exception(SENSITIVE)
        integration = _make_integration("email")
        integration.api_key = None
        integration.settings = {"smtp_host": "smtp.internal.local", "smtp_port": 587}
        result = store_service._test_email_integration(
            integration, {"success": False, "message": "", "details": {}}
        )
        self._assert_no_sensitive(result)

    # --- Outer exception handler ---

    @patch("apps.stores.services.store_service.StoreService._test_whatsapp_integration")
    def test_outer_exception_handler_no_str_e(self, mock_inner):
        from apps.stores.services.store_service import store_service
        mock_inner.side_effect = RuntimeError(SENSITIVE)
        integration = _make_integration("whatsapp")
        integration.last_sync_at = None
        result = store_service.test_integration(integration)
        self._assert_no_sensitive(result)


class WebhookServiceTestWebhookStrELeakTest(SimpleTestCase):
    """str(e) NÃO deve aparecer no dict retornado por webhook_service.test_webhook."""

    @patch("requests.post")
    def test_connection_error_no_str_e(self, mock_post):
        from apps.stores.services.webhook_service import webhook_service
        mock_post.side_effect = req_mod.RequestException(SENSITIVE)
        result = webhook_service.test_webhook(_make_webhook())
        result_str = str(result)
        self.assertNotIn(SENSITIVE, result_str,
                         f"str(e) sensível vazou na resposta de test_webhook: {result_str}")
        self.assertFalse(result.get("success"))
