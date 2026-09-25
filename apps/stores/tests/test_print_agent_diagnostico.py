"""Diagnóstico do print agent: 401 diz qual chave chegou; job travado em `claimed` volta à fila.

25/set: o notebook da Cê Saladas ficou 10 min mandando uma chave recusada e o backend só
dizia "Unauthorized". E um job que o agent pegou e nunca fechou (processo morto no meio)
ficava `claimed` para sempre, invisível para qualquer outro agent.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store, StorePrintAgent, StorePrintJob
from apps.stores.services.print_service import claim_next_print_job

User = get_user_model()


class Base(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-diag', email='owner-diag@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Diag', slug='loja-diag', owner=self.owner, status='active',
        )
        raw, prefix, hashed = StorePrintAgent.generate_api_key()
        self.raw_key = raw
        self.agent = StorePrintAgent.objects.create(
            store=self.store, name='Caixa', slug='caixa-diag',
            api_key_prefix=prefix, api_key_hash=hashed,
        )

    def _claim(self, key):
        return self.client.post(
            '/api/v1/stores/print/agent/claim-next/', {}, format='json',
            HTTP_X_PRINT_AGENT_KEY=key,
        )


class Log401Tests(Base):
    def test_prefixo_desconhecido_vai_para_o_log(self):
        with self.assertLogs('apps.stores.api.views.print_views', level='WARNING') as cm:
            resp = self._claim('pa_000000000000.segredo')
        self.assertEqual(resp.status_code, 401)
        self.assertIn('pa_000000000000', cm.output[0])
        self.assertIn('prefixo_desconhecido', cm.output[0])

    def test_segredo_errado_vai_para_o_log(self):
        with self.assertLogs('apps.stores.api.views.print_views', level='WARNING') as cm:
            resp = self._claim(f'{self.agent.api_key_prefix}.segredo-errado')
        self.assertEqual(resp.status_code, 401)
        self.assertIn(self.agent.api_key_prefix, cm.output[0])
        self.assertIn('segredo_errado', cm.output[0])

    def test_agente_inativo_vai_para_o_log(self):
        self.agent.status = StorePrintAgent.AgentStatus.DISABLED
        self.agent.save(update_fields=['status'])
        with self.assertLogs('apps.stores.api.views.print_views', level='WARNING') as cm:
            resp = self._claim(self.raw_key)
        self.assertEqual(resp.status_code, 401)
        self.assertIn('agente_inativo', cm.output[0])

    def test_chave_sem_ponto_vai_para_o_log(self):
        with self.assertLogs('apps.stores.api.views.print_views', level='WARNING') as cm:
            resp = self._claim('pa_semponto')
        self.assertEqual(resp.status_code, 401)
        self.assertIn('formato_invalido', cm.output[0])

    def test_segredo_nunca_vai_para_o_log(self):
        with self.assertLogs('apps.stores.api.views.print_views', level='WARNING') as cm:
            self._claim(f'{self.agent.api_key_prefix}.SEGREDO-SECRETO')
        self.assertNotIn('SEGREDO-SECRETO', cm.output[0])


class ClaimTravadoTests(Base):
    def _job(self, **kw):
        return StorePrintJob.objects.create(store=self.store, title='t', **kw)

    def test_job_claimed_ha_mais_de_5_min_volta_para_a_fila(self):
        travado = self._job(
            status=StorePrintJob.JobStatus.CLAIMED, claimed_by=self.agent,
            claimed_at=timezone.now() - timedelta(minutes=6), attempts=1,
        )
        job = claim_next_print_job(self.agent)
        self.assertEqual(job.id, travado.id)
        self.assertEqual(job.status, StorePrintJob.JobStatus.CLAIMED)
        self.assertEqual(job.attempts, 2)
        self.assertIn('claimed', job.last_error)

    def test_job_claimed_recente_nao_e_roubado(self):
        self._job(
            status=StorePrintJob.JobStatus.CLAIMED, claimed_by=self.agent,
            claimed_at=timezone.now() - timedelta(minutes=1), attempts=1,
        )
        self.assertIsNone(claim_next_print_job(self.agent))

    def test_job_travado_que_esgotou_tentativas_vira_failed(self):
        travado = self._job(
            status=StorePrintJob.JobStatus.CLAIMED, claimed_by=self.agent,
            claimed_at=timezone.now() - timedelta(minutes=6), attempts=3, max_attempts=3,
        )
        self.assertIsNone(claim_next_print_job(self.agent))
        travado.refresh_from_db()
        self.assertEqual(travado.status, StorePrintJob.JobStatus.FAILED)
