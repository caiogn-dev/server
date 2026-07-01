"""Pagamento na entrega: pedidos em dinheiro nascem 'pending' e nunca passam pelo
status PAID. Ao serem entregues/concluídos o dinheiro foi recebido → marcar pago,
senão a receita (que filtra payment_status='paid') zerava para lojas que vendem
em dinheiro na entrega/retirada (ex.: Cê Saladas).
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder

User = get_user_model()


class PaidOnDeliveryTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='ow-pod', email='ow-pod@t.com', password='x')
        self.store = Store.objects.create(name='Loja POD', slug='loja-pod', owner=self.owner, status='active')

    def _order(self, method, pay_status='pending'):
        return StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='+5563999',
            subtotal=Decimal('40.00'), total=Decimal('40.00'),
            payment_method=method, payment_status=pay_status,
        )

    def test_cash_order_marked_paid_on_delivered(self):
        order = self._order('cash')
        order.update_status(StoreOrder.OrderStatus.DELIVERED, notify=False)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertIsNotNone(order.paid_at)

    def test_cash_order_marked_paid_on_completed(self):
        order = self._order('cash')
        order.update_status(StoreOrder.OrderStatus.COMPLETED, notify=False)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertIsNotNone(order.paid_at)

    def test_online_order_not_auto_paid_on_delivery(self):
        # PIX/cartão pagam via webhook ANTES da entrega; entregar não pode marcar
        # pago um pedido online que continua pendente (evita receita falsa).
        order = self._order('pix')
        order.update_status(StoreOrder.OrderStatus.DELIVERED, notify=False)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.PENDING)
        self.assertIsNone(order.paid_at)

    def test_paid_at_not_overwritten_if_already_paid(self):
        from django.utils import timezone
        from datetime import timedelta
        first = timezone.now() - timedelta(days=2)
        order = self._order('cash', pay_status='paid')
        order.paid_at = first
        order.save(update_fields=['paid_at'])
        order.update_status(StoreOrder.OrderStatus.DELIVERED, notify=False)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertEqual(order.paid_at, first)

    def test_cancel_does_not_crash(self):
        # Regressão: update_status referenciava OrderStatus.PICKED_UP (inexistente),
        # estourando AttributeError ao cancelar/reembolsar.
        order = self._order('cash')
        order.update_status(StoreOrder.OrderStatus.CANCELLED, notify=False)
        order.refresh_from_db()
        self.assertEqual(order.status, StoreOrder.OrderStatus.CANCELLED)
        self.assertIsNotNone(order.cancelled_at)
        # cancelado NÃO vira pago
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.PENDING)
