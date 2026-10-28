"""Cancelar impressão (28/10): cancelada no Windows, o agent avisava "falhou",
o servidor punha de volta na fila e a comanda voltava em loop — mesmo depois de
reiniciar a impressora. O painel cancela, e cancelado não volta mais."""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.stores.models.printing import StorePrintAgent, StorePrintJob

User = get_user_model()


class CancelarImpressaoTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-imp', email='i@t.com', password='x')
        self.store = Store.objects.create(name='Loja Imp', slug='loja-imp', owner=self.owner, status='active')
        self.raw, prefix, hashed = StorePrintAgent.generate_api_key()
        self.agent = StorePrintAgent.objects.create(
            store=self.store, name='Balcão', slug='balcao', station='kitchen',
            api_key_prefix=prefix, api_key_hash=hashed,
        )
        self.client.force_authenticate(self.owner)

    def _job(self, **extra):
        return StorePrintJob.objects.create(store=self.store, station='kitchen', title='Comanda', payload={}, **extra)

    def _agente(self, caminho, dados=None):
        self.client.force_authenticate(None)
        resp = self.client.post(caminho, dados or {}, format='json', HTTP_X_PRINT_AGENT_KEY=self.raw)
        self.client.force_authenticate(self.owner)
        return resp

    def test_painel_cancela_um_trabalho_e_o_agent_nao_pega_mais(self):
        job = self._job()
        resp = self.client.post(f'/api/v1/stores/print-jobs/{job.id}/cancel/', {}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['status'], 'cancelled')
        resp = self._agente('/api/v1/stores/print/agent/claim-next/')
        self.assertIsNone(resp.data['job'])

    def test_falha_depois_de_cancelado_nao_volta_para_a_fila(self):
        job = self._job()
        job.claim(self.agent)
        self.client.post(f'/api/v1/stores/print-jobs/{job.id}/cancel/', {}, format='json')
        self._agente(f'/api/v1/stores/print/jobs/{job.id}/fail/', {'error': 'x', 'retryable': True})
        job.refresh_from_db()
        self.assertEqual(job.status, StorePrintJob.JobStatus.CANCELLED)

    def test_cancelado_no_windows_vira_cancelado_e_nao_repete(self):
        job = self._job()
        job.claim(self.agent)
        self._agente(f'/api/v1/stores/print/jobs/{job.id}/fail/', {
            'error': 'Print job 12 failed/stalled: status=Deleting, Error, document=Comanda',
            'retryable': True,
        })
        job.refresh_from_db()
        self.assertEqual(job.status, StorePrintJob.JobStatus.CANCELLED)

    def test_falha_comum_ainda_tenta_de_novo(self):
        job = self._job()
        job.claim(self.agent)
        self._agente(f'/api/v1/stores/print/jobs/{job.id}/fail/', {'error': 'Printer offline', 'retryable': True})
        job.refresh_from_db()
        self.assertEqual(job.status, StorePrintJob.JobStatus.PENDING)

    def test_limpar_fila_cancela_pendentes_e_em_impressao_e_poupa_o_resto(self):
        pendente = self._job()
        pegando = self._job()
        pegando.claim(self.agent)
        feito = self._job(status=StorePrintJob.JobStatus.COMPLETED)
        outra_loja = Store.objects.create(name='Outra', slug='outra-imp', owner=self.owner, status='active')
        alheio = StorePrintJob.objects.create(store=outra_loja, station='kitchen', payload={})

        resp = self.client.post('/api/v1/stores/print-jobs/cancelar-fila/', {'store': str(self.store.id)}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['canceladas'], 2)
        for job, esperado in [(pendente, 'cancelled'), (pegando, 'cancelled'), (feito, 'completed'), (alheio, 'pending')]:
            job.refresh_from_db()
            self.assertEqual(job.status, esperado)

    def test_nao_cancela_o_que_ja_imprimiu(self):
        job = self._job(status=StorePrintJob.JobStatus.COMPLETED)
        resp = self.client.post(f'/api/v1/stores/print-jobs/{job.id}/cancel/', {}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_quem_nao_e_da_loja_nao_cancela(self):
        estranho = User.objects.create_user(username='estranho-imp', email='e@t.com', password='x')
        job = self._job()
        self.client.force_authenticate(estranho)
        resp = self.client.post(f'/api/v1/stores/print-jobs/{job.id}/cancel/', {}, format='json')
        self.assertIn(resp.status_code, (403, 404))
        resp = self.client.post('/api/v1/stores/print-jobs/cancelar-fila/', {'store': str(self.store.id)}, format='json')
        self.assertIn(resp.status_code, (403, 404))
        job.refresh_from_db()
        self.assertEqual(job.status, StorePrintJob.JobStatus.PENDING)
