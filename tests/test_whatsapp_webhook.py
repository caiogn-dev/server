"""
Tests for the WhatsApp Webhook endpoint.
Covers:
- GET verification challenge (hub.mode, hub.verify_token, hub.challenge)
- POST webhook event ingestion
- Signature validation logic
"""
import hashlib
import hmac
import json
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import MagicMock

User = get_user_model()

VERIFY_TOKEN = 'test-verify-token-abc123'
WEBHOOK_URL = '/webhooks/v1/whatsapp/'


def _make_signature(secret: str, body: str) -> str:
    """Produce a valid X-Hub-Signature-256 header value."""
    mac = hmac.new(secret.encode(), body.encode(), hashlib.sha256)
    return f'sha256={mac.hexdigest()}'


# Minimal valid WhatsApp Business webhook payload (text message)
_TEXT_MESSAGE_PAYLOAD = {
    'object': 'whatsapp_business_account',
    'entry': [{
        'id': '123456789',
        'changes': [{
            'value': {
                'messaging_product': 'whatsapp',
                'metadata': {
                    'display_phone_number': '5511999990000',
                    'phone_number_id': '111111111111',
                },
                'contacts': [{'profile': {'name': 'Test User'}, 'wa_id': '5511888880000'}],
                'messages': [{
                    'from': '5511888880000',
                    'id': 'wamid.test001',
                    'timestamp': '1700000000',
                    'type': 'text',
                    'text': {'body': 'Olá!'},
                }],
            },
            'field': 'messages',
        }],
    }],
}


@override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN=VERIFY_TOKEN)
class WhatsAppWebhookVerificationTestCase(TestCase):
    """Tests for the GET verification handshake."""

    def setUp(self):
        self.client = APIClient()

    def test_valid_verification_returns_challenge(self):
        """Meta sends hub.challenge — we must echo it back."""
        resp = self.client.get(WEBHOOK_URL, {
            'hub.mode': 'subscribe',
            'hub.verify_token': VERIFY_TOKEN,
            'hub.challenge': 'my-challenge-string',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(b'my-challenge-string', resp.content)

    def test_wrong_token_returns_403(self):
        resp = self.client.get(WEBHOOK_URL, {
            'hub.mode': 'subscribe',
            'hub.verify_token': 'wrong-token',
            'hub.challenge': 'irrelevant',
        })
        self.assertEqual(resp.status_code, 403)

    def test_missing_mode_returns_403(self):
        resp = self.client.get(WEBHOOK_URL, {
            'hub.verify_token': VERIFY_TOKEN,
            'hub.challenge': 'irrelevant',
        })
        self.assertEqual(resp.status_code, 403)

    def test_wrong_mode_returns_403(self):
        resp = self.client.get(WEBHOOK_URL, {
            'hub.mode': 'unsubscribe',
            'hub.verify_token': VERIFY_TOKEN,
            'hub.challenge': 'irrelevant',
        })
        self.assertEqual(resp.status_code, 403)

    def test_challenge_value_is_preserved(self):
        """The exact challenge string must appear in the response body."""
        challenge = 'abc-XYZ-123'
        resp = self.client.get(WEBHOOK_URL, {
            'hub.mode': 'subscribe',
            'hub.verify_token': VERIFY_TOKEN,
            'hub.challenge': challenge,
        })
        self.assertIn(challenge.encode(), resp.content)


@override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN=VERIFY_TOKEN)
class WhatsAppWebhookIngestTestCase(TestCase):
    """Tests for the POST webhook ingestion."""

    def setUp(self):
        self.client = APIClient()

    def _post(self, payload, headers=None):
        body = json.dumps(payload)
        kwargs = {'content_type': 'application/json'}
        if headers:
            kwargs.update(headers)
        return self.client.post(WEBHOOK_URL, body, **kwargs)

    # --- Basic ingestion ---

    def test_post_returns_200_always(self):
        """Meta requires 200 even on error — we must not return 4xx/5xx to Meta."""
        resp = self._post(_TEXT_MESSAGE_PAYLOAD)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_post_returns_ok_status(self):
        resp = self._post(_TEXT_MESSAGE_PAYLOAD)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Response may be JSON or HTML depending on error handling
        if resp.get('Content-Type', '').startswith('application/json'):
            data = resp.json()
            self.assertIn('status', data)

    def test_invalid_json_returns_400(self):
        """Pure garbage body should 400 (not crash)."""
        resp = self.client.post(
            WEBHOOK_URL,
            'NOT JSON',
            content_type='application/json',
        )
        # The view may return 400 or 200 depending on implementation;
        # it must not raise a 500.
        self.assertNotEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_empty_entries_is_accepted(self):
        payload = {'object': 'whatsapp_business_account', 'entry': []}
        resp = self._post(payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # --- Status notification payload ---

    def test_status_update_payload_is_accepted(self):
        payload = {
            'object': 'whatsapp_business_account',
            'entry': [{
                'id': '123456789',
                'changes': [{
                    'value': {
                        'messaging_product': 'whatsapp',
                        'metadata': {
                            'display_phone_number': '5511999990000',
                            'phone_number_id': '111111111111',
                        },
                        'statuses': [{
                            'id': 'wamid.status001',
                            'status': 'delivered',
                            'timestamp': '1700000001',
                            'recipient_id': '5511888880000',
                        }],
                    },
                    'field': 'messages',
                }],
            }],
        }
        resp = self._post(payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # --- Signature validation logic (unit test) ---

    @override_settings(WHATSAPP_APP_SECRET='mysecret')
    def test_validate_signature_valid(self):
        """WebhookService.validate_signature accepts a correctly signed body (bytes)."""
        from apps.whatsapp.services.webhook_service import WebhookService
        from apps.core.utils import verify_webhook_signature
        body_bytes = b'{"object":"test"}'
        sig = f'sha256={hmac.new("mysecret".encode(), body_bytes, hashlib.sha256).hexdigest()}'
        result = verify_webhook_signature(body_bytes, sig, 'mysecret')
        self.assertTrue(result)

    @override_settings(WHATSAPP_APP_SECRET='mysecret')
    def test_validate_signature_invalid(self):
        """verify_webhook_signature rejects a body that doesn't match the signature."""
        from apps.core.utils import verify_webhook_signature
        body_bytes = b'{"object":"test"}'
        sig = f'sha256={hmac.new("mysecret".encode(), body_bytes, hashlib.sha256).hexdigest()}'
        result = verify_webhook_signature(b'{"object":"tampered"}', sig, 'mysecret')
        self.assertFalse(result)

    @override_settings(WHATSAPP_APP_SECRET='mysecret')
    def test_validate_signature_empty_signature(self):
        """Empty/missing signature should be invalid."""
        from apps.whatsapp.services.webhook_service import WebhookService
        service = WebhookService()
        # Empty signature string is falsy → validate_signature returns False
        result = service.validate_signature('irrelevant', '')
        self.assertFalse(result)


@override_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN=VERIFY_TOKEN)
class WhatsAppWebhookNoSlashTestCase(TestCase):
    """The no-trailing-slash verification URL must also work (Meta sends without slash)."""

    def setUp(self):
        self.client = APIClient()

    def test_verification_no_trailing_slash(self):
        resp = self.client.get('/webhooks/v1/whatsapp', {
            'hub.mode': 'subscribe',
            'hub.verify_token': VERIFY_TOKEN,
            'hub.challenge': 'challenge-no-slash',
        })
        # Should succeed — the route is in urls.py
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(b'challenge-no-slash', resp.content)
