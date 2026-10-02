"""Cobrança cancelada não pode derrubar venda já paga ou já entregue.

Em 19/08 cancelei no Mercado Pago 4 cobranças órfãs do pedido CE-2608190245
(Sheslley). O pedido estava `delivered/paid` — pago na MAQUININHA, fora do
gateway. O webhook `cancelled` chegou e o handler rebaixou a venda inteira
para `cancelled/failed`, sumindo com ela da tela de quem estava trabalhando.

A trava que existia só cobria "há OUTRA cobrança confirmada no gateway".
Pagamento em maquininha, dinheiro ou PIX na mão não produz StorePayment
COMPLETED — e era justamente esse o caso.

Regra: o gateway manda no que é dele (a cobrança). Ele não manda numa venda
que já foi paga por outro meio nem numa comida que já saiu para o cliente.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import Store, StoreOrder, StoreOrderItem, StoreProduct
from apps.stores.services.checkout_service import CheckoutService


class WebhookNaoDerrubaVendaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        owner = User.objects.create_user(username='dono_nd', email='d@nd.com', password='x')
        self.store = Store.objects.create(name='Loja ND', slug='loja-nd', owner=owner)

    def _pedido(self, status, payment_status):
        return StoreOrder.objects.create(
            store=self.store, customer_name='Sheslley Costa',
            customer_email='s@t.com', customer_phone='63992509193',
            subtotal=Decimal('39.33'), total=Decimal('39.33'),
            status=status, payment_status=payment_status,
        )

    def test_pedido_pago_na_maquininha_sobrevive_ao_cancelamento(self):
        o = self._pedido(StoreOrder.OrderStatus.DELIVERED, StoreOrder.PaymentStatus.PAID)
        CheckoutService._apply_order_webhook_status(o, 'cancelled')
        o.refresh_from_db()
        self.assertEqual(o.status, StoreOrder.OrderStatus.DELIVERED)
        self.assertEqual(o.payment_status, StoreOrder.PaymentStatus.PAID)

    def test_pedido_entregue_sobrevive_mesmo_sem_estar_pago(self):
        """Comida que já saiu não volta porque uma cobrança venceu."""
        o = self._pedido(StoreOrder.OrderStatus.DELIVERED, StoreOrder.PaymentStatus.PENDING)
        CheckoutService._apply_order_webhook_status(o, 'cancelled')
        o.refresh_from_db()
        self.assertEqual(o.status, StoreOrder.OrderStatus.DELIVERED)

    def test_pedido_completo_sobrevive(self):
        o = self._pedido(StoreOrder.OrderStatus.COMPLETED, StoreOrder.PaymentStatus.PAID)
        CheckoutService._apply_order_webhook_status(o, 'rejected')
        o.refresh_from_db()
        self.assertEqual(o.status, StoreOrder.OrderStatus.COMPLETED)

    def test_estorno_de_verdade_continua_valendo(self):
        """Refund é decisão do lojista sobre venda paga — esse tem que passar."""
        o = self._pedido(StoreOrder.OrderStatus.DELIVERED, StoreOrder.PaymentStatus.PAID)
        CheckoutService._apply_order_webhook_status(o, 'refunded')
        o.refresh_from_db()
        self.assertEqual(o.status, StoreOrder.OrderStatus.REFUNDED)

    def test_pedido_pendente_ainda_pode_ser_cancelado(self):
        """Sem isso a trava viraria um pedido zumbi que nunca cancela."""
        o = self._pedido(StoreOrder.OrderStatus.PENDING, StoreOrder.PaymentStatus.PENDING)
        CheckoutService._apply_order_webhook_status(o, 'cancelled')
        o.refresh_from_db()
        self.assertEqual(o.status, StoreOrder.OrderStatus.CANCELLED)

    def test_pedido_em_preparo_sobrevive_a_tentativa_recusada(self):
        """CE-2610029555 (Carla, 02/10): pedido em preparo, link de pagamento
        enviado; a 1ª tentativa no link foi recusada e o webhook cancelou a
        venda inteira — a cliente pagou o PIX 4 minutos depois num pedido já
        morto e a loja relançou em duplicidade. Cobrança recusada derruba a
        cobrança; o pedido que a loja já aceitou segue, com o pagamento em falha
        para a equipe ver."""
        for status_do_gateway in ('rejected', 'cancelled'):
            o = self._pedido(StoreOrder.OrderStatus.PREPARING, StoreOrder.PaymentStatus.PENDING)
            CheckoutService._apply_order_webhook_status(o, status_do_gateway)
            o.refresh_from_db()
            self.assertEqual(o.status, StoreOrder.OrderStatus.PREPARING)
            self.assertEqual(o.payment_status, StoreOrder.PaymentStatus.FAILED)
            self.assertIsNone(o.cancelled_at)

    def test_nenhum_estado_aceito_pela_loja_e_cancelado_pelo_gateway(self):
        for aceito in (
            StoreOrder.OrderStatus.CONFIRMED,
            StoreOrder.OrderStatus.PREPARING,
            StoreOrder.OrderStatus.READY,
            StoreOrder.OrderStatus.OUT_FOR_DELIVERY,
        ):
            o = self._pedido(aceito, StoreOrder.PaymentStatus.PENDING)
            CheckoutService._apply_order_webhook_status(o, 'rejected')
            o.refresh_from_db()
            self.assertEqual(o.status, aceito)


class PagamentoAprovadoDepoisDoCancelamentoTests(TestCase):
    """Se o gateway cancelou o pedido e o dinheiro entra depois (cliente tentou
    de novo no mesmo link), a venda volta. Cancelamento feito pela LOJA não
    volta: ali houve decisão de alguém."""

    def setUp(self):
        User = get_user_model()
        owner = User.objects.create_user(username='dono_pd', email='d@pd.com', password='x')
        self.store = Store.objects.create(name='Loja PD', slug='loja-pd', owner=owner)
        self.produto = StoreProduct.objects.create(
            store=self.store, name='Magnífico Camarão', slug='camarao', price=Decimal('37.83'),
            track_stock=True, stock_quantity=10, sold_count=0,
        )

    def _pedido_pendente_com_baixa(self):
        o = StoreOrder.objects.create(
            store=self.store, customer_name='Carla Miranda',
            customer_email='c@m.com', customer_phone='63992221268',
            subtotal=Decimal('37.83'), total=Decimal('37.83'),
            status=StoreOrder.OrderStatus.PENDING, payment_status=StoreOrder.PaymentStatus.PENDING,
        )
        StoreOrderItem.objects.create(order=o, product=self.produto, product_name='Magnífico Camarão',
                                      unit_price=Decimal('37.83'), quantity=1, subtotal=Decimal('37.83'))
        # A baixa que o checkout fez ao criar o pedido.
        StoreProduct.objects.filter(pk=self.produto.pk).update(stock_quantity=9, sold_count=1)
        return o

    def test_pix_aprovado_depois_de_cancelamento_do_gateway_reabre_o_pedido(self):
        o = self._pedido_pendente_com_baixa()
        CheckoutService._apply_order_webhook_status(o, 'rejected')
        o.refresh_from_db()
        self.assertEqual(o.status, StoreOrder.OrderStatus.CANCELLED)
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.stock_quantity, 10)  # devolvido no cancelamento

        CheckoutService._apply_order_webhook_status(o, 'approved')
        o.refresh_from_db()
        self.assertEqual(o.status, StoreOrder.OrderStatus.CONFIRMED)
        self.assertEqual(o.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertIsNone(o.cancelled_at)
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.stock_quantity, 9)  # baixado de novo
        self.assertEqual(self.produto.sold_count, 1)

    def test_aprovado_repetido_nao_baixa_estoque_duas_vezes(self):
        o = self._pedido_pendente_com_baixa()
        CheckoutService._apply_order_webhook_status(o, 'rejected')
        CheckoutService._apply_order_webhook_status(o, 'approved')
        CheckoutService._apply_order_webhook_status(o, 'approved')
        self.produto.refresh_from_db()
        self.assertEqual(self.produto.stock_quantity, 9)

    def test_cancelamento_feito_pela_loja_nao_e_desfeito_pelo_pagamento(self):
        o = self._pedido_pendente_com_baixa()
        o.status = StoreOrder.OrderStatus.CANCELLED
        o.save()
        CheckoutService._apply_order_webhook_status(o, 'approved')
        o.refresh_from_db()
        self.assertEqual(o.status, StoreOrder.OrderStatus.CANCELLED)
        self.assertEqual(o.payment_status, StoreOrder.PaymentStatus.PAID)
