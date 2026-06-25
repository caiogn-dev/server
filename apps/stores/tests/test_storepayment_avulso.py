"""Fase 3 — B0: StorePayment.order nullable + store obrigatório (cobrança avulsa).

Permite cobrança de valor arbitrário SEM pedido, escopada por loja.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StorePayment

User = get_user_model()


class StorePaymentAvulsoTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o-av', password='x')
        self.store = Store.objects.create(
            name='Loja Av', slug='loja-av', owner=self.owner, status='active',
        )

    def test_create_avulso_without_order(self):
        """Cobrança avulsa: order=None, store obrigatório."""
        sp = StorePayment.objects.create(
            store=self.store,
            amount=Decimal('25.00'),
            payment_method='pix',
            status=StorePayment.PaymentStatus.PENDING,
        )
        sp.refresh_from_db()
        self.assertIsNone(sp.order_id)
        self.assertEqual(sp.store_id, self.store.id)
        self.assertEqual(sp.amount, Decimal('25.00'))

    def test_store_derived_from_order(self):
        """Quando order é dado e store não, store é inferido do pedido."""
        order = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='5599999999999',
            subtotal=Decimal('10.00'), total=Decimal('10.00'),
        )
        sp = StorePayment.objects.create(
            order=order,
            amount=Decimal('10.00'),
            payment_method='pix',
            status=StorePayment.PaymentStatus.PENDING,
        )
        sp.refresh_from_db()
        self.assertEqual(sp.store_id, self.store.id)

    def test_avulso_requires_store(self):
        """Sem order E sem store deve falhar (invariante: cobrança precisa de loja)."""
        with self.assertRaises(Exception):
            StorePayment.objects.create(
                amount=Decimal('15.00'),
                payment_method='pix',
                status=StorePayment.PaymentStatus.PENDING,
            )

    def test_completed_avulso_does_not_crash_sync(self):
        """StorePayment avulso (order=None) marcado completed não deve quebrar
        o sync (que tenta espelhar no pedido)."""
        sp = StorePayment.objects.create(
            store=self.store,
            amount=Decimal('25.00'),
            payment_method='pix',
            status=StorePayment.PaymentStatus.PENDING,
        )
        sp.status = StorePayment.PaymentStatus.COMPLETED
        sp.save()  # não deve levantar AttributeError por order None
        sp.refresh_from_db()
        self.assertEqual(sp.status, StorePayment.PaymentStatus.COMPLETED)
