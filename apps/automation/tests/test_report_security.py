"""Regressão de segurança: IDOR cross-tenant na geração de relatórios.

`ReportScheduleViewSet.create` e `GeneratedReportViewSet.generate` aceitavam
account_id/company_id arbitrários sem checar ownership — qualquer autenticado
podia agendar/disparar um relatório sobre os dados de OUTRO tenant e enviá-lo
por email para destinatários que ele controla (exfiltração).
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class ReportTargetIDORTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='rp-owner', email='rp-o@t.com', password='x')
        self.attacker = User.objects.create_user(username='rp-att', email='rp-a@t.com', password='x')
        self.victim_account = WhatsAppAccount.objects.create(
            name='victim-acc', phone_number_id='pn-v', waba_id='wa-v',
            phone_number='+5511222221', display_phone_number='+5511222221',
            access_token_encrypted='x', webhook_verify_token='x',
            owner=self.owner,
        )

    def test_attacker_cannot_schedule_report_on_victim_account(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(
            '/api/v1/automation/report-schedules/',
            {'name': 'leak', 'account_id': str(self.victim_account.id),
             'recipients': ['attacker@evil.com']},
            format='json',
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_attacker_cannot_generate_report_on_victim_account(self):
        self.client.force_authenticate(self.attacker)
        resp = self.client.post(
            '/api/v1/automation/reports/generate/',
            {'account_id': str(self.victim_account.id),
             'recipients': ['attacker@evil.com']},
            format='json',
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_owner_can_generate_report_on_own_account(self):
        self.client.force_authenticate(self.owner)
        with patch('apps.automation.tasks.generate_report.delay') as mock_delay:
            mock_delay.return_value = type('T', (), {'id': 'task-123'})()
            resp = self.client.post(
                '/api/v1/automation/reports/generate/',
                {'account_id': str(self.victim_account.id)},
                format='json',
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        mock_delay.assert_called_once()
