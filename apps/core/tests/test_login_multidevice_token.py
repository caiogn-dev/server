"""Login NÃO pode invalidar sessões de outros dispositivos.

Regressão do incidente COEX 14/jul: o LoginView rotacionava o token a cada
login (delete + create), então qualquer login novo matava o token de todas as
outras abas/dispositivos do mesmo usuário. Uma aba "morta" burnou o code do
Embedded Signup com 401 e o onboarding nunca aconteceu.

Contrato: login retorna sempre um token válido e tokens previamente emitidos
continuam autenticando (comportamento padrão do DRF obtain_auth_token).
Logout continua sendo o único caminho que invalida o token.
"""
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

User = get_user_model()

PASSWORD = 'senha-forte-123'


class LoginMultiDeviceTokenTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='multidevice', email='multi@device.com', password=PASSWORD,
        )

    def _login(self):
        resp = self.client.post(
            '/api/v1/auth/login/',
            {'email': 'multi@device.com', 'password': PASSWORD},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.data['token']

    def test_second_login_keeps_first_token_valid(self):
        token_a = self._login()  # dispositivo A
        token_b = self._login()  # dispositivo B

        # Token do dispositivo A continua autenticando
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token_a}')
        resp = self.client.get('/api/v1/auth/me/')
        self.assertEqual(
            resp.status_code, 200,
            'Login em outro dispositivo invalidou a sessão anterior',
        )

        # E o token retornado no segundo login também é válido
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token_b}')
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 200)

    def test_login_rotates_token_expired_by_ttl(self):
        """Token além do AUTH_TOKEN_TTL_DAYS deve ser rotacionado no login,
        senão o login devolve um token que o TokenExpirationMiddleware rejeita
        (loop de 401)."""
        from datetime import timedelta
        from django.conf import settings
        from django.utils import timezone

        ttl = settings.AUTH_TOKEN_TTL_DAYS
        if ttl is None:
            self.skipTest('TTL de token desabilitado')

        old = Token.objects.create(user=self.user)
        Token.objects.filter(pk=old.pk).update(
            created=timezone.now() - timedelta(days=ttl + 1)
        )

        token = self._login()
        self.assertNotEqual(token, old.key, 'Login deve rotacionar token vencido')

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 200)

    def test_logout_still_invalidates_token(self):
        token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(self.client.post('/api/v1/auth/logout/').status_code, 200)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 401)
