from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from apps.core.exceptions import WebhookValidationError
from apps.whatsapp.services.webhook_service import WebhookService
from apps.whatsapp.webhooks.views import WhatsAppWebhookView


def _get(params):
    request = APIRequestFactory().get('/webhooks/v1/whatsapp', params)
    return WhatsAppWebhookView.as_view()(request)


class VerificacaoWebhookViewTests(SimpleTestCase):
    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN='segredo')
    def test_token_correto_devolve_challenge(self):
        r = _get({'hub.mode': 'subscribe', 'hub.verify_token': 'segredo', 'hub.challenge': '123'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b'123')

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN='segredo')
    def test_token_errado_403(self):
        r = _get({'hub.mode': 'subscribe', 'hub.verify_token': 'x', 'hub.challenge': '123'})
        self.assertEqual(r.status_code, 403)

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN='')
    def test_env_vazia_nao_verifica_com_token_vazio(self):
        r = _get({'hub.mode': 'subscribe', 'hub.verify_token': '', 'hub.challenge': '123'})
        self.assertEqual(r.status_code, 403)

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN=None)
    def test_env_ausente_nao_verifica_sem_token(self):
        r = _get({'hub.mode': 'subscribe', 'hub.challenge': '123'})
        self.assertEqual(r.status_code, 403)


class VerificacaoWebhookServiceTests(SimpleTestCase):
    def _svc(self):
        svc = WebhookService.__new__(WebhookService)
        return svc

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN='segredo')
    def test_token_correto(self):
        self.assertEqual(self._svc().verify_webhook('subscribe', 'segredo', 'abc'), 'abc')

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN='segredo')
    def test_token_errado(self):
        with self.assertRaises(WebhookValidationError):
            self._svc().verify_webhook('subscribe', 'x', 'abc')

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN='')
    def test_env_vazia_token_vazio(self):
        with self.assertRaises(WebhookValidationError):
            self._svc().verify_webhook('subscribe', '', 'abc')

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN='segredo')
    def test_token_none(self):
        with self.assertRaises(WebhookValidationError):
            self._svc().verify_webhook('subscribe', None, 'abc')
