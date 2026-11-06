"""Lista de trabalhos de impressão: custo de queries constante (target_agent no select_related)."""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.stores.models.printing import StorePrintAgent, StorePrintJob

User = get_user_model()


class ListaPrintJobsQueriesTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-nm1', email='nm1@t.com', password='x')
        self.store = Store.objects.create(name='Loja NM1', slug='loja-nm1', owner=self.owner, status='active')
        self.client.force_authenticate(self.owner)

    def _agente(self, i):
        _raw, prefix, hashed = StorePrintAgent.generate_api_key()
        return StorePrintAgent.objects.create(
            store=self.store, name=f'Agent {i}', slug=f'agent-{i}', station='kitchen',
            api_key_prefix=prefix, api_key_hash=hashed,
        )

    def _criar_jobs(self, n):
        for i in range(n):
            ag = self._agente(f'{StorePrintJob.objects.count()}-{i}')
            StorePrintJob.objects.create(
                store=self.store, station='kitchen', title='Comanda', payload={},
                target_agent=ag, claimed_by=ag,
            )

    def _queries(self):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get('/api/v1/stores/print-jobs/')
        self.assertEqual(resp.status_code, 200, resp.content)
        return len(ctx), resp

    def test_queries_nao_crescem_com_o_numero_de_jobs(self):
        self._criar_jobs(2)
        self.client.get('/api/v1/stores/print-jobs/')  # aquecimento (caches de 1ª chamada)
        pequeno, _ = self._queries()
        self._criar_jobs(6)
        grande, resp = self._queries()
        self.assertEqual(pequeno, grande)
        results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        self.assertTrue(all(r['target_agent_name'] for r in results))
