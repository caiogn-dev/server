"""Cartão na maquininha: a comanda avisa o entregador para levar a máquina.

Reclamação medida no relatório de conversas da Cê Saladas (02/10): "não veio
maquininha para pagamento". O pedido diz `card_on_delivery`, mas o papel que o
entregador leva só mostrava a forma de pagamento crua lá embaixo.

O aviso vai em `order.internal_notes` do payload — a faixa "ATENCAO DA LOJA",
que todo print agent instalado imprime desde abril. Os PCs das lojas rodam
versões antigas do agente (a 0.4 nunca foi instalada), então um campo novo não
sairia no papel.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreOrder
from apps.stores.services.print_service import build_order_print_payload

AVISO = 'LEVAR MAQUININHA'


class ComandaLevaMaquininhaTests(TestCase):
    def setUp(self):
        dono = get_user_model().objects.create_user(username='dono_mq', email='d@mq.com', password='x')
        self.store = Store.objects.create(name='Loja MQ', slug='loja-mq', owner=dono)

    def _pedido(self, **campos):
        dados = dict(
            store=self.store, customer_name='Cliente', customer_phone='63999990000',
            subtotal=Decimal('37.83'), total=Decimal('63.59'), delivery_method='delivery',
            payment_method='card_on_delivery', payment_status='pending', status='confirmed',
        )
        dados.update(campos)
        return StoreOrder.objects.create(**dados)

    def test_cartao_na_entrega_avisa_levar_maquininha_com_o_valor(self):
        notas = build_order_print_payload(self._pedido())['order']['internal_notes']
        self.assertIn(AVISO, notas)
        self.assertIn('63,59', notas)

    def test_aviso_vem_antes_da_nota_interna_da_loja(self):
        notas = build_order_print_payload(self._pedido(internal_notes='Cliente pediu sem cebola'))['order']['internal_notes']
        self.assertTrue(notas.startswith(AVISO), notas)
        self.assertIn('Cliente pediu sem cebola', notas)

    def test_ja_pago_nao_pede_maquininha(self):
        notas = build_order_print_payload(self._pedido(payment_status='paid'))['order']['internal_notes']
        self.assertNotIn(AVISO, notas)

    def test_outras_formas_nao_pedem_maquininha(self):
        for forma in ('pix', 'cash', 'card', 'credit_card'):
            notas = build_order_print_payload(self._pedido(payment_method=forma))['order']['internal_notes']
            self.assertNotIn(AVISO, notas, forma)
