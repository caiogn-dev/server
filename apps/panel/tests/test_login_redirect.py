"""A3 — open redirect no login do painel.

O parâmetro ?next= não pode redirecionar para hosts externos.
"""
from django.contrib.auth.models import User
from django.test import TestCase, Client


class PanelLoginRedirectTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='panu', email='panu@x.com', password='secret123', is_active=True
        )

    def _login(self, next_param):
        return self.client.post(
            f'/panel/login/?next={next_param}',
            {'email': 'panu@x.com', 'password': 'secret123'},
        )

    def test_external_next_is_rejected(self):
        resp = self._login('https://evil.com/phish')
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.com', resp['Location'])
        self.assertTrue(resp['Location'].endswith('/panel/stores/') or resp['Location'].endswith('/stores/'))

    def test_protocol_relative_next_is_rejected(self):
        resp = self._login('//evil.com/phish')
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.com', resp['Location'])

    def test_safe_relative_next_is_honored(self):
        resp = self._login('/panel/orders/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/panel/orders/')
