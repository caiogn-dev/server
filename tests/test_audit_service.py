"""
Unit tests for AuditService.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.audit.models import AuditLog
from apps.audit.services import AuditService

User = get_user_model()


class AuditServiceLogTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='auditor', email='audit@example.com', password='pass'
        )
        self.service = AuditService()

    def test_log_action_creates_record(self):
        self.service.log_action(
            action='create',
            module='stores',
            user=self.user,
            description='Created store',
        )
        self.assertEqual(AuditLog.objects.filter(user=self.user).count(), 1)

    def test_log_action_stores_correct_fields(self):
        self.service.log_action(
            action='update',
            module='products',
            user=self.user,
            description='Updated price',
        )
        log = AuditLog.objects.get(user=self.user)
        self.assertEqual(log.action, 'update')
        self.assertEqual(log.module, 'products')
        self.assertEqual(log.user_email, self.user.email)

    def test_get_user_activity_scoped(self):
        other_user = User.objects.create_user(
            username='other', email='other@test.com', password='pass'
        )
        self.service.log_action(
            action='login', module='auth', user=self.user, description='Login'
        )
        self.service.log_action(
            action='login', module='auth', user=other_user, description='Login'
        )

        logs = self.service.get_user_activity(self.user, days=30, limit=100)
        users_in_logs = {log.user_id for log in logs}
        self.assertIn(self.user.pk, users_in_logs)
        self.assertNotIn(other_user.pk, users_in_logs)

    def test_get_logs_by_user(self):
        self.service.log_action(
            action='create', module='orders', user=self.user, description='Order created'
        )
        self.service.log_action(
            action='update', module='orders', user=self.user, description='Order updated'
        )

        logs = self.service.get_logs(user=self.user, limit=10)
        self.assertEqual(len(list(logs)), 2)

    def test_log_without_user_sets_empty_email(self):
        self.service.log_action(
            action='cleanup',
            module='system',
            description='Automated cleanup',
        )
        log = AuditLog.objects.filter(action='cleanup').first()
        self.assertIsNotNone(log)
        self.assertIsNone(log.user)
        self.assertEqual(log.user_email, '')

    def test_log_with_request_info(self):
        self.service.log_action(
            action='view',
            module='reports',
            user=self.user,
            description='Viewed export',
            request_info={
                'ip': '127.0.0.1',
                'user_agent': 'Mozilla/5.0',
                'path': '/api/v1/audit/exports/',
                'method': 'GET',
            }
        )
        log = AuditLog.objects.get(action='view', user=self.user)
        self.assertEqual(log.user_ip, '127.0.0.1')
        self.assertEqual(log.request_method, 'GET')
