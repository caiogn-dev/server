"""Regressão de integridade: StorePayment.store era NULL-able no banco.

O invariante "toda cobrança pertence a uma loja" vivia SÓ no save(). Qualquer
caminho que fura o save() (bulk_create, update, SQL cru) podia gravar um
pagamento órfão, sem loja — corrompendo relatórios financeiros e o
roteamento multi-tenant. Fix: a coluna passa a NOT NULL (o banco garante).

Cenários:
  1. bulk_create sem store (fura o save()) → IntegrityError no banco.
  2. Regressão: pagamento com order continua inferindo a loja no save().
"""
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.stores.models import Store, StoreOrder, StorePayment

User = get_user_model()


class StorePaymentStoreRequiredTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='pay-owner', email='po@t.com', password='x')
        self.store = Store.objects.create(name='Loja Pay', slug='loja-pay', owner=self.owner, status='active')

    def test_banco_rejeita_pagamento_sem_store(self):
        """bulk_create (bypass do save) não pode gravar cobrança órfã."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StorePayment.objects.bulk_create([
                    StorePayment(order=None, store=None, amount=Decimal('10.00'),
                                 payment_id=str(uuid.uuid4())),
                ])

    def test_pagamento_com_order_infere_store(self):
        """Regressão: save() continua inferindo a loja a partir do pedido."""
        order = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='+55',
            subtotal=Decimal('10.00'), total=Decimal('10.00'), payment_status='pending',
        )
        pay = StorePayment.objects.create(order=order, amount=Decimal('10.00'))
        self.assertEqual(pay.store_id, self.store.id)
