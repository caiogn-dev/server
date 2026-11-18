"""GET /marketing/automations/{id}/logs/ não faz query por log."""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient, APITestCase

from apps.marketing.models import EmailAutomation, EmailAutomationLog
from apps.stores.models import Store

User = get_user_model()


class LogsDaAutomacaoQueryCountTests(APITestCase):
    def setUp(self):
        self.dono = User.objects.create_user('dono', 'd@x.com', 'pw')
        self.loja = Store.objects.create(name='A', slug='loja-a', owner=self.dono)
        self.auto = EmailAutomation.objects.create(
            store=self.loja, name='Boas-vindas', trigger_type='welcome',
            subject='s', html_content='<p>x</p>')
        self.client = APIClient()
        self.client.force_authenticate(self.dono)

    def _logs(self, n):
        EmailAutomationLog.objects.bulk_create([
            EmailAutomationLog(automation=self.auto, recipient_email=f'u{i}@x.com')
            for i in range(n)
        ])

    def _queries(self):
        url = f'/api/v1/marketing/automations/{self.auto.id}/logs/'
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(url)
        self.assertEqual(r.status_code, 200, r.content)
        return len(ctx), r.json()

    def test_queries_nao_crescem_com_o_numero_de_logs(self):
        self._logs(2)
        q2, _ = self._queries()
        self._logs(6)
        q8, dados = self._queries()
        self.assertEqual(len(dados), 8)
        self.assertEqual(dados[0]['automation_name'], 'Boas-vindas')
        self.assertEqual(dados[0]['trigger_type'], 'welcome')
        self.assertEqual(q2, q8)
