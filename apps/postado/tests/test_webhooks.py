import json
from unittest.mock import patch
from django.test import TestCase, Client as DjangoClient
from apps.postado.models import PostadoClient, PostadoPack


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
        url = "/api/postado/webhook/mp/?preapproval_id=SUB_123"
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        mock_generate_pack.delay.assert_called_once()

    def test_unknown_action_is_ignored(self):
        payload = {"action": "some.other.action"}
        url = "/api/postado/webhook/mp/?preapproval_id=SUB_123"
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
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
