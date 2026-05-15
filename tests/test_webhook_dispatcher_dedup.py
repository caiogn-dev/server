"""
Tests for WebhookDispatcherView._extract_event_id deduplication logic.
"""
from django.test import TestCase

from apps.webhooks.dispatcher import WebhookDispatcherView


class ExtractEventIdTestCase(TestCase):
    def setUp(self):
        self.view = WebhookDispatcherView()

    def _call(self, provider, payload):
        return self.view._extract_event_id(provider, payload, {})

    # ── WhatsApp ──────────────────────────────────────────────────────────────

    def test_whatsapp_message_id(self):
        payload = {
            'entry': [{'changes': [{'value': {'messages': [{'id': 'wamid.abc123'}]}}]}]
        }
        result = self._call('whatsapp', payload)
        self.assertEqual(result, 'wa_msg_wamid.abc123')

    def test_whatsapp_status_update(self):
        payload = {
            'entry': [{'changes': [{'value': {'statuses': [{'id': 'wamid.xyz', 'status': 'delivered'}]}}]}]
        }
        result = self._call('whatsapp', payload)
        self.assertEqual(result, 'wa_status_wamid.xyz_delivered')

    def test_whatsapp_empty_payload_returns_none(self):
        self.assertIsNone(self._call('whatsapp', {}))

    # ── Instagram ─────────────────────────────────────────────────────────────

    def test_instagram_message_id(self):
        payload = {
            'entry': [{'messaging': [{'message': {'mid': 'mid.111'}, 'sender': {'id': '555'}}]}]
        }
        self.assertEqual(self._call('instagram', payload), 'instagram_msg_mid.111')

    def test_instagram_delivery_watermark(self):
        payload = {
            'entry': [{'messaging': [{'delivery': {'watermark': 9999}, 'sender': {'id': '555'}}]}]
        }
        self.assertEqual(self._call('instagram', payload), 'instagram_delivery_555_9999')

    def test_instagram_empty_returns_none(self):
        self.assertIsNone(self._call('instagram', {}))

    # ── Messenger ─────────────────────────────────────────────────────────────

    def test_messenger_message_id(self):
        payload = {
            'entry': [{'messaging': [{'message': {'mid': 'mid.222'}, 'sender': {'id': '999'}}]}]
        }
        self.assertEqual(self._call('messenger', payload), 'messenger_msg_mid.222')

    # ── Mercado Pago ──────────────────────────────────────────────────────────

    def test_mercadopago_payment_event(self):
        payload = {'id': 12345, 'action': 'payment.updated', 'type': 'payment'}
        self.assertEqual(self._call('mercadopago', payload), 'mp_payment.updated_12345')

    def test_mercadopago_data_nested_id(self):
        payload = {'data': {'id': '99999'}, 'action': 'payment.created', 'type': 'payment'}
        self.assertEqual(self._call('mercadopago', payload), 'mp_payment.created_99999')

    def test_mercadopago_no_id_returns_none(self):
        self.assertIsNone(self._call('mercadopago', {'type': 'payment'}))

    # ── Toca Delivery ─────────────────────────────────────────────────────────

    def test_toca_delivery_event_id(self):
        payload = {'event_id': 'toca-evt-789', 'status': 'delivered'}
        self.assertEqual(self._call('toca-delivery', payload), 'toca_toca-evt-789')

    def test_toca_delivery_fallback_id(self):
        payload = {'id': 'toca-order-456', 'status': 'shipped'}
        self.assertEqual(self._call('toca-delivery', payload), 'toca_toca-order-456')

    # ── Unknown provider ──────────────────────────────────────────────────────

    def test_unknown_provider_returns_none(self):
        self.assertIsNone(self._call('stripe', {'id': 'evt_123'}))
