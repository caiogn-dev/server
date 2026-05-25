from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(POSTADO_ADMIN_TOKEN='test-token-123')
class AdminAuthTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_no_token_returns_401(self):
        response = self.client.get('/api/postado/admin/dashboard/')
        self.assertEqual(response.status_code, 401)

    def test_wrong_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer wrong-token')
        response = self.client.get('/api/postado/admin/dashboard/')
        self.assertEqual(response.status_code, 401)

    def test_correct_token_returns_200(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer test-token-123')
        response = self.client.get('/api/postado/admin/dashboard/')
        self.assertEqual(response.status_code, 200)
