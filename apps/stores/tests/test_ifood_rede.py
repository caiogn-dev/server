"""Rede no iFood: várias marcas (mesmo CNPJ, mesma cozinha) caindo no painel de UMA loja.

Medido 26/11: a rede da Agrião tem 7 marcas no iFood (Santa Parmê, Pasta 2 Go,
Leve Com Sabor...). O dono quer um canal só — não criar 7 lojas no Cardapidex.
"""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.stores.models import Store
from apps.stores.models.ifood import StoreIfoodIntegration
from apps.stores.services import pedidos_do_ifood as pif
from apps.stores.services import webhook_ifood
from apps.stores.tests.test_pedidos_do_ifood import CREDENCIAIS, _pedido

User = get_user_model()
PRINCIPAL = 'merchant-agriao'
MARCA = 'merchant-parme'


@override_settings(**CREDENCIAIS)
class RedeNoMesmoPainelTest(TestCase):
    def setUp(self):
        cache.clear()
        dono = User.objects.create_user(username='dono-rede', password='x')
        self.store = Store.objects.create(billing_exempt=True, name='Agrião', slug='agriao-rede', owner=dono,
                                          store_type='food', status='active')
        StoreIfoodIntegration.objects.create(
            store=self.store, conectado=True, merchant_id=PRINCIPAL, merchant_name='Agrião Comida Saudável',
            merchants_da_rede=[{'id': MARCA, 'nome': 'Santa Parmê'}],
            access_token='tok', refresh_token='ref', token_expires_at=timezone.now() + timedelta(hours=5),
        )
        self.chamadas = []

    def _chamar(self, respostas):
        def falso(store, metodo, caminho, corpo=None, cabecalhos=None):
            self.chamadas.append((metodo, caminho, corpo, cabecalhos))
            return respostas.get((metodo, caminho))
        return mock.patch.object(pif, '_chamar', side_effect=falso)

    def test_polling_pede_as_marcas_e_o_evento_cai_na_loja(self):
        eventos = [{'id': 'e1', 'code': 'CON', 'orderId': 'x1', 'merchantId': MARCA}]
        with self._chamar({('GET', '/events/v1.0/events:polling'): eventos}), \
                mock.patch.object(pif, 'aplicar_evento', return_value=False) as aplicar:
            pif.processar_eventos([self.store])
        polling = [c for c in self.chamadas if c[1] == '/events/v1.0/events:polling'][0]
        self.assertEqual(set(polling[3]['x-polling-merchants'].split(',')), {PRINCIPAL, MARCA})
        self.assertEqual(aplicar.call_args.args[0], self.store)

    def test_webhook_de_marca_da_rede_aplica_na_loja(self):
        evento = {'code': 'PLC', 'id': 'e2', 'merchantId': MARCA, 'orderId': 'o2'}
        with mock.patch.object(pif, 'aplicar_evento', return_value=True) as aplicar:
            webhook_ifood.processar('pedidos', evento)
        self.assertEqual(aplicar.call_args.args[0], self.store)

    def test_keepalive_deixa_as_marcas_online(self):
        online = webhook_ifood.presenca('pedidos', {'merchantIds': [MARCA, 'outra']})
        self.assertEqual(online, [MARCA])

    def test_pedido_guarda_de_qual_marca_veio(self):
        with mock.patch.object(pif, 'imprimir_depois'), mock.patch.object(pif, 'confirmar_depois'):
            pedido, _ = pif.receber_pedido_novo(
                self.store, _pedido(merchant={'id': MARCA, 'name': 'Santa Parmê - Parmegianas'}))
        self.assertEqual(pedido.metadata['ifood']['marca'], 'Santa Parmê')


class WidgetPorLojaTest(TestCase):
    def test_com_store_vai_so_a_loja_e_as_marcas_da_rede(self):
        from rest_framework.test import APIClient
        dono = User.objects.create_user(username='dono-widget-rede', password='x')
        for slug, principal, rede in (('ce-w2', 'm-ce', []), ('agriao-w2', 'm-agriao', [{'id': 'm-parme', 'nome': 'Parmê'}])):
            loja = Store.objects.create(billing_exempt=True, name=slug, slug=slug, owner=dono,
                                        store_type='food', status='active')
            StoreIfoodIntegration.objects.create(store=loja, merchant_id=principal, conectado=True,
                                                 merchants_da_rede=rede)
        cliente = APIClient()
        cliente.force_authenticate(dono)
        with mock.patch('apps.stores.services.ifood_oauth.merchants_autorizados', return_value=None):
            r = cliente.get('/api/v1/stores/integracoes/ifood/merchants/', {'store': 'agriao-w2'})
            todas = cliente.get('/api/v1/stores/integracoes/ifood/merchants/')
        self.assertEqual(r.data['merchant_ids'], ['m-agriao', 'm-parme'])
        self.assertEqual(sorted(todas.data['merchant_ids']), ['m-agriao', 'm-ce', 'm-parme'])


class PollingSoComLojasAutorizadasTest(TestCase):
    def test_fora_da_homologacao_tira_a_loja_que_o_app_nao_tem(self):
        from apps.stores.services import ifood_oauth
        with mock.patch.object(ifood_oauth, 'em_homologacao', return_value=False), \
                mock.patch.object(ifood_oauth, 'merchants_autorizados', return_value={'m-ok'}):
            self.assertEqual(ifood_oauth.merchants_do_app('pedidos', ['M-OK', 'm-teste']), ['M-OK'])

    def test_sem_saber_as_autorizadas_manda_todas(self):
        from apps.stores.services import ifood_oauth
        with mock.patch.object(ifood_oauth, 'em_homologacao', return_value=False), \
                mock.patch.object(ifood_oauth, 'merchants_autorizados', return_value=None):
            self.assertEqual(ifood_oauth.merchants_do_app('pedidos', ['a', 'b']), ['a', 'b'])
