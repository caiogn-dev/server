"""
Testes do serviço de webhook do WhatsApp — assinatura e verificação de subscribe.
"""
import hashlib
import hmac

from django.test import TestCase, override_settings

from apps.whatsapp.services.webhook_service import WebhookService
from apps.core.exceptions import WebhookValidationError


def _sig(secret: str, body: bytes) -> str:
    return 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class ValidateSignatureTests(TestCase):
    @override_settings(WHATSAPP_APP_SECRET='')
    def test_sem_secret_configurado_rejeita(self):
        """Fail-closed: sem WHATSAPP_APP_SECRET nenhum webhook é aceito."""
        service = WebhookService()
        self.assertFalse(service.validate_signature(b'{}', 'sha256=abc'))

    @override_settings(WHATSAPP_APP_SECRET='topsecret')
    def test_assinatura_valida_aceita(self):
        service = WebhookService()
        body = b'{"entry": []}'
        self.assertTrue(service.validate_signature(body, _sig('topsecret', body)))

    @override_settings(WHATSAPP_APP_SECRET='topsecret')
    def test_assinatura_invalida_rejeita(self):
        service = WebhookService()
        self.assertFalse(service.validate_signature(b'{"entry": []}', 'sha256=deadbeef'))

    @override_settings(WHATSAPP_APP_SECRET='topsecret')
    def test_sem_assinatura_rejeita(self):
        service = WebhookService()
        self.assertFalse(service.validate_signature(b'{"entry": []}', ''))


class VerifyWebhookTests(TestCase):
    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN='vtoken')
    def test_subscribe_com_token_correto_retorna_challenge(self):
        service = WebhookService()
        self.assertEqual(service.verify_webhook('subscribe', 'vtoken', '42'), '42')

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN='vtoken')
    def test_subscribe_com_token_errado_levanta_erro(self):
        service = WebhookService()
        with self.assertRaises(WebhookValidationError):
            service.verify_webhook('subscribe', 'errado', '42')

    @override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN='vtoken')
    def test_mode_diferente_de_subscribe_levanta_erro(self):
        service = WebhookService()
        with self.assertRaises(WebhookValidationError):
            service.verify_webhook('unsubscribe', 'vtoken', '42')
