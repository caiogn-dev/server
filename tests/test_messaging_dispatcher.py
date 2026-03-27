"""
Unit tests for the unified MessageDispatcher.
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase

from apps.messaging.dispatcher import MessageDispatcher, DispatchMessage, SUPPORTED_CHANNELS
from apps.messaging.providers.base import ProviderResult


class DispatcherChannelValidationTest(TestCase):
    def setUp(self):
        self.dispatcher = MessageDispatcher()

    def test_unsupported_channel_returns_failure(self):
        result = self.dispatcher.send(
            channel='telegram',
            recipient='+5511999999999',
            content={'type': 'text', 'text': 'hi'},
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, 'UNSUPPORTED_CHANNEL')

    def test_supported_channels_listed(self):
        channels = self.dispatcher.channels()
        self.assertIn('whatsapp', channels)
        self.assertIn('email', channels)
        self.assertIn('instagram', channels)


class DispatcherWhatsAppTest(TestCase):
    def setUp(self):
        self.dispatcher = MessageDispatcher()

    @patch('apps.messaging.dispatcher._get_provider')
    def test_send_calls_provider(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.format_recipient.return_value = '+5511999999999'
        mock_provider.validate_recipient.return_value = True
        mock_provider.send.return_value = ProviderResult(success=True, external_id='wamid.123')
        mock_get_provider.return_value = mock_provider

        result = self.dispatcher.send(
            channel='whatsapp',
            recipient='+5511999999999',
            content={'type': 'text', 'text': 'Olá!'},
            source='test',
            source_id='test-001',
        )

        self.assertTrue(result.success)
        self.assertEqual(result.external_id, 'wamid.123')
        mock_provider.send.assert_called_once()

    @patch('apps.messaging.dispatcher._get_provider')
    def test_invalid_recipient_blocked(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.format_recipient.return_value = 'not-a-phone'
        mock_provider.validate_recipient.return_value = False
        mock_get_provider.return_value = mock_provider

        result = self.dispatcher.send(
            channel='whatsapp',
            recipient='not-a-phone',
            content={'type': 'text', 'text': 'hi'},
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, 'INVALID_RECIPIENT')
        mock_provider.send.assert_not_called()

    @patch('apps.messaging.dispatcher._get_provider')
    def test_provider_exception_returns_failure(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.format_recipient.return_value = '+5511999999999'
        mock_provider.validate_recipient.return_value = True
        mock_provider.send.side_effect = RuntimeError('connection refused')
        mock_get_provider.return_value = mock_provider

        result = self.dispatcher.send(
            channel='whatsapp',
            recipient='+5511999999999',
            content={'type': 'text', 'text': 'hi'},
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, 'DISPATCH_ERROR')

    @patch('apps.messaging.dispatcher._get_provider')
    def test_send_bulk(self, mock_get_provider):
        mock_provider = MagicMock()
        mock_provider.format_recipient.side_effect = lambda r: r
        mock_provider.validate_recipient.return_value = True
        mock_provider.send.return_value = ProviderResult(success=True)
        mock_get_provider.return_value = mock_provider

        recipients = ['+5511111111111', '+5522222222222', '+5533333333333']
        results = self.dispatcher.send_bulk(
            channel='whatsapp',
            recipients=recipients,
            content={'type': 'text', 'text': 'Broadcast!'},
        )

        self.assertEqual(len(results), 3)
        for recipient in recipients:
            self.assertTrue(results[recipient].success)


class DispatchMessageDataclassTest(TestCase):
    def test_dispatch_message_defaults(self):
        msg = DispatchMessage(
            channel='email',
            recipient='user@example.com',
            content={'subject': 'Test', 'body': 'Hello'},
        )
        self.assertEqual(msg.source, '')
        self.assertEqual(msg.source_id, '')
        self.assertEqual(msg.metadata, {})
