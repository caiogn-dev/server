from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from apps.messaging.api.views import MessengerWebhookViewSet
from apps.messaging.services import MessengerPlatformService


def _call(params):
    request = APIRequestFactory().get('/webhook/verify/', params)
    return MessengerWebhookViewSet.as_view({'get': 'verify'})(request)


class MessengerVerifyViewTests(SimpleTestCase):
    @override_settings(MESSENGER_WEBHOOK_VERIFY_TOKEN='', MESSENGER_VERIFY_TOKEN='')
    def test_token_vazio_configurado_nao_verifica(self):
        r = _call({'hub.mode': 'subscribe', 'hub.verify_token': '', 'hub.challenge': '123'})
        self.assertEqual(r.status_code, 403)

    @override_settings(MESSENGER_WEBHOOK_VERIFY_TOKEN='', MESSENGER_VERIFY_TOKEN='')
    def test_sem_token_e_sem_config_nao_verifica(self):
        r = _call({'hub.mode': 'subscribe', 'hub.challenge': '123'})
        self.assertEqual(r.status_code, 403)

    @override_settings(MESSENGER_WEBHOOK_VERIFY_TOKEN='segredo')
    def test_token_correto_verifica(self):
        r = _call({'hub.mode': 'subscribe', 'hub.verify_token': 'segredo', 'hub.challenge': '123'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, 123)

    @override_settings(MESSENGER_WEBHOOK_VERIFY_TOKEN='segredo')
    def test_token_errado_recusado(self):
        r = _call({'hub.mode': 'subscribe', 'hub.verify_token': 'outro', 'hub.challenge': '123'})
        self.assertEqual(r.status_code, 403)

    @override_settings(MESSENGER_WEBHOOK_VERIFY_TOKEN='segredo')
    def test_challenge_nao_numerico_nao_gera_500(self):
        r = _call({'hub.mode': 'subscribe', 'hub.verify_token': 'segredo', 'hub.challenge': 'abc'})
        self.assertEqual(r.status_code, 403)


class MessengerServiceVerifyTests(SimpleTestCase):
    @override_settings(MESSENGER_VERIFY_TOKEN='')
    def test_token_vazio_configurado_nao_verifica(self):
        svc = MessengerPlatformService.__new__(MessengerPlatformService)
        self.assertIsNone(svc.verify_webhook('', 'c', 'subscribe'))

    @override_settings(MESSENGER_VERIFY_TOKEN='segredo')
    def test_token_correto(self):
        svc = MessengerPlatformService.__new__(MessengerPlatformService)
        self.assertEqual(svc.verify_webhook('segredo', 'c', 'subscribe'), 'c')
