"""Testes da autenticação SSE (A1).

Objetivo: não vazar token de auth na query string da URL (logs/histórico).
Mantém compat com ?token= (deprecado) e adiciona caminhos seguros:
- ticket de uso único e curta duração (?ticket=)
- header Authorization: Token <key>
- cookie sse_token
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, RequestFactory
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.core.sse_views import BaseSSEView, issue_sse_ticket

User = get_user_model()


class SSEAuthTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='sseu', email='sseu@x.com', password='x'
        )
        self.token = Token.objects.create(user=self.user)
        self.rf = RequestFactory()
        self.view = BaseSSEView()

    def test_header_auth_resolves_user(self):
        req = self.rf.get('/api/sse/orders/', HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.assertEqual(self.view.check_authentication(req), self.user)

    def test_cookie_auth_resolves_user(self):
        req = self.rf.get('/api/sse/orders/')
        req.COOKIES['sse_token'] = self.token.key
        self.assertEqual(self.view.check_authentication(req), self.user)

    def test_single_use_ticket_resolves_then_expires(self):
        ticket = issue_sse_ticket(self.user)
        req = self.rf.get(f'/api/sse/orders/?ticket={ticket}')
        self.assertEqual(self.view.check_authentication(req), self.user)
        # Segundo uso do mesmo ticket falha (uso único).
        req2 = self.rf.get(f'/api/sse/orders/?ticket={ticket}')
        self.assertIsNone(self.view.check_authentication(req2))

    def test_legacy_query_token_still_works(self):
        req = self.rf.get(f'/api/sse/orders/?token={self.token.key}')
        self.assertEqual(self.view.check_authentication(req), self.user)

    def test_no_credentials_returns_none(self):
        req = self.rf.get('/api/sse/orders/')
        self.assertIsNone(self.view.check_authentication(req))

    def test_ticket_endpoint_requires_auth(self):
        client = APIClient()
        resp = client.post('/api/sse/ticket/')
        self.assertEqual(resp.status_code, 401)

    def test_ticket_endpoint_mints_usable_ticket(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        resp = client.post('/api/sse/ticket/')
        self.assertEqual(resp.status_code, 200, resp.content)
        ticket = resp.json()['ticket']
        req = self.rf.get(f'/api/sse/orders/?ticket={ticket}')
        self.assertEqual(self.view.check_authentication(req), self.user)
