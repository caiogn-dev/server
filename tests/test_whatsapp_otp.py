"""
Regression tests for WhatsApp OTP authentication.
Covers: phone normalization, code generation, cache lifecycle,
attempt limiting, expiry, and template config contract.
"""
from unittest.mock import patch, MagicMock

from django.core.cache import cache
from django.test import TestCase

from apps.core.auth.whatsapp_auth import WhatsAppAuthService


ACCOUNT_ID = '11111111-1111-1111-1111-111111111111'


def _seed_cache(phone: str, code: str, attempts: int = 0):
    """Helper: pre-populate cache as if send_auth_code already ran."""
    from django.utils import timezone
    key = WhatsAppAuthService._get_cache_key(phone)
    cache.set(key, {
        'code': code,
        'attempts': attempts,
        'created_at': timezone.now().isoformat(),
        'phone': phone,
        'whatsapp_account_id': ACCOUNT_ID,
    }, timeout=900)


class PhoneNormalizationTest(TestCase):
    def test_adds_brazil_prefix(self):
        self.assertEqual(WhatsAppAuthService._normalize_phone('63999999999'), '5563999999999')

    def test_keeps_existing_prefix(self):
        self.assertEqual(WhatsAppAuthService._normalize_phone('5563999999999'), '5563999999999')

    def test_strips_non_digits(self):
        self.assertEqual(WhatsAppAuthService._normalize_phone('+55 (63) 9-9999-9999'), '5563999999999')

    def test_plus_sign_stripped(self):
        result = WhatsAppAuthService._normalize_phone('+5511987654321')
        self.assertTrue(result.isdigit())
        self.assertTrue(result.startswith('55'))


class GenerateCodeTest(TestCase):
    def test_code_is_six_digits(self):
        code = WhatsAppAuthService.generate_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_codes_differ(self):
        codes = {WhatsAppAuthService.generate_code() for _ in range(20)}
        self.assertGreater(len(codes), 1)


class TemplateConfigTest(TestCase):
    def test_body_parameter_contains_code(self):
        configs = WhatsAppAuthService._get_template_configs('123456')
        self.assertGreater(len(configs), 0)
        body = configs[0]['components'][0]
        self.assertEqual(body['type'], 'body')
        self.assertEqual(body['parameters'][0]['text'], '123456')

    def test_button_payload_carries_code(self):
        """O template AUTH `codigo_verificacao` exige o código também no
        parâmetro do botão COPY_CODE — sem ele a Meta devolve #131008
        (50f4390b, 29/07). A regra antiga ("o template é dono do botão") foi
        revertida ali; ver também CLAUDE.md."""
        configs = WhatsAppAuthService._get_template_configs('999999')
        self.assertEqual(configs[0]['name'], 'codigo_verificacao')
        botoes = [c for c in configs[0]['components'] if c.get('type') == 'button']
        self.assertEqual(len(botoes), 1)
        self.assertEqual(botoes[0]['sub_type'], 'url')
        self.assertEqual(botoes[0]['index'], '0')
        self.assertEqual(botoes[0]['parameters'], [{'type': 'text', 'text': '999999'}])

    def test_template_name_is_set(self):
        configs = WhatsAppAuthService._get_template_configs('000000')
        self.assertTrue(all(cfg.get('name') for cfg in configs))


class VerifyCodeTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_valid_code_returns_valid_true(self):
        _seed_cache('5511999990001', '654321')
        result = WhatsAppAuthService.verify_code('5511999990001', '654321')
        self.assertTrue(result['valid'])

    def test_wrong_code_returns_valid_false(self):
        _seed_cache('5511999990002', '111111')
        result = WhatsAppAuthService.verify_code('5511999990002', '222222')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error'], 'invalid_code')

    def test_wrong_code_increments_attempts(self):
        _seed_cache('5511999990003', '111111')
        WhatsAppAuthService.verify_code('5511999990003', '000000')
        key = WhatsAppAuthService._get_cache_key('5511999990003')
        self.assertEqual(cache.get(key)['attempts'], 1)

    def test_expired_code_returns_code_expired(self):
        result = WhatsAppAuthService.verify_code('5511999990099', '123456')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error'], 'code_expired')

    def test_too_many_attempts_blocks_and_clears_cache(self):
        _seed_cache('5511999990004', '111111', attempts=WhatsAppAuthService.MAX_ATTEMPTS)
        result = WhatsAppAuthService.verify_code('5511999990004', '111111')
        self.assertFalse(result['valid'])
        self.assertEqual(result['error'], 'too_many_attempts')
        key = WhatsAppAuthService._get_cache_key('5511999990004')
        self.assertIsNone(cache.get(key), "Cache must be cleared after max attempts")

    def test_valid_code_clears_cache(self):
        _seed_cache('5511999990005', '777777')
        WhatsAppAuthService.verify_code('5511999990005', '777777')
        key = WhatsAppAuthService._get_cache_key('5511999990005')
        self.assertIsNone(cache.get(key), "Cache must be cleared after successful verify")

    def test_phone_normalization_on_verify(self):
        """Verify works regardless of phone format passed in."""
        _seed_cache('5511999990006', '888888')
        result = WhatsAppAuthService.verify_code('+55 11 99999-0006', '888888')
        self.assertTrue(result['valid'])

    def test_remaining_attempts_decrements(self):
        _seed_cache('5511999990007', '111111')
        result = WhatsAppAuthService.verify_code('5511999990007', '000000')
        self.assertEqual(result['remaining_attempts'], WhatsAppAuthService.MAX_ATTEMPTS - 1)


class SendAuthCodeRateLimitTest(TestCase):
    def setUp(self):
        cache.clear()

    @patch('apps.core.auth.whatsapp_auth.MessageService')
    def test_send_returns_already_sent_if_cache_exists(self, mock_ms_cls):
        _seed_cache('5511999990010', '123456')
        result = WhatsAppAuthService.send_auth_code('5511999990010', ACCOUNT_ID)
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'code_already_sent')
        mock_ms_cls.assert_not_called()

    @patch('apps.core.auth.whatsapp_auth.MessageService')
    def test_send_stores_code_in_cache(self, mock_ms_cls):
        mock_svc = MagicMock()
        mock_ms_cls.return_value = mock_svc
        mock_svc.send_template_message.return_value = {'messages': [{'id': 'wamid.test'}]}

        result = WhatsAppAuthService.send_auth_code('+5511999990011', ACCOUNT_ID)

        self.assertTrue(result['success'])
        key = WhatsAppAuthService._get_cache_key('5511999990011')
        stored = cache.get(key)
        self.assertIsNotNone(stored)
        # Desde 0d320852 (31/05) o cache guarda só o HMAC do código, nunca o
        # código em texto puro. O hash tem que bater com o código que foi no
        # template.
        self.assertNotIn('code', stored)
        enviado = mock_svc.send_template_message.call_args.kwargs['components'][0]['parameters'][0]['text']
        self.assertEqual(len(enviado), 6)
        self.assertEqual(stored['code_hash'], WhatsAppAuthService._hash_code(enviado))

    @patch('apps.core.auth.whatsapp_auth.MessageService')
    def test_send_clears_cache_on_all_templates_fail(self, mock_ms_cls):
        mock_svc = MagicMock()
        mock_ms_cls.return_value = mock_svc
        mock_svc.send_template_message.side_effect = Exception('template error')
        mock_svc.send_text_message.side_effect = Exception('text error')

        from apps.core.auth.whatsapp_auth import WhatsAppAuthError
        with self.assertRaises(WhatsAppAuthError):
            WhatsAppAuthService.send_auth_code('+5511999990012', ACCOUNT_ID)

        key = WhatsAppAuthService._get_cache_key('5511999990012')
        self.assertIsNone(cache.get(key), "Cache must be cleared when send fails")


class TextFallbackOnlyInsideWindowTest(TestCase):
    """OTP sai pelo template `codigo_verificacao`. O texto livre é último
    recurso e SÓ dentro da janela de 24 h (CLAUDE.md, regra de 26/04): fora
    dela a Meta aceita a chamada e depois devolve 131047 — o cliente lia
    "Código enviado", não recebia nada e ainda ficava 15 min barrado por
    `code_already_sent`."""

    TEL = '5563999990777'

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.whatsapp.models import WhatsAppAccount

        cache.clear()
        dono = get_user_model().objects.create_user(username='otp-janela', password='x')
        self.conta = WhatsAppAccount.objects.create(
            name='Oficial', phone_number_id='pn-otp-janela', waba_id='waba-otp',
            phone_number='+5563900000077', display_phone_number='+5563900000077',
            access_token_encrypted='x', owner=dono,
            status=WhatsAppAccount.AccountStatus.ACTIVE,
        )

    def _abrir_janela(self):
        from django.utils import timezone
        from apps.conversations.models import Conversation
        Conversation.objects.create(
            account=self.conta, phone_number=self.TEL,
            last_customer_message_at=timezone.now(),
        )

    def _template_falha(self, mock_ms_cls):
        mock_svc = MagicMock()
        mock_ms_cls.return_value = mock_svc
        mock_svc.send_template_message.side_effect = Exception('(#131008) Required parameter is missing')
        mock_svc.send_text_message.return_value = MagicMock(id='msg-1')
        return mock_svc

    @patch('apps.core.auth.whatsapp_auth.MessageService')
    def test_fora_da_janela_nao_manda_texto_livre(self, mock_ms_cls):
        from apps.core.auth.whatsapp_auth import WhatsAppAuthError
        mock_svc = self._template_falha(mock_ms_cls)

        with self.assertRaises(WhatsAppAuthError):
            WhatsAppAuthService.send_auth_code(self.TEL, str(self.conta.id))

        mock_svc.send_text_message.assert_not_called()
        key = WhatsAppAuthService._get_cache_key(self.TEL)
        self.assertIsNone(cache.get(key), 'sem envio, o cliente pode pedir de novo')

    @patch('apps.core.auth.whatsapp_auth.MessageService')
    def test_dentro_da_janela_texto_livre_e_ultimo_recurso(self, mock_ms_cls):
        self._abrir_janela()
        mock_svc = self._template_falha(mock_ms_cls)

        result = WhatsAppAuthService.send_auth_code(self.TEL, str(self.conta.id))

        self.assertTrue(result['success'])
        self.assertEqual(result['template_used'], 'text_fallback')
        mock_svc.send_text_message.assert_called_once()
