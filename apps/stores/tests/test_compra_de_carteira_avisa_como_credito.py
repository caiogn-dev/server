"""Compra de saldo da carteira não pode parecer pedido que sumiu.

26/09, Cê Saladas: Flaviane comprou o Pacote Leve (pagou R$ 139, ganhou
R$ 152 de saldo). O push disse "Novo pedido #CE-2609267553 — R$ 139,00"; o
dono abriu o quadro de pedidos, não encontrou nada (venda de saldo não entra
no quadro, por desenho) e achou que o pedido tinha sumido e não imprimiu.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreOrder
from apps.stores.services import realtime_service
from apps.stores.tasks import texto_do_aviso_de_pedido

User = get_user_model()


class AvisoDeCarteiraTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dona-carteira-aviso', password='x')
        self.store = Store.objects.create(name='Cê', slug='ce-carteira-aviso', owner=owner, billing_exempt=True)

    def _pedido(self, **extra):
        campos = dict(store=self.store, customer_name='Flaviane Paes', customer_phone='5511976457452',
                      total=Decimal('139.00'), subtotal=Decimal('139.00'), status='confirmed', payment_status='paid')
        campos.update(extra)
        return StoreOrder.objects.create(**campos)

    def test_push_de_compra_de_saldo_diz_credito_e_nao_pedido(self):
        pedido = self._pedido(source='carteira', metadata={'origem': 'carteira_prepaga', 'credito_concedido': '152.00'})
        titulo, mensagem, url = texto_do_aviso_de_pedido(pedido)
        self.assertIn('Crédito comprado', titulo)
        self.assertNotIn('Novo pedido', titulo)
        self.assertIn('R$ 152.00 de saldo', mensagem)
        self.assertIn('pagou R$ 139.00', mensagem)
        self.assertIn('Não é pedido', mensagem)
        self.assertEqual(url, '/loyalty')

    def test_pedido_de_comida_continua_igual(self):
        pedido = self._pedido(source='web')
        titulo, mensagem, url = texto_do_aviso_de_pedido(pedido)
        self.assertEqual(titulo, f'Novo pedido #{pedido.order_number}')
        self.assertEqual(url, f'/orders/{pedido.id}')

    def test_evento_em_tempo_real_leva_a_origem_e_o_credito(self):
        pedido = self._pedido(source='carteira', metadata={'credito_concedido': '152.00'})
        enviados = []

        class Camada:
            async def group_send(self, grupo, mensagem):
                enviados.append(mensagem)

        with patch.object(realtime_service, 'get_channel_layer', return_value=Camada()):
            realtime_service.broadcast_order_event(pedido, 'order.created')

        self.assertTrue(enviados)
        payload = enviados[0].get('payload') or enviados[0].get('data') or enviados[0]
        # O payload pode vir aninhado; o que importa é que os dois campos cheguem.
        texto = str(enviados)
        self.assertIn("'source': 'carteira'", texto)
        self.assertIn("'credito_concedido': '152.00'", texto)
