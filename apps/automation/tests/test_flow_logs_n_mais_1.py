"""GET /flow-logs/ lia session.conversation.phone_number sem select_related:
1 query extra por log. O número de queries tem de ser constante."""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.automation.models import AgentFlow, FlowExecutionLog, FlowSession
from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.models.account import WhatsAppAccount

User = get_user_model()


class FlowLogsListaSemN1Test(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='ow-fl', email='ow-fl@t.com', password='x')
        self.store = Store.objects.create(name='Loja FL', slug='loja-fl', owner=self.owner, status='active')
        self.flow = AgentFlow.objects.create(store=self.store, name='F', flow_json={'nodes': [], 'edges': []})
        self.account = WhatsAppAccount.objects.create(
            name='Conta', phone_number_id='PNFL', waba_id='WAFL',
            phone_number='5563999999998', access_token_encrypted='x', owner=self.owner,
        )
        self.client.force_authenticate(self.owner)

    def _logs(self, n):
        base = FlowExecutionLog.objects.count()
        for i in range(n):
            conv = Conversation.objects.create(account=self.account, phone_number=f'55639990{base + i:05d}')
            s = FlowSession.objects.create(conversation=conv, flow=self.flow)
            FlowExecutionLog.objects.create(session=s, flow=self.flow, node_id='n', node_type='message')

    def _consulta(self):
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get('/api/v1/automation/flow-logs/')
        self.assertEqual(r.status_code, 200, r.content)
        return len(ctx), r.json()

    def test_queries_nao_crescem_com_o_numero_de_logs(self):
        self._logs(2)
        q2, body = self._consulta()
        self._logs(6)
        q8, body8 = self._consulta()
        itens = body8.get('results', body8)
        self.assertEqual(len(itens), 8)
        self.assertTrue(all(i['phone_number'] for i in itens))
        self.assertEqual(q2, q8)
