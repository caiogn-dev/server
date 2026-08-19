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

from apps.stores.models import Store, StoreOrder
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

    def test_pedido_em_preparo_e_nao_pago_ainda_cancela(self):
        o = self._pedido(StoreOrder.OrderStatus.PREPARING, StoreOrder.PaymentStatus.PENDING)
        CheckoutService._apply_order_webhook_status(o, 'cancelled')
        o.refresh_from_db()
        self.assertEqual(o.status, StoreOrder.OrderStatus.CANCELLED)
