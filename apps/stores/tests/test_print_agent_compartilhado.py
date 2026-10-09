"""
Impressora de uma loja atendendo outra (09/10): a Zebra e a Elgin ficam no PC da
Cê Saladas, e a Agrião, que divide a cozinha, imprime as etiquetas nelas.

O agent continua da loja dele; `metadata.lojas_compartilhadas` lista as lojas
extras que podem mandar etiqueta para ele. Sem estar na lista, nada muda.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StorePrintAgent, StorePrintJob
from apps.stores.services.print_service import claim_next_print_job

User = get_user_model()
URL = '/api/v1/stores/print-jobs/etiquetas/'
VALIDADE = [{'name': 'Salada', 'manip': '09/10/2026', 'val': '12/10/2026'}]
CFG = {'cols': 3, 'labelW': 33, 'labelH': 22, 'gap': 2, 'paperW': 105, 'offsetX': 0, 'offsetY': 0}


class AgentCompartilhadoTest(APITestCase):
    def setUp(self):
        self.dona_ce = User.objects.create_user(username='ce', email='ce@t.local', password='x')
        self.dona_ag = User.objects.create_user(username='ag', email='ag@t.local', password='x')
        self.ce = Store.objects.create(name='Cê', slug='ce-t', owner=self.dona_ce, status='active')
        self.agriao = Store.objects.create(name='Agrião', slug='agriao-t', owner=self.dona_ag, status='active')
        _, p, h = StorePrintAgent.generate_api_key()
        self.zebra = StorePrintAgent.objects.create(
            store=self.ce, name='pc desktop', slug='pc-ce', station='kitchen', imprime=['etiquetas'],
            printer_name='ZDesigner', api_key_prefix=p, api_key_hash=h)
        self.client.force_authenticate(self.dona_ag)

    def _compartilhar(self):
        self.zebra.metadata = {'lojas_compartilhadas': [str(self.agriao.id)]}
        self.zebra.save(update_fields=['metadata'])

    def _post(self):
        return self.client.post(URL, {'store': str(self.agriao.id), 'agent': str(self.zebra.id),
                                      'modelo': 'validade', 'etiquetas': VALIDADE, 'config': CFG}, format='json')

    def _lista(self):
        r = self.client.get('/api/v1/stores/print-agents/', {'store': self.agriao.slug})
        self.assertEqual(r.status_code, 200, r.content)
        dados = r.data.get('results', r.data)
        return [a['id'] for a in dados]

    def test_sem_compartilhar_a_agriao_nao_ve_nem_usa(self):
        self.assertNotIn(str(self.zebra.id), self._lista())
        self.assertEqual(self._post().status_code, 400)

    def test_compartilhada_aparece_na_lista_da_agriao(self):
        self._compartilhar()
        self.assertIn(str(self.zebra.id), self._lista())

    def test_etiqueta_da_agriao_vai_para_a_zebra_da_ce_e_o_agent_pega(self):
        self._compartilhar()
        r = self._post()
        self.assertEqual(r.status_code, 201, r.content)
        job = StorePrintJob.objects.get(id=r.data['job']['id'])
        self.assertEqual(job.store_id, self.agriao.id)
        self.assertEqual(job.target_agent_id, self.zebra.id)
        self.assertEqual(claim_next_print_job(self.zebra).id, job.id)

    def test_agent_nao_pega_job_da_outra_loja_sem_ser_o_alvo(self):
        self._compartilhar()
        StorePrintJob.objects.create(store=self.agriao, station='kitchen', payload={}, template='kitchen_ticket')
        self.assertIsNone(claim_next_print_job(self.zebra))

    def test_loja_compartilhada_nao_troca_chave_nem_edita_o_agent(self):
        self._compartilhar()
        base = f'/api/v1/stores/print-agents/{self.zebra.id}/'
        self.assertIn(self.client.post(base + 'rotate-key/').status_code, (403, 404))
        self.assertIn(self.client.patch(base, {'name': 'roubado'}, format='json').status_code, (403, 404))
        self.zebra.refresh_from_db()
        self.assertEqual(self.zebra.name, 'pc desktop')
