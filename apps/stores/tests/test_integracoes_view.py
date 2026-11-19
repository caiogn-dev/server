"""A aba Integrações do painel: o estado de cada canal de venda da loja.

    GET /api/v1/stores/integracoes/?store=<id|slug>

Um endpoint só, para a tela não fazer quatro chamadas e mostrar "não
conectado" no canal cuja chamada caiu.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StorePaymentGateway
from apps.stores.models.ifood import StoreIfoodIntegration

User = get_user_model()
URL = '/api/v1/stores/integracoes/'


class IntegracoesTests(APITestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dono-integracoes', password='x')
        self.loja = Store.objects.create(name='Cê', slug='ce-integra', owner=self.dono, status='active')
        self.client.force_authenticate(self.dono)

    def _pedido(self, source='', dias_atras=0):
        pedido = StoreOrder.objects.create(
            store=self.loja, customer_name='A', customer_phone='1', subtotal=Decimal('40'),
            total=Decimal('40'), status='confirmed', source=source,
        )
        if dias_atras:
            StoreOrder.objects.filter(pk=pedido.pk).update(
                created_at=timezone.now() - timedelta(days=dias_atras),
            )
        return pedido

    def _get(self, store=None):
        return self.client.get(URL, {'store': store or self.loja.slug})

    def test_loja_sem_nada_conectado(self):
        resp = self._get()

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['99food'], {'ativo': False, 'ultimo_pedido_em': None, 'pedidos_30_dias': 0})
        self.assertFalse(resp.data['ifood']['conectado'])
        self.assertFalse(resp.data['mercado_pago']['conectado'])

    def test_99_ativo_conta_so_pedidos_da_99_dos_ultimos_30_dias(self):
        self._pedido('99food')
        self._pedido('99food', dias_atras=40)
        self._pedido('')  # pedido do site não conta

        dados = self._get().data['99food']

        self.assertTrue(dados['ativo'])
        self.assertEqual(dados['pedidos_30_dias'], 1)
        self.assertIsNotNone(dados['ultimo_pedido_em'])

    def test_ifood_conectado_mostra_o_nome_da_loja_no_ifood(self):
        StoreIfoodIntegration.objects.create(store=self.loja, conectado=True, merchant_name='Cê Saladas Palmas')

        dados = self._get().data['ifood']

        self.assertTrue(dados['conectado'])
        self.assertEqual(dados['loja'], 'Cê Saladas Palmas')

    @override_settings(IFOOD_CLIENT_ID='', IFOOD_CLIENT_SECRET='')
    def test_ifood_indisponivel_sem_app_da_plataforma(self):
        self.assertFalse(self._get().data['ifood']['disponivel'])

    @override_settings(IFOOD_CLIENT_ID='id', IFOOD_CLIENT_SECRET='seg')
    def test_ifood_disponivel_com_app_da_plataforma(self):
        self.assertTrue(self._get().data['ifood']['disponivel'])

    def test_mercado_pago_conectado_exige_gateway_ligado_com_credencial(self):
        StorePaymentGateway.objects.create(
            store=self.loja, name='MP', gateway_type='mercadopago', is_enabled=True, access_token='APP_USR-x',
        )
        self.assertTrue(self._get().data['mercado_pago']['conectado'])

    def test_mercado_pago_desligado_nao_conta(self):
        StorePaymentGateway.objects.create(
            store=self.loja, name='MP', gateway_type='mercadopago', is_enabled=False, access_token='APP_USR-x',
        )
        self.assertFalse(self._get().data['mercado_pago']['conectado'])

    @override_settings(MERCADO_PAGO_ACCESS_TOKEN='APP_USR-plataforma')
    def test_loja_que_recebe_na_conta_da_plataforma_esta_conectada(self):
        # Cê Saladas, Pastita, Ivoneth: lojas do dono, recebem no MP dele.
        self.loja.usa_gateway_da_plataforma = True
        self.loja.save(update_fields=['usa_gateway_da_plataforma'])
        mp = self._get().data['mercado_pago']
        self.assertTrue(mp['conectado'])
        self.assertEqual(mp['conta'], 'plataforma')

    @override_settings(MERCADO_PAGO_ACCESS_TOKEN='')
    def test_flag_da_plataforma_sem_token_nao_conta(self):
        self.loja.usa_gateway_da_plataforma = True
        self.loja.save(update_fields=['usa_gateway_da_plataforma'])
        self.assertFalse(self._get().data['mercado_pago']['conectado'])

    def test_loja_de_outro_dono_e_404(self):
        outro = User.objects.create_user(username='outro-integracoes', password='x')
        alheia = Store.objects.create(name='Outra', slug='outra-integra', owner=outro, status='active')

        self.assertEqual(self._get(alheia.slug).status_code, 404)

    def test_sem_loja_e_400(self):
        self.assertEqual(self.client.get(URL).status_code, 400)
