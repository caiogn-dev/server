"""Embedded Signup — dados internos não devem vazar nas respostas de erro.

Bug (P1-a): quando EmbeddedSignupService.onboard() lança uma Exception genérica
(falha de rede, timeout etc.) a view retornava `f'Falha no onboarding: {exc}'` —
tokens/URLs internas da Meta podiam aparecer na resposta 502.

Bug (P1-b): EmbeddedSignupError (falha no exchange_code) incluía `data.get('error', data)`
no str(exc) — se `data` não tivesse chave 'error', o dict inteiro (fbtrace_id, type, code,
sub_code etc.) aparecia na resposta 400.

Correções:
- view: `except Exception` → mensagem estática na resposta 502
- service: `exchange_code` extrai apenas `error.message` da resposta da Meta
"""
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.whatsapp.services.embedded_signup_service import EmbeddedSignupService

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


class ExchangeCodeErrorSanitizationTest(APITestCase):
    """exchange_code não deve incluir o dict bruto da Meta no str(exc).

    Quando a API de token da Meta retorna erro sem 'access_token', o dict de
    resposta (com fbtrace_id, type, code, sub_code etc.) não deve aparecer na
    mensagem da EmbeddedSignupError — apenas o campo 'message' da Meta.
    """

    def _make_svc(self):
        svc = EmbeddedSignupService.__new__(EmbeddedSignupService)
        svc.base = 'https://graph.facebook.com/v19.0'
        svc.app_id = 'APP_ID'
        svc.app_secret = 'APP_SECRET'
        return svc

    def test_dict_bruto_nao_aparece_na_mensagem_de_erro(self):
        """fbtrace_id e campos técnicos da Meta não devem aparecer em str(exc)."""
        meta_response = {
            'error': {
                'message': 'Invalid OAuth 2.0 access token.',
                'type': 'OAuthException',
                'code': 190,
                'fbtrace_id': 'AbCdEfGhIjK_SENSITIVE',
            }
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = meta_response

        svc = self._make_svc()
        with patch('requests.get', return_value=mock_resp):
            from apps.whatsapp.services.embedded_signup_service import EmbeddedSignupError
            with self.assertRaises(EmbeddedSignupError) as ctx:
                svc.exchange_code('bad-code')

        error_str = str(ctx.exception)
        self.assertNotIn('fbtrace_id', error_str,
                         'fbtrace_id da Meta não deve aparecer na mensagem de erro')
        self.assertNotIn('AbCdEfGhIjK_SENSITIVE', error_str,
                         'Valor do fbtrace_id não deve aparecer na mensagem de erro')
        self.assertNotIn('OAuthException', error_str,
                         'Tipo de erro técnico da Meta não deve aparecer na mensagem')
        self.assertIn('Invalid OAuth 2.0 access token.', error_str,
                      'Mensagem legível da Meta deve ser preservada para o operador')

    def test_resposta_sem_chave_error_usa_mensagem_generica(self):
        """Quando Meta retorna formato inesperado sem 'error', não deve serializar o dict inteiro."""
        meta_response = {'some_unexpected_field': 'value', 'internal_id': 'SENSITIVE_123'}
        mock_resp = MagicMock()
        mock_resp.json.return_value = meta_response

        svc = self._make_svc()
        with patch('requests.get', return_value=mock_resp):
            from apps.whatsapp.services.embedded_signup_service import EmbeddedSignupError
            with self.assertRaises(EmbeddedSignupError) as ctx:
                svc.exchange_code('bad-code')

        error_str = str(ctx.exception)
        self.assertNotIn('SENSITIVE_123', error_str,
                         'Campos inesperados da resposta Meta não devem aparecer na mensagem')
        self.assertIn('código inválido ou expirado', error_str)
