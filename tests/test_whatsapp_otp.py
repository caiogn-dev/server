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

    def test_no_button_payload_injected(self):
        """Regression: COPY_CODE button must come from the approved template, not the payload."""
        configs = WhatsAppAuthService._get_template_configs('999999')
        for cfg in configs:
            for comp in cfg.get('components', []):
                self.assertNotEqual(comp.get('type'), 'button',
                    "Payload must NOT inject a button component — the Meta template owns it.")

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
        self.assertEqual(len(stored['code']), 6)

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
