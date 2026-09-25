"""Cada agent diz o que imprime: comanda, recibo, etiquetas.

Antes, todo agent ativo da loja recebia comanda — a Zebra de etiqueta do pc
desktop da Cê Saladas acumulou 230 comandas falhadas. Agora a comanda só vai
para quem imprime comanda; a etiqueta só sai por quem imprime etiquetas.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StorePrintAgent, StorePrintJob
from apps.stores.services.print_service import enqueue_order_print_job

User = get_user_model()

VALIDADE = [{'name': 'Salada', 'manip': '25/09/2026', 'val': '30/09/2026'}]


def _agent(store, name, imprime=None, station='kitchen'):
    _, p, h = StorePrintAgent.generate_api_key()
    extra = {} if imprime is None else {'imprime': imprime}
    return StorePrintAgent.objects.create(
        store=store, name=name, slug=name.replace(' ', '-'), station=station,
        api_key_prefix=p, api_key_hash=h, **extra)


class Base(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-imp', email='dono-imp@t.local', password='x')
        self.store = Store.objects.create(name='Loja I', slug='loja-i', owner=self.owner, status='active')
        self.client.force_authenticate(self.owner)


class EnfileiramentoTests(Base):
    def _pedido(self):
        return StoreOrder.objects.create(store=self.store, order_number='CE-1', total=10, subtotal=10)

    def test_padrao_do_agent_e_comanda_e_recibo(self):
        a = _agent(self.store, 'caixa')
        self.assertEqual(sorted(a.imprime), ['comanda', 'recibo'])

    def test_comanda_nao_vai_para_agent_so_de_etiquetas(self):
        epson = _agent(self.store, 'epson', ['comanda'])
        zebra = _agent(self.store, 'zebra', ['etiquetas'])
        enqueue_order_print_job(self._pedido())
        alvos = set(StorePrintJob.objects.values_list('target_agent_id', flat=True))
        self.assertEqual(alvos, {epson.id})
        self.assertNotIn(zebra.id, alvos)

    def test_recibo_so_para_quem_imprime_recibo(self):
        cozinha = _agent(self.store, 'cozinha', ['comanda'], station='balcao')
        balcao = _agent(self.store, 'balcao', ['recibo'], station='balcao')
        enqueue_order_print_job(self._pedido(), station='balcao',
                                template=StorePrintJob.Template.CUSTOMER_RECEIPT)
        alvos = set(StorePrintJob.objects.values_list('target_agent_id', flat=True))
        self.assertEqual(alvos, {balcao.id})
        self.assertNotIn(cozinha.id, alvos)

    def test_loja_sem_agent_de_comanda_nao_cria_job_orfao_para_a_zebra(self):
        _agent(self.store, 'zebra', ['etiquetas'])
        enqueue_order_print_job(self._pedido())
        # sem agent de comanda o comportamento antigo vale: job sem alvo
        # (qualquer agent futuro da estação pega), mas NUNCA apontado à Zebra
        self.assertEqual(StorePrintJob.objects.filter(target_agent__isnull=False).count(), 0)


class EtiquetaTests(Base):
    URL = '/api/v1/stores/print-jobs/etiquetas/'

    def _post(self, agent):
        return self.client.post(self.URL, {
            'store': str(self.store.id), 'agent': str(agent.id), 'modelo': 'validade',
            'etiquetas': VALIDADE, 'config': {'cols': 1, 'labelW': 33, 'labelH': 22},
        }, format='json')

    def test_agent_que_nao_imprime_etiquetas_e_recusado(self):
        epson = _agent(self.store, 'epson', ['comanda'])
        r = self._post(epson)
        self.assertEqual(r.status_code, 400)
        self.assertIn('etiquetas', r.data['detail'])

    def test_agent_de_etiquetas_aceita(self):
        zebra = _agent(self.store, 'zebra', ['etiquetas'])
        self.assertEqual(self._post(zebra).status_code, 201)


class ApiDoPainelTests(Base):
    def test_painel_le_e_grava_o_que_o_agent_imprime(self):
        a = _agent(self.store, 'pc desktop')
        r = self.client.get(f'/api/v1/stores/print-agents/{a.id}/')
        self.assertEqual(sorted(r.data['imprime']), ['comanda', 'recibo'])
        r = self.client.patch(f'/api/v1/stores/print-agents/{a.id}/', {'imprime': ['etiquetas']}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        a.refresh_from_db()
        self.assertEqual(a.imprime, ['etiquetas'])

    def test_valor_desconhecido_e_400(self):
        a = _agent(self.store, 'pc desktop')
        r = self.client.patch(f'/api/v1/stores/print-agents/{a.id}/', {'imprime': ['fax']}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_criar_agent_ja_com_o_papel(self):
        r = self.client.post('/api/v1/stores/print-agents/', {
            'store': str(self.store.id), 'name': 'Zebra', 'slug': 'zebra-nova', 'imprime': ['etiquetas'],
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(StorePrintAgent.objects.get(slug='zebra-nova').imprime, ['etiquetas'])
