"""
Regression tests for WhatsApp OTP API endpoints (send + verify).

Covers the HTTP-layer contracts:
 - POST /api/v1/auth/whatsapp/send/
 - POST /api/v1/auth/whatsapp/verify/

These tests mock WhatsAppAuthService and CustomerIdentityService so that
no real WhatsApp API calls or complex DB side-effects are needed.
"""
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from rest_framework.test import APIClient

from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()

SEND_URL = '/api/v1/auth/whatsapp/send/'
VERIFY_URL = '/api/v1/auth/whatsapp/verify/'

# Disable throttling for all tests in this module
NO_THROTTLE = override_settings(
    REST_FRAMEWORK={
        'DEFAULT_THROTTLE_CLASSES': [],
        'DEFAULT_THROTTLE_RATES': {},
    }
)


@NO_THROTTLE
class OTPWhatsAppTests(TestCase):
    """8 contract tests for the WhatsApp OTP send/verify API endpoints."""

    def setUp(self):
        self.client = APIClient()
        # Owner user required by WhatsAppAccount FK
        self.owner = User.objects.create_user(
            username='otp_test_owner',
            password='pass',
            email='otp_owner@test.local',
        )
        # Active WhatsApp account used by tests 3, 4, 7 and 8
        self.wa_account = WhatsAppAccount.objects.create(
            name='Test WA',
            phone_number_id='test-123',
            waba_id='test-waba',
            phone_number='5511000000000',
            display_phone_number='+55 11 00000-0000',
            access_token_encrypted='stub',
            status='active',
            owner=self.owner,
        )

    # ------------------------------------------------------------------ #
    # Send endpoint                                                        #
    # ------------------------------------------------------------------ #

    def test_send_missing_phone_returns_400(self):
        """POST /send/ with empty body must return 400."""
        response = self.client.post(SEND_URL, {}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_send_no_whatsapp_account_returns_400(self):
        """POST /send/ with a valid phone but no WA account → 400."""
        # Remove every WhatsApp account so _resolve_whatsapp_account_id returns ''
        WhatsAppAccount.objects.all().delete()
        response = self.client.post(
            SEND_URL,
            {'phone_number': '+5511999999999'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    @patch('apps.core.auth.views.WhatsAppAuthService.send_auth_code')
    def test_send_success_does_not_expose_code(self, mock_send):
        """The OTP code must be stripped from the API response."""
        mock_send.return_value = {
            'success': True,
            'code': '123456',
            'expires_in_minutes': 15,
            'expires_at': '2026-01-01T12:00:00Z',
            'message_id': 'wamid.test',
        }
        response = self.client.post(
            SEND_URL,
            {'phone_number': '+5511999999999'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('code', response.json())

    @patch('apps.core.auth.views.WhatsAppAuthService.send_auth_code')
    def test_send_success_returns_expires_fields(self, mock_send):
        """Successful send must include expires_in_minutes and expires_at."""
        mock_send.return_value = {
            'success': True,
            'code': '123456',
            'expires_in_minutes': 15,
            'expires_at': '2026-01-01T12:00:00Z',
            'message_id': 'wamid.test',
        }
        response = self.client.post(
            SEND_URL,
            {'phone_number': '+5511999999999'},
            format='json',
        )
        data = response.json()
        self.assertIn('expires_in_minutes', data)
        self.assertIn('expires_at', data)

    # ------------------------------------------------------------------ #
    # Verify endpoint                                                      #
    # ------------------------------------------------------------------ #

    def test_verify_missing_fields_returns_400(self):
        """POST /verify/ with empty body must return 400."""
        response = self.client.post(VERIFY_URL, {}, format='json')
        self.assertEqual(response.status_code, 400)

    @patch('apps.core.auth.views.WhatsAppAuthService.verify_code')
    def test_verify_invalid_code_returns_valid_false(self, mock_verify):
        """An invalid code response must propagate valid=False with status 200-range (400 per view)."""
        mock_verify.return_value = {
            'valid': False,
            'error': 'invalid_code',
            'remaining_attempts': 2,
        }
        response = self.client.post(
            VERIFY_URL,
            {'phone_number': '+5511999999999', 'code': '000000'},
            format='json',
        )
        data = response.json()
        self.assertFalse(data['valid'])
        # The view returns 400 for invalid codes
        self.assertEqual(response.status_code, 400)

    @patch('apps.core.auth.views.CustomerIdentityService.resolve_user')
    @patch('apps.core.auth.views.WhatsAppAuthService.verify_code')
    def test_verify_valid_code_returns_drf_token(self, mock_verify, mock_resolve):
        """A valid OTP must yield a DRF token and valid=True in the response."""
        # Set up a real user so Token.objects.get_or_create works
        real_user = User.objects.create_user(
            username='wa_customer_token',
            password='pass',
            email='wa_token@test.local',
        )
        profile_mock = MagicMock()
        profile_mock.phone = '5511999999999'

        mock_verify.return_value = {
            'valid': True,
            'phone_number': '5511999999999',
            'message': 'Autenticação realizada com sucesso',
            'user': {'name': 'Test User'},
        }
        mock_resolve.return_value = (real_user, profile_mock, True)

        response = self.client.post(
            VERIFY_URL,
            {'phone_number': '+5511999999999', 'code': '123456'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['valid'])
        self.assertIn('token', data)
        self.assertTrue(len(data['token']) > 0)

    @patch('apps.core.auth.views.CustomerIdentityService.resolve_user')
    @patch('apps.core.auth.views.WhatsAppAuthService.verify_code')
    def test_verify_does_not_expose_placeholder_email(self, mock_verify, mock_resolve):
        """Placeholder @pastita.local emails must never appear in the verify response."""
        real_user = User.objects.create_user(
            username='wa_customer_email',
            password='pass',
            email='wa_email@test.local',
        )
        profile_mock = MagicMock()
        profile_mock.phone = '5511999999999'

        mock_verify.return_value = {
            'valid': True,
            'phone_number': '5511999999999',
            'message': 'Autenticação realizada com sucesso',
            'user': {'name': 'Test User'},
        }
        mock_resolve.return_value = (real_user, profile_mock, False)

        response = self.client.post(
            VERIFY_URL,
            {'phone_number': '+5511999999999', 'code': '123456'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('@pastita.local', str(response.json()))
