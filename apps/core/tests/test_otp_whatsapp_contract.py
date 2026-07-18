"""
Testes de contrato para o fluxo OTP WhatsApp.

Cobre os invariantes críticos:
- Geração CSPRNG de código de 6 dígitos
- Hash HMAC-SHA256 (nunca armazena código em texto puro no cache)
- verify_code: comparação em tempo constante, bloqueio após MAX_ATTEMPTS,
  expiração, limpeza de cache no sucesso
- send_auth_code: rate-limit (código já enviado), código nunca em plaintext
  no cache, cache limpo em caso de erro
- resend_code: cooldown enforcement
- Views AllowAny: não expondo str(WhatsAppAuthError) na resposta HTTP (P1)

Todos SimpleTestCase — sem Docker/PostgreSQL/Redis.
Rodar: DJANGO_SETTINGS_MODULE=config.settings.test_serializer \\
         python manage.py test apps.core.tests.test_otp_whatsapp_contract -v 2
"""
import hashlib
import hmac as _hmac
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from apps.core.auth.whatsapp_auth import WhatsAppAuthError, WhatsAppAuthService


class TestOTPGenerate(SimpleTestCase):
    """Geração de código OTP."""

    def test_code_has_correct_length(self):
        self.assertEqual(len(WhatsAppAuthService.generate_code()), WhatsAppAuthService.CODE_LENGTH)

    def test_code_is_digits_only(self):
        code = WhatsAppAuthService.generate_code()
        self.assertTrue(code.isdigit(), f"Código deve ser numérico: {code!r}")

    def test_code_is_variable(self):
        """100 amostras devem ter pelo menos 2 valores distintos (CSPRNG)."""
        codes = {WhatsAppAuthService.generate_code() for _ in range(100)}
        self.assertGreater(len(codes), 1, "100 códigos devem ter pelo menos 2 valores distintos")


class TestOTPHash(SimpleTestCase):
    """HMAC-SHA256 do código OTP."""

    def test_hash_is_hmac_sha256(self):
        """Confirma que _hash_code usa HMAC-SHA256 com a SECRET_KEY."""
        with self.settings(SECRET_KEY='chave-de-teste'):
            expected = _hmac.new(b'chave-de-teste', b'123456', hashlib.sha256).hexdigest()
            self.assertEqual(WhatsAppAuthService._hash_code('123456'), expected)

    def test_different_codes_different_hashes(self):
        with self.settings(SECRET_KEY='chave-de-teste'):
            self.assertNotEqual(
                WhatsAppAuthService._hash_code('111111'),
                WhatsAppAuthService._hash_code('999999'),
            )


class TestOTPVerifyCode(SimpleTestCase):
    """Verificação de código OTP."""

    def _stored(self, code, attempts=0, minutes_ago=0):
        with self.settings(SECRET_KEY='chave-de-teste'):
            return {
                'code_hash': WhatsAppAuthService._hash_code(code),
                'attempts': attempts,
                'created_at': (timezone.now() - timedelta(minutes=minutes_ago)).isoformat(),
                'phone': '5511999999999',
                'whatsapp_account_id': 'account-uuid',
            }

    def test_correct_code_returns_valid_true(self):
        with self.settings(SECRET_KEY='chave-de-teste'), \
             patch('apps.core.auth.whatsapp_auth.cache') as mock_cache:
            mock_cache.get.return_value = self._stored('123456')
            result = WhatsAppAuthService.verify_code('+5511999999999', '123456')
        self.assertTrue(result['valid'])

    def test_correct_code_clears_cache(self):
        with self.settings(SECRET_KEY='chave-de-teste'), \
             patch('apps.core.auth.whatsapp_auth.cache') as mock_cache:
            mock_cache.get.return_value = self._stored('123456')
            WhatsAppAuthService.verify_code('+5511999999999', '123456')
        mock_cache.delete.assert_called_once()

    def test_wrong_code_returns_invalid_and_increments_attempts(self):
        with self.settings(SECRET_KEY='chave-de-teste'), \
             patch('apps.core.auth.whatsapp_auth.cache') as mock_cache:
            mock_cache.get.return_value = self._stored('123456', attempts=0)
            result = WhatsAppAuthService.verify_code('+5511999999999', '000000')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error'], 'invalid_code')
        updated = mock_cache.set.call_args[0][1]
        self.assertEqual(updated['attempts'], 1)

    def test_max_attempts_locks_out(self):
        with self.settings(SECRET_KEY='chave-de-teste'), \
             patch('apps.core.auth.whatsapp_auth.cache') as mock_cache:
            mock_cache.get.return_value = self._stored('123456', attempts=WhatsAppAuthService.MAX_ATTEMPTS)
            result = WhatsAppAuthService.verify_code('+5511999999999', '123456')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error'], 'too_many_attempts')
        mock_cache.delete.assert_called_once()

    def test_expired_code_returns_code_expired(self):
        with patch('apps.core.auth.whatsapp_auth.cache') as mock_cache:
            mock_cache.get.return_value = None
            result = WhatsAppAuthService.verify_code('+5511999999999', '123456')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error'], 'code_expired')

    def test_uses_constant_time_comparison(self):
        """verify_code deve usar hmac.compare_digest (resistência a timing attacks)."""
        import inspect
        source = inspect.getsource(WhatsAppAuthService.verify_code)
        self.assertIn(
            'compare_digest', source,
            "verify_code deve usar hmac.compare_digest para comparação em tempo constante",
        )

    def test_response_does_not_contain_code_plaintext(self):
        """Código verificado nunca deve aparecer em texto puro na resposta."""
        with self.settings(SECRET_KEY='chave-de-teste'), \
             patch('apps.core.auth.whatsapp_auth.cache') as mock_cache:
            mock_cache.get.return_value = self._stored('123456')
            result = WhatsAppAuthService.verify_code('+5511999999999', '123456')
        self.assertNotIn('code', result)
        for v in result.values():
            if isinstance(v, str):
                self.assertNotEqual(v, '123456', "Código não deve aparecer em texto puro")

    def test_remaining_attempts_counted_correctly(self):
        with self.settings(SECRET_KEY='chave-de-teste'), \
             patch('apps.core.auth.whatsapp_auth.cache') as mock_cache:
            mock_cache.get.return_value = self._stored('123456', attempts=1)
            result = WhatsAppAuthService.verify_code('+5511999999999', '000000')
        expected_remaining = WhatsAppAuthService.MAX_ATTEMPTS - 2
        self.assertEqual(result['remaining_attempts'], expected_remaining)


class TestOTPSendAuthCode(SimpleTestCase):
    """Envio de código OTP."""

    def test_rate_limit_when_code_already_sent(self):
        existing = {
            'code_hash': 'somehash',
            'attempts': 0,
            'created_at': timezone.now().isoformat(),
            'phone': '5511999999999',
            'whatsapp_account_id': 'account-uuid',
        }
        with patch('apps.core.auth.whatsapp_auth.cache') as mock_cache:
            mock_cache.get.return_value = existing
            result = WhatsAppAuthService.send_auth_code('+5511999999999', 'account-uuid')
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'code_already_sent')

    def test_code_stored_as_hash_not_plaintext(self):
        """Código nunca deve ser armazenado em texto puro no cache."""
        stored_value = {}

        def capture_set(key, value, timeout=None):
            stored_value.update(value)

        mock_service = MagicMock()
        mock_service.send_template_message.return_value = {'messages': [{'id': 'wamid.1'}]}

        with self.settings(SECRET_KEY='chave-de-teste'), \
             patch('apps.core.auth.whatsapp_auth.cache') as mock_cache, \
             patch('apps.core.auth.whatsapp_auth.MessageService', return_value=mock_service):
            mock_cache.get.return_value = None
            mock_cache.set.side_effect = capture_set
            WhatsAppAuthService.send_auth_code('+5511999999999', 'account-uuid')

        self.assertIn('code_hash', stored_value, "Cache deve conter 'code_hash'")
        self.assertNotIn('code', stored_value, "Cache NÃO deve conter 'code' em texto puro")

    def test_cache_cleared_on_all_send_methods_fail(self):
        """Cache deve ser invalidado quando todos os métodos de envio falham."""
        mock_service = MagicMock()
        mock_service.send_template_message.side_effect = Exception("template error")
        mock_service.send_text_message.side_effect = Exception("text fallback error")

        with patch('apps.core.auth.whatsapp_auth.cache') as mock_cache, \
             patch('apps.core.auth.whatsapp_auth.MessageService', return_value=mock_service):
            mock_cache.get.return_value = None
            with self.assertRaises(WhatsAppAuthError):
                WhatsAppAuthService.send_auth_code('+5511999999999', 'account-uuid')
            mock_cache.delete.assert_called()


class TestOTPResendCode(SimpleTestCase):
    """Reenvio de código com cooldown."""

    def test_resend_within_cooldown_blocked(self):
        existing = {
            'code_hash': 'somehash',
            'attempts': 0,
            'created_at': timezone.now().isoformat(),
            'phone': '5511999999999',
            'whatsapp_account_id': 'account-uuid',
        }
        with patch('apps.core.auth.whatsapp_auth.cache') as mock_cache:
            mock_cache.get.return_value = existing
            result = WhatsAppAuthService.resend_code('+5511999999999', 'account-uuid')
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'resend_too_soon')
        self.assertIn('retry_after', result)

    def test_resend_after_cooldown_clears_cache_and_resends(self):
        """Após cooldown expirado, limpa o cache anterior e reenvia."""
        created_at = (
            timezone.now() - timedelta(seconds=WhatsAppAuthService.RESEND_COOLDOWN_SECONDS + 10)
        ).isoformat()
        existing = {
            'code_hash': 'somehash',
            'attempts': 0,
            'created_at': created_at,
            'phone': '5511999999999',
            'whatsapp_account_id': 'account-uuid',
        }
        mock_service = MagicMock()
        mock_service.send_template_message.return_value = {'messages': [{'id': 'wamid.1'}]}

        with self.settings(SECRET_KEY='chave-de-teste'), \
             patch('apps.core.auth.whatsapp_auth.cache') as mock_cache, \
             patch('apps.core.auth.whatsapp_auth.MessageService', return_value=mock_service):
            mock_cache.get.side_effect = [existing, None]
            mock_cache.set.return_value = None
            result = WhatsAppAuthService.resend_code('+5511999999999', 'account-uuid')

        mock_cache.delete.assert_called()
        self.assertTrue(result.get('success', False))


class TestOTPNormalizePhone(SimpleTestCase):
    """Normalização de número de telefone."""

    def test_adds_55_prefix_if_missing(self):
        result = WhatsAppAuthService._normalize_phone('11999999999')
        self.assertTrue(result.startswith('55'))

    def test_does_not_double_55_prefix(self):
        result = WhatsAppAuthService._normalize_phone('+5511999999999')
        self.assertTrue(result.startswith('55'))
        self.assertFalse(result.startswith('5555'))

    def test_strips_non_digit_characters(self):
        result = WhatsAppAuthService._normalize_phone('+55 (11) 99999-9999')
        self.assertTrue(result.isdigit())


class TestOTPViewInfoDisclosure(SimpleTestCase):
    """Views AllowAny de OTP não devem vazar str(WhatsAppAuthError) na resposta HTTP."""

    def test_send_view_hides_whatsapp_auth_error_details(self):
        """POST /api/v1/auth/whatsapp/send/ não deve expor mensagem interna de erro."""
        from apps.core.auth.views import WhatsAppAuthThrottle, send_whatsapp_auth_code
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.post(
            '/api/v1/auth/whatsapp/send/',
            {'phone_number': '+5511999999999', 'whatsapp_account_id': 'uuid-123'},
            format='json',
        )
        internal_msg = 'HTTPSConnectionPool(host=api.meta.interno:443): Max retries exceeded'
        with patch.object(WhatsAppAuthThrottle, 'allow_request', return_value=True), \
             patch(
                 'apps.core.auth.views.WhatsAppAuthService.send_auth_code',
                 side_effect=WhatsAppAuthError(internal_msg),
             ):
            response = send_whatsapp_auth_code(request)

        self.assertEqual(response.status_code, 500)
        response_str = str(response.data)
        self.assertNotIn('api.meta.interno', response_str,
                         "Host interno não deve aparecer na resposta")
        self.assertNotIn('Max retries exceeded', response_str,
                         "Detalhe de erro de rede não deve aparecer na resposta")
        self.assertIn('error', response.data)

    def test_resend_view_hides_whatsapp_auth_error_details(self):
        """POST /api/v1/auth/whatsapp/resend/ não deve expor mensagem interna de erro."""
        from apps.core.auth.views import WhatsAppAuthThrottle, resend_whatsapp_auth_code
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.post(
            '/api/v1/auth/whatsapp/resend/',
            {'phone_number': '+5511999999999', 'whatsapp_account_id': 'uuid-123'},
            format='json',
        )
        internal_msg = 'SMTP connection error: smtp.interno:587 Connection refused (login=root)'
        with patch.object(WhatsAppAuthThrottle, 'allow_request', return_value=True), \
             patch(
                 'apps.core.auth.views.WhatsAppAuthService.resend_code',
                 side_effect=WhatsAppAuthError(internal_msg),
             ):
            response = resend_whatsapp_auth_code(request)

        self.assertEqual(response.status_code, 500)
        response_str = str(response.data)
        self.assertNotIn('smtp.interno', response_str,
                         "Host interno não deve aparecer na resposta")
        self.assertNotIn('Connection refused', response_str,
                         "Detalhe de conexão não deve aparecer na resposta")
        self.assertIn('error', response.data)
