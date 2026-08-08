"""Embedded Signup — mensagem de exceção interna não deve vazar na resposta 502.

Bug (P1): quando EmbeddedSignupService.onboard() lança uma Exception genérica
(falha de rede, timeout na API da Meta, erro interno etc.) a view retornava
`{'error': f'Falha no onboarding: {exc}'}` — ou seja, `str(exc)` ficava exposto
na resposta HTTP 502, podendo vazar URLs internas, tokens ou detalhes da API Meta.

Contrato correto:
- 502 mantido (falha real)
- `error` recebe mensagem genérica e segura
- Nenhum detalhe técnico da exceção vaza no corpo JSON
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

User = get_user_model()

_INTERNAL_MESSAGE = 'Meta API 500: internal_token=tok_meta_secret_XYZ endpoint=/v19.0/token'
_SIGNUP_URL = '/api/v1/whatsapp/accounts/embedded_signup/'


class EmbeddedSignupExcLeakTest(APITestCase):
    """Garante que str(exc) não vaza em error na rota embedded_signup."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-esignleak', email='esignleak@real.com', password='x'
        )
        token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def _post_signup(self):
        return self.client.post(
            _SIGNUP_URL,
            {
                'code': 'AQC_test_code',
                'waba_id': 'WABA_TEST_123',
                'phone_number_id': 'PHONE_TEST_456',
            },
            format='json',
        )

    def test_excecao_generica_nao_vaza_mensagem_interna(self):
        """str(exc) não deve aparecer no corpo da resposta 502."""
        with patch(
            'apps.whatsapp.services.embedded_signup_service.EmbeddedSignupService.onboard',
            side_effect=RuntimeError(_INTERNAL_MESSAGE),
        ):
            resp = self._post_signup()

        self.assertEqual(resp.status_code, 502, resp.data)
        error_msg = resp.data.get('error', '')
        self.assertNotIn(_INTERNAL_MESSAGE, error_msg,
                         'Mensagem interna da exceção não deve aparecer na resposta')
        self.assertNotIn('tok_meta_secret', error_msg,
                         'Tokens internos não devem vazar na resposta')

    def test_excecao_generica_retorna_mensagem_segura(self):
        """error deve ser mensagem genérica e segura, sem detalhes da exceção."""
        with patch(
            'apps.whatsapp.services.embedded_signup_service.EmbeddedSignupService.onboard',
            side_effect=RuntimeError(_INTERNAL_MESSAGE),
        ):
            resp = self._post_signup()

        self.assertEqual(resp.status_code, 502)
        self.assertEqual(
            resp.data.get('error'),
            'Falha no onboarding. Verifique os dados e tente novamente.',
        )
