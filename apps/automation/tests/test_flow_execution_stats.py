"""AgentFlow.total_executions/success_rate eram sempre 0 (campos nunca populados).
refresh_execution_stats recalcula de FlowSession (nº de execuções) e FlowExecutionLog
(% de nós executados com sucesso). Painel de Automação mostrava 0% fixo.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.conversations.models import Conversation
from apps.automation.models import AgentFlow, FlowSession, FlowExecutionLog

User = get_user_model()


class FlowExecutionStatsTest(APITestCase):
    def setUp(self):
        from apps.whatsapp.models.account import WhatsAppAccount
        self.owner = User.objects.create_user(username='ow-flow', email='ow-flow@t.com', password='x')
        self.store = Store.objects.create(name='Loja Flow', slug='loja-flow', owner=self.owner, status='active')
        self.flow = AgentFlow.objects.create(store=self.store, name='Atendimento', flow_json={'nodes': [], 'edges': []})
        self.account = WhatsAppAccount.objects.create(
            name='Conta', phone_number_id='PN', waba_id='WA',
            phone_number='5563999999999', access_token_encrypted='x', owner=self.owner,
        )
        self._seq = 0

    def _session(self):
        self._seq += 1
        conv = Conversation.objects.create(account=self.account, phone_number=f'556399900011{self._seq}')
        return FlowSession.objects.create(conversation=conv, flow=self.flow)

    def test_stats_start_at_zero(self):
        self.assertEqual(self.flow.total_executions, 0)
        self.assertEqual(self.flow.success_rate, 0.0)

    def test_refresh_computes_executions_and_success_rate(self):
        s1 = self._session()
        s2 = self._session()
        # 3 nós ok, 1 falho → 75%
        for ok in (True, True, True, False):
            FlowExecutionLog.objects.create(
                session=s1, flow=self.flow, node_id='n', node_type='message', success=ok,
            )
        FlowExecutionLog.objects.create(session=s2, flow=self.flow, node_id='n', node_type='message', success=True)
        # agora: 5 logs, 4 sucesso → 80%; 2 sessões
        self.flow.refresh_execution_stats()
        self.flow.refresh_from_db()
        self.assertEqual(self.flow.total_executions, 2)
        self.assertEqual(self.flow.success_rate, 80.0)

    def test_refresh_no_logs_keeps_zero(self):
        self._session()
        self.flow.refresh_execution_stats()
        self.flow.refresh_from_db()
        self.assertEqual(self.flow.total_executions, 1)
        self.assertEqual(self.flow.success_rate, 0.0)
