"""Pedido não pode desaparecer do painel porque o cartão não passou.

11/ago/2026, pedido CE-2608113992 (Aline, R$ 270,37). O que a dona da loja viu:
o pedido apareceu no painel e sumiu um segundo depois, "como se tivesse sido
excluído". O que aconteceu de verdade:

    16:20:06  pedido criado, WS emite order.created  → aparece no painel
    16:20:07  MP recusa o payload com 400:
              '$.payer.address.street_number' - length must be <= 10, but got 12
    16:20:07  checkout marca status=FAILED           → some da lista

Duas coisas erradas na mesma linha:

1. O 400 era ERRO NOSSO de payload (endereço "Lt 11 casa 2"). O cartão da
   cliente nunca chegou a ser consultado — não havia recusa nenhuma para
   registrar, e mesmo assim o pedido foi condenado.

2. Mesmo em recusa de verdade do emissor, `OrderStatus.FAILED` esconde o
   pedido. Cartão recusado é venda a recuperar (mandar PIX, cobrar na
   entrega), não pedido morto. O `payment_status` já conta essa história sem
   apagar o pedido da tela de quem está trabalhando.

Regra: `payment_status` registra o que houve com o dinheiro; `status` do
pedido não vira FAILED por causa de pagamento.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from apps.stores.models import Store, StoreOrder, StoreOrderItem
from apps.stores.services import mp_orders
from apps.stores.services.checkout_service import CheckoutService

ERRO_DE_PAYLOAD = {
    'errors': [{
        'code': 'property_value',
        'message': 'Invalid value for property',
        'details': ["'$.payer.address.street_number' - length must be <= 10, but got 12"],
    }],
}
RECUSA_DO_EMISSOR = {
    'status': 'rejected',
    'status_detail': 'cc_rejected_insufficient_amount',
    'transactions': {'payments': [{'id': 'PAY9', 'status_detail': 'cc_rejected_insufficient_amount'}]},
}


class ClassificaFalhaDoMPTest(TestCase):
    """Erro de payload nosso não é recusa de cartão — e não pode ser tratado como uma."""

    def test_400_de_validacao_e_erro_de_payload(self):
        self.assertTrue(mp_orders.eh_erro_de_payload(400, ERRO_DE_PAYLOAD))

    def test_recusa_do_emissor_nao_e_erro_de_payload(self):
        self.assertFalse(mp_orders.eh_erro_de_payload(200, RECUSA_DO_EMISSOR))

    def test_falha_generica_nao_e_erro_de_payload(self):
        self.assertFalse(mp_orders.eh_erro_de_payload(500, {'message': 'internal error'}))

    def test_aprovado_nao_e_erro_de_payload(self):
        self.assertFalse(mp_orders.eh_erro_de_payload(201, {'status': 'processed'}))


class PedidoContinuaVisivelTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('dona', 'dona@ce.com', 'x')
        self.store = Store.objects.create(
            name='Cê Saladas', slug='ce-saladas-falha-cartao', owner=self.owner,
            status=Store.StoreStatus.ACTIVE, billing_exempt=True,
        )
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Aline Nasche',
            customer_email='aline@x.com', customer_phone='11975373744',
            delivery_address={'street_name': 'Quadra 505', 'number': 'Lt 11 casa 2',
                              'city': 'Palmas', 'state': 'TO'},
            subtotal=Decimal('248.37'), delivery_fee=Decimal('22.00'),
            total=Decimal('270.37'),
            status=StoreOrder.OrderStatus.PENDING,
            payment_status=StoreOrder.PaymentStatus.PENDING,
        )
        StoreOrderItem.objects.create(
            order=self.order, product_name='Combo Queridinha',
            unit_price=Decimal('248.37'), quantity=1,
        )

    def _cobrar(self, status_code, body):
        with patch.object(CheckoutService, 'get_payment_credentials',
                          return_value={'access_token': 'TOKEN', 'public_key': 'PK'}), \
             patch.object(mp_orders, 'create_order', return_value=(status_code, body)):
            return CheckoutService.create_payment(
                self.order, payment_method='credit_card',
                payment_data={'token': 'TKN', 'payment_method_id': 'master', 'installments': 1,
                              'payer': {'email': 'aline@x.com'}},
            )

    def test_erro_de_payload_nao_marca_pedido_como_falho(self):
        resultado = self._cobrar(400, ERRO_DE_PAYLOAD)
        self.order.refresh_from_db()

        self.assertFalse(resultado['success'])
        self.assertNotEqual(self.order.status, StoreOrder.OrderStatus.FAILED)
        self.assertEqual(
            self.order.payment_status, StoreOrder.PaymentStatus.PENDING,
            'não houve cobrança nenhuma: o MP recusou o nosso payload',
        )

    def test_recusa_do_emissor_registra_o_pagamento_mas_mantem_o_pedido(self):
        resultado = self._cobrar(200, RECUSA_DO_EMISSOR)
        self.order.refresh_from_db()

        self.assertFalse(resultado['success'])
        self.assertEqual(self.order.payment_status, StoreOrder.PaymentStatus.FAILED)
        self.assertNotEqual(
            self.order.status, StoreOrder.OrderStatus.FAILED,
            'cartão recusado é venda a recuperar — o pedido tem que continuar na tela',
        )
