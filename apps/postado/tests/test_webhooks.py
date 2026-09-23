import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, Client as DjangoClient, override_settings

from apps.postado.models import PostadoClient, PostadoPack

SEGREDO = 'segredo-de-teste'


def _assinar(data_id: str, request_id: str = 'req-1', ts: str = '1700000000'):
    """Cabeçalhos que o Mercado Pago mandaria — assinados de verdade.

    O endpoint ganhou verificação HMAC (sem ela qualquer um forja um pagamento
    aprovado) e estes testes nunca aprenderam a assinar: passaram a receber 403
    e a acusar o acerto como se fosse defeito. Assinar aqui devolve o teste ao
    que ele cobra — o fluxo depois do pagamento — e o teste de forja abaixo
    passa a cobrar a trava.
    """
    manifesto = f'id:{data_id};request-id:{request_id};ts:{ts};'
    v1 = hmac.new(SEGREDO.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
    return {
        'HTTP_X_SIGNATURE': f'ts={ts},v1={v1}',
        'HTTP_X_REQUEST_ID': request_id,
    }


@override_settings(DEBUG=False)
class TestMPWebhook(TestCase):
    def setUp(self):
        self.client = DjangoClient()
        self.client_obj = PostadoClient.objects.create(
            business_name="Webhook Test",
            niche='restaurant',
            tone='casual',
            email="webhook@test.com",
            whatsapp="61900000003",
            mp_subscription_id="SUB_123",
        )

    @patch('apps.postado.api.views.generate_pack')
    def test_payment_approved_triggers_generation(self, mock_generate_pack):
        payload = {
            "type": "payment",
            "action": "payment.created",
            "data": {"id": "PAY_999"},
        }
        url = "/api/postado/webhook/mp/?preapproval_id=SUB_123&data.id=PAY_999"
        with self.settings(MERCADO_PAGO_WEBHOOK_SECRET=SEGREDO):
            with patch.dict('os.environ', {'MERCADO_PAGO_WEBHOOK_SECRET': SEGREDO}):
                response = self.client.post(
                    url,
                    data=json.dumps(payload),
                    content_type='application/json',
                    **_assinar('PAY_999'),
                )
        self.assertEqual(response.status_code, 200, response.content)
        mock_generate_pack.delay.assert_called_once()

    @patch('apps.postado.api.views.generate_pack')
    def test_corpo_forjado_nao_gera_pacote(self, mock_generate_pack):
        """Sem o segredo, ninguém manda gerar pacote de graça."""
        payload = {"type": "payment", "action": "payment.created",
                   "data": {"id": "PAY_999"}}
        url = "/api/postado/webhook/mp/?preapproval_id=SUB_123&data.id=PAY_999"
        with patch.dict('os.environ', {'MERCADO_PAGO_WEBHOOK_SECRET': SEGREDO}):
            response = self.client.post(
                url,
                data=json.dumps(payload),
                content_type='application/json',
                HTTP_X_SIGNATURE='ts=1700000000,v1=' + 'f' * 64,
                HTTP_X_REQUEST_ID='req-1',
            )
        self.assertEqual(response.status_code, 403)
        mock_generate_pack.delay.assert_not_called()

    def test_unknown_action_is_ignored(self):
        payload = {"action": "some.other.action"}
        url = "/api/postado/webhook/mp/?preapproval_id=SUB_123"
        with patch.dict('os.environ', {'MERCADO_PAGO_WEBHOOK_SECRET': SEGREDO}):
            response = self.client.post(
                url,
                data=json.dumps(payload),
                content_type='application/json',
                **_assinar(''),
            )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data['status'], 'ignored')


class TestSignupAPI(TestCase):
    def setUp(self):
        self.client = DjangoClient()

    def test_signup_creates_client(self):
        response = self.client.post(
            '/api/postado/signup/',
            data=json.dumps({
                'business_name': 'New Restaurant',
                'niche': 'restaurant',
                'tone': 'casual',
                'brand_colors': ['#FF0000'],
                'email': 'new@restaurant.com',
                'whatsapp': '61900000099',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(PostadoClient.objects.filter(email='new@restaurant.com').exists())

    def test_signup_invalid_niche_returns_400(self):
        response = self.client.post(
            '/api/postado/signup/',
            data=json.dumps({
                'business_name': 'X',
                'niche': 'invalid_niche',
                'tone': 'casual',
                'email': 'x@x.com',
                'whatsapp': '61900000001',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
