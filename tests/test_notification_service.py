"""
Unit tests for NotificationService.
"""
from unittest.mock import patch, MagicMock, PropertyMock
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.notifications.models import Notification, PushSubscription
from apps.notifications.services.notification_service import NotificationService

User = get_user_model()


class NotificationServiceCreateTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', email='test@example.com', password='pass'
        )
        self.service = NotificationService()

    @patch('apps.notifications.services.notification_service.get_channel_layer', return_value=None)
    def test_create_notification_persists(self, _mock_layer):
        notif = self.service.create_notification(
            title='Test',
            message='Hello',
            user=self.user,
            send_push=False,
            send_realtime=False,
        )
        self.assertIsNotNone(notif.pk)
        self.assertEqual(notif.title, 'Test')
        self.assertEqual(notif.user, self.user)
        self.assertFalse(notif.is_read)

    @patch('apps.notifications.services.notification_service.get_channel_layer', return_value=None)
    def test_create_notification_default_type_is_system(self, _mock_layer):
        notif = self.service.create_notification(
            title='T', message='M', send_push=False, send_realtime=False
        )
        self.assertEqual(notif.notification_type, Notification.NotificationType.SYSTEM)

    @patch('apps.notifications.services.notification_service.get_channel_layer', return_value=None)
    def test_mark_as_read(self, _mock_layer):
        notif = self.service.create_notification(
            title='T', message='M', user=self.user, send_push=False, send_realtime=False
        )
        self.service.mark_as_read(notif.pk, self.user)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    @patch('apps.notifications.services.notification_service.get_channel_layer', return_value=None)
    def test_get_unread_count(self, _mock_layer):
        self.service.create_notification(
            title='A', message='M', user=self.user, send_push=False, send_realtime=False
        )
        self.service.create_notification(
            title='B', message='M', user=self.user, send_push=False, send_realtime=False
        )
        count = self.service.get_unread_count(self.user)
        self.assertEqual(count, 2)


class PushSubscriptionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='pushuser', email='push@example.com', password='pass'
        )

    def test_subscription_created_and_retrieved(self):
        sub = PushSubscription.objects.create(
            user=self.user,
            endpoint='https://fcm.googleapis.com/push/abc',
            p256dh='key123',
            auth='auth456',
        )
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 1)
        self.assertEqual(sub.endpoint, 'https://fcm.googleapis.com/push/abc')

    def test_duplicate_endpoint_updates(self):
        PushSubscription.objects.create(
            user=self.user,
            endpoint='https://fcm.googleapis.com/push/abc',
            p256dh='key1',
            auth='auth1',
        )
        PushSubscription.objects.update_or_create(
            user=self.user,
            endpoint='https://fcm.googleapis.com/push/abc',
            defaults={'p256dh': 'key2', 'auth': 'auth2'},
        )
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 1)
