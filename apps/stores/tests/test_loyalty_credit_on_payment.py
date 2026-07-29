"""Fidelidade deve creditar no momento em que o pagamento é aprovado.

Antes o crédito só acontecia em OrderService.update_status (paid/delivered/
completed) — pagamento aprovado via webhook setava CONFIRMED direto e o selo
só aparecia quando o lojista marcava "entregue" no painel.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import (
    Store,
    StoreLoyaltyTransaction,
    StoreOrder,
    StoreOrderItem,
)
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


class LoyaltyCreditOnPaymentTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-pay-loyal', email='opl@test.com', password='x',
        )
        self.customer = User.objects.create_user(
            username='cliente-pay-loyal', email='cpl@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Pay Loyal', slug='loja-pay-loyal', owner=self.owner,
            status='active', metadata={'loyalty_enabled': True},
        )

    def _order(self, customer=None, status='pending'):
        order = StoreOrder.objects.create(
            store=self.store, customer=customer, subtotal=30, total=30,
            status=status,
        )
        StoreOrderItem.objects.create(
            order=order, product_name='Rondelli de Frango',
            unit_price=30, quantity=2, subtotal=60,
        )
        return order

    def test_webhook_aprovado_credita_fidelidade(self):
        order = self._order(customer=self.customer)
        CheckoutService._apply_order_webhook_status(order, 'approved')

        tx = StoreLoyaltyTransaction.objects.get(
            account__store=self.store, account__user=self.customer, kind='earn',
        )
        self.assertEqual(tx.quantity, 2)
        self.assertEqual(tx.order, order)

    def test_webhook_aprovado_duas_vezes_credita_uma_vez(self):
        order = self._order(customer=self.customer)
        CheckoutService._apply_order_webhook_status(order, 'approved')
        CheckoutService._apply_order_webhook_status(order, 'approved')

        self.assertEqual(
            StoreLoyaltyTransaction.objects.filter(
                account__store=self.store, account__user=self.customer, kind='earn',
            ).count(),
            1,
        )

    def test_webhook_aprovado_sem_customer_nao_quebra(self):
        order = self._order(customer=None)
        CheckoutService._apply_order_webhook_status(order, 'approved')
        self.assertEqual(StoreLoyaltyTransaction.objects.count(), 0)

    def test_label_do_status_usa_rotulo_da_loja_nao_hardcoded_saladas(self):
        self.store.metadata['loyalty_item_label'] = 'rondelli'
        self.store.metadata['loyalty_item_label_plural'] = 'rondellis'
        self.store.save(update_fields=['metadata'])
        status = CheckoutService.get_loyalty_status(self.store, self.customer)
        self.assertIn('rondellis', status['label'])
        self.assertNotIn('saladas', status['label'])

    def test_guest_status_acha_conta_com_telefone_prefixado_55(self):
        # Autofill do Google salva com +55; pedido foi gravado sem o código
        # do país — as variantes precisam casar nos dois sentidos.
        from apps.stores.api.views.loyalty_views import LoyaltyGuestStatusView
        order = self._order(customer=self.customer)
        order.customer_phone = '63999547790'
        order.save(update_fields=['customer_phone'])
        view = LoyaltyGuestStatusView()
        self.assertEqual(view._resolve_user(self.store, '+55 63 99954-7790'), self.customer)
        self.assertEqual(view._resolve_user(self.store, '5563999547790'), self.customer)

    def test_guest_status_acha_conta_com_pedido_gravado_com_55(self):
        from apps.stores.api.views.loyalty_views import LoyaltyGuestStatusView
        order = self._order(customer=self.customer)
        order.customer_phone = '5563999547790'
        order.save(update_fields=['customer_phone'])
        view = LoyaltyGuestStatusView()
        self.assertEqual(view._resolve_user(self.store, '(63) 99954-7790'), self.customer)

    def test_webhook_rejeitado_nao_credita(self):
        order = self._order(customer=self.customer)
        CheckoutService._apply_order_webhook_status(order, 'rejected')
        self.assertEqual(StoreLoyaltyTransaction.objects.count(), 0)
