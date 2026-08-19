"""Os itens da Orders API precisam somar exatamente o total cobrado.

A Orders API recusa a order inteira com 400 `order_items_total_amount_mismatch`
quando sum(items) != total_amount. O build_items mandava só os produtos,
enquanto total_amount é order.total — que inclui frete e desconto.

Vale para PIX e para CARTÃO (mesmo builder). No cartão o estrago era pior:
`eh_erro_de_payload` não conhece esse código, então a venda era marcada FAILED
como se o emissor tivesse recusado o cliente.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreOrder, StoreOrderItem
from apps.stores.services import mp_orders


def soma(items):
    return sum(
        (Decimal(str(i['unit_price'])) * int(i['quantity']) for i in items),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))


class ItensSomamOTotalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        owner = User.objects.create_user(username='dono_it', email='d@it.com', password='x')
        self.store = Store.objects.create(name='Loja IT', slug='loja-it', owner=owner)

    def _pedido(self, subtotal, frete, desconto, total):
        o = StoreOrder.objects.create(
            store=self.store, customer_name='Maria Silva',
            customer_email='m@t.com', customer_phone='63999990000',
            subtotal=Decimal(subtotal), delivery_fee=Decimal(frete),
            discount=Decimal(desconto), total=Decimal(total),
        )
        StoreOrderItem.objects.create(
            order=o, product_name='Almôndega Premium',
            quantity=1, unit_price=Decimal(subtotal), subtotal=Decimal(subtotal),
        )
        return o

    def test_sem_frete_nem_desconto_mantem_itens_reais(self):
        o = self._pedido('30.75', '0.00', '0.00', '30.75')
        items = mp_orders.build_items(o)
        self.assertEqual(soma(items), Decimal('30.75'))
        self.assertEqual(items[0]['title'], 'Almôndega Premium')

    def test_com_frete_o_frete_vira_item(self):
        o = self._pedido('30.75', '11.66', '0.00', '42.41')
        items = mp_orders.build_items(o)
        self.assertEqual(soma(items), Decimal('42.41'))
        self.assertTrue(any('ntrega' in i['title'] for i in items), items)

    def test_pedido_real_ce_2608197068(self):
        """O caso que quebrou em produção: frete E desconto."""
        o = self._pedido('30.75', '11.66', '3.08', '39.33')
        items = mp_orders.build_items(o)
        self.assertEqual(soma(items), Decimal('39.33'))

    def test_payload_de_pix_fecha_com_total_amount(self):
        o = self._pedido('30.75', '11.66', '3.08', '39.33')
        p = mp_orders.build_pix_order_payload(o, 'm@t.com')
        self.assertEqual(soma(p['items']), Decimal(p['total_amount']))

    def test_payload_de_cartao_fecha_com_total_amount(self):
        o = self._pedido('30.75', '11.66', '3.08', '39.33')
        p = mp_orders.build_order_payload(
            o, card_token='tok', payment_method_id='visa', installments=1,
            payer_email='m@t.com',
        )
        self.assertEqual(soma(p['items']), Decimal(p['total_amount']))

    def test_mismatch_e_erro_de_payload_nosso_nao_recusa_do_cliente(self):
        corpo = {'errors': [{'code': 'order_items_total_amount_mismatch',
                             'message': 'Order items total amount sum does not match'}]}
        self.assertTrue(mp_orders.eh_erro_de_payload(400, corpo))
