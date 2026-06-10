"""
Testes do dispatcher de webhooks — verificação de assinatura HMAC.

Cobre o comportamento fail-closed: provedores em _PROVIDERS_REQUIRE_SIGNATURE
(Meta + MercadoPago) DEVEM ter secret configurado (WebhookEndpoint ou settings),
caso contrário a requisição é rejeitada com 403.
"""
import hashlib
import hmac
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import WebhookEndpoint, WebhookEvent


def _meta_signature(secret: str, body: bytes) -> str:
    return 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class WebhookDispatcherSignatureTests(TestCase):
    """Assinatura HMAC no dispatcher central (/webhooks/v1/<provider>/)."""

    def _post(self, provider: str, body: dict, signature: str = None):
        url = f'/webhooks/v1/{provider}/'
        raw = json.dumps(body).encode()
        headers = {'content_type': 'application/json'}
        if signature is not None:
            headers['HTTP_X_HUB_SIGNATURE_256'] = signature
        return self.client.post(url, data=raw, **headers)

    # --- fail-closed: sem secret configurado em lugar nenhum ---

    @override_settings(WHATSAPP_APP_SECRET='', INSTAGRAM_APP_SECRET='',
                       META_WEBHOOK_APP_SECRET='')
    def test_whatsapp_sem_secret_configurado_rejeita_403(self):
        resp = self._post('whatsapp', {'entry': []})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    @override_settings(WHATSAPP_APP_SECRET='', INSTAGRAM_APP_SECRET='',
                       META_WEBHOOK_APP_SECRET='')
    def test_instagram_sem_secret_configurado_rejeita_403(self):
        resp = self._post('instagram', {'entry': []})
        self.assertEqual(resp.status_code, 403)

    def test_mercadopago_sem_secret_configurado_rejeita_403(self):
        resp = self._post('mercadopago', {'data': {'id': '123'}})
        self.assertEqual(resp.status_code, 403)

    # --- assinatura inválida ---

    def test_whatsapp_assinatura_invalida_rejeita_403(self):
        WebhookEndpoint.objects.create(
            name='wa', provider='whatsapp', path='wa', secret='topsecret',
        )
        resp = self._post('whatsapp', {'entry': []}, signature='sha256=deadbeef')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_whatsapp_sem_header_de_assinatura_rejeita_403(self):
        WebhookEndpoint.objects.create(
            name='wa', provider='whatsapp', path='wa', secret='topsecret',
        )
        resp = self._post('whatsapp', {'entry': []})
        self.assertEqual(resp.status_code, 403)

    # --- assinatura válida via WebhookEndpoint ---

    def test_whatsapp_assinatura_valida_aceita(self):
        WebhookEndpoint.objects.create(
            name='wa', provider='whatsapp', path='wa', secret='topsecret',
        )
        body = {'entry': [], 'object': 'whatsapp_business_account'}
        raw = json.dumps(body).encode()
        resp = self.client.post(
            '/webhooks/v1/whatsapp/', data=raw, content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=_meta_signature('topsecret', raw),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(WebhookEvent.objects.count(), 1)

    # --- fallback de secret via settings (sem WebhookEndpoint no banco) ---

    @override_settings(WHATSAPP_APP_SECRET='envsecret')
    def test_whatsapp_fallback_secret_de_settings_valida_assinatura(self):
        body = {'entry': []}
        raw = json.dumps(body).encode()
        resp = self.client.post(
            '/webhooks/v1/whatsapp/', data=raw, content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=_meta_signature('envsecret', raw),
        )
        self.assertEqual(resp.status_code, 200)

    @override_settings(WHATSAPP_APP_SECRET='envsecret')
    def test_whatsapp_fallback_secret_de_settings_rejeita_assinatura_errada(self):
        raw = json.dumps({'entry': []}).encode()
        resp = self.client.post(
            '/webhooks/v1/whatsapp/', data=raw, content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256='sha256=deadbeef',
        )
        self.assertEqual(resp.status_code, 403)

    @override_settings(WHATSAPP_APP_SECRET='', INSTAGRAM_APP_SECRET='',
                       META_WEBHOOK_APP_SECRET='genericsecret')
    def test_meta_generic_secret_cobre_instagram(self):
        raw = json.dumps({'entry': []}).encode()
        resp = self.client.post(
            '/webhooks/v1/instagram/', data=raw, content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=_meta_signature('genericsecret', raw),
        )
        self.assertEqual(resp.status_code, 200)

    # --- provedores fora da lista obrigatória seguem aceitos (custom) ---

    def test_provider_custom_sem_secret_segue_aceito(self):
        resp = self._post('custom', {'hello': 'world'})
        # custom não está em _PROVIDERS_REQUIRE_SIGNATURE — não deve dar 403
        self.assertNotEqual(resp.status_code, 403)

    # --- dedup por event_id ---

    def test_evento_duplicado_nao_cria_segunda_linha(self):
        WebhookEndpoint.objects.create(
            name='wa', provider='whatsapp', path='wa', secret='topsecret',
        )
        body = {
            'object': 'whatsapp_business_account',
            'entry': [{'changes': [{'value': {'messages': [{'id': 'MSG-1'}]}}]}],
        }
        raw = json.dumps(body).encode()
        sig = _meta_signature('topsecret', raw)
        for _ in range(2):
            self.client.post(
                '/webhooks/v1/whatsapp/', data=raw, content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256=sig,
            )
        self.assertEqual(
            WebhookEvent.objects.filter(event_id='wa_msg_MSG-1').count(), 1,
        )
