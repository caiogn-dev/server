"""Fase 3 — B4: webhook casa StorePayment por external_id (multi-charge) com
fallback legado por order.payment_id. CAMINHO SENSÍVEL (prod cobra de verdade).
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StorePayment
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


def _charge(order, store, amount, ext, status=StorePayment.PaymentStatus.PENDING):
    return StorePayment.objects.create(
        order=order, store=store, amount=Decimal(amount),
        payment_method='pix', status=status, external_id=ext,
    )


class WebhookStorePaymentTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o-wh', password='x')
        self.store = Store.objects.create(
            name='Loja WH', slug='loja-wh', owner=self.owner, status='active',
        )

    def _order(self, total='100.00'):
        return StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='5599999999999',
            subtotal=Decimal(total), total=Decimal(total),
        )

    def test_approved_full_charge_marks_order_paid(self):
        order = self._order('100.00')
        _charge(order, self.store, '100.00', 'MPFULL')

        result = CheckoutService.process_payment_webhook('MPFULL', 'approved')

        self.assertIsNotNone(result)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertEqual(order.status, StoreOrder.OrderStatus.CONFIRMED)
        self.assertIsNotNone(order.paid_at)
        sp = StorePayment.objects.get(external_id='MPFULL')
        self.assertEqual(sp.status, StorePayment.PaymentStatus.COMPLETED)

    def test_approved_partial_does_not_mark_paid(self):
        order = self._order('100.00')
        _charge(order, self.store, '40.00', 'MPPART1')
        _charge(order, self.store, '60.00', 'MPPART2')

        CheckoutService.process_payment_webhook('MPPART1', 'approved')

        order.refresh_from_db()
        self.assertEqual(order.amount_paid, Decimal('40.00'))
        self.assertNotEqual(order.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertIsNone(order.paid_at)
        # a outra cobrança continua pendente intacta
        other = StorePayment.objects.get(external_id='MPPART2')
        self.assertEqual(other.status, StorePayment.PaymentStatus.PENDING)

    def test_two_charges_complete_marks_paid(self):
        order = self._order('100.00')
        _charge(order, self.store, '40.00', 'MPC1')
        _charge(order, self.store, '60.00', 'MPC2')

        CheckoutService.process_payment_webhook('MPC1', 'approved')
        CheckoutService.process_payment_webhook('MPC2', 'approved')

        order.refresh_from_db()
        self.assertEqual(order.amount_paid, Decimal('100.00'))
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertEqual(order.status, StoreOrder.OrderStatus.CONFIRMED)

    def test_approved_idempotent(self):
        order = self._order('100.00')
        _charge(order, self.store, '100.00', 'MPIDEM')

        CheckoutService.process_payment_webhook('MPIDEM', 'approved')
        order.refresh_from_db()
        first_paid_at = order.paid_at
        # segunda vez não deve duplicar nem quebrar
        CheckoutService.process_payment_webhook('MPIDEM', 'approved')
        order.refresh_from_db()
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertEqual(order.amount_paid, Decimal('100.00'))
        self.assertEqual(
            StorePayment.objects.filter(external_id='MPIDEM',
                                        status=StorePayment.PaymentStatus.COMPLETED).count(),
            1,
        )

    def test_legacy_fallback_by_order_payment_id(self):
        """Pedido antigo (sem StorePayment) — casa por order.payment_id."""
        order = self._order('100.00')
        order.payment_id = 'LEGACY1'
        order.payment_method = 'pix'
        order.save(update_fields=['payment_id', 'payment_method'])

        result = CheckoutService.process_payment_webhook('LEGACY1', 'approved')

        self.assertIsNotNone(result)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertEqual(order.status, StoreOrder.OrderStatus.CONFIRMED)

    def test_avulso_charge_no_order(self):
        sp = _charge(None, self.store, '25.00', 'MPAV')

        result = CheckoutService.process_payment_webhook('MPAV', 'approved')

        self.assertIsNone(result)  # sem pedido a sincronizar
        sp.refresh_from_db()
        self.assertEqual(sp.status, StorePayment.PaymentStatus.COMPLETED)

    def test_rejected_single_charge_cancels_order(self):
        """Regressão: cobrança única rejeitada cancela o pedido (comportamento legado)."""
        order = self._order('100.00')
        _charge(order, self.store, '100.00', 'MPREJ')

        CheckoutService.process_payment_webhook('MPREJ', 'rejected')

        order.refresh_from_db()
        self.assertEqual(order.status, StoreOrder.OrderStatus.CANCELLED)
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.FAILED)
