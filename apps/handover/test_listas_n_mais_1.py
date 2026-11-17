"""GET /handover/requests/ e /handover/logs/ serializam usuários aninhados
(requested_by, approved_by, assigned_to, performed_by) sem select_related:
2-3 queries extras por linha. O número de queries tem de ser constante."""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.conversations.models import Conversation
from apps.handover.models import HandoverLog, HandoverRequest
from apps.whatsapp.models.account import WhatsAppAccount

User = get_user_model()


class HandoverListasSemN1Test(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='ow-ho', email='ow-ho@t.com', password='x')
        self.account = WhatsAppAccount.objects.create(
            name='Conta', phone_number_id='PNHO', waba_id='WAHO',
            phone_number='5563999999997', access_token_encrypted='x', owner=self.owner,
        )
        self.client.force_authenticate(self.owner)
        self.n = 0

    def _linhas(self, k):
        for _ in range(k):
            self.n += 1
            u = User.objects.create_user(username=f'u-ho-{self.n}', email=f'u{self.n}@t.com', password='x')
            conv = Conversation.objects.create(account=self.account, phone_number=f'5563988{self.n:06d}')
            HandoverRequest.objects.create(
                conversation=conv, requested_by=u, approved_by=u, assigned_to=u,
            )
            HandoverLog.objects.create(
                conversation=conv, from_status='bot', to_status='human',
                performed_by=u, assigned_to=u,
            )

    def _consulta(self, url):
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(url)
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        return len(ctx), body.get('results', body)

    def _confere(self, url):
        self._linhas(2)
        q2, _ = self._consulta(url)
        self._linhas(6)
        q8, itens = self._consulta(url)
        self.assertEqual(len(itens), 8)
        self.assertEqual(q2, q8)
        return itens

    def test_lista_de_solicitacoes_sem_n_mais_1(self):
        itens = self._confere('/api/v1/handover/requests/')
        self.assertTrue(all(i['assigned_to']['username'] for i in itens))

    def test_lista_de_logs_sem_n_mais_1(self):
        itens = self._confere('/api/v1/handover/logs/')
        self.assertTrue(all(i['performed_by']['username'] for i in itens))
