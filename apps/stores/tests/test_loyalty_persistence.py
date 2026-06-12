"""Fidelidade persistida — saldo materializado + trilha de transações auditável."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.models import (
    Store,
    StoreLoyaltyAccount,
    StoreLoyaltyTransaction,
    StoreOrder,
)
from apps.stores.services.loyalty_service import LoyaltyService

User = get_user_model()


class LoyaltyPersistenceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-loyal', email='owner-loyal@test.com', password='x',
        )
        self.customer = User.objects.create_user(
            username='cliente-loyal', email='cliente-loyal@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Loyal', slug='loja-loyal', owner=self.owner, status='active',
            metadata={'loyalty_salads_required': 5, 'loyalty_enabled': True},
        )

    def _order(self, **kw):
        return StoreOrder.objects.create(
            store=self.store, customer=self.customer, subtotal=30, total=30,
            status=kw.pop('status', 'delivered'), **kw,
        )

    def test_credit_cria_conta_e_transacao(self):
        order = self._order()
        LoyaltyService.credit_qualified(self.store, self.customer, order, quantity=3)

        account = StoreLoyaltyAccount.objects.get(store=self.store, user=self.customer)
        self.assertEqual(account.qualified_count, 3)
        tx = StoreLoyaltyTransaction.objects.get(account=account)
        self.assertEqual(tx.kind, 'earn')
        self.assertEqual(tx.quantity, 3)
        self.assertEqual(tx.order, order)

    def test_credit_e_idempotente_por_pedido(self):
        order = self._order()
        LoyaltyService.credit_qualified(self.store, self.customer, order, quantity=3)
        LoyaltyService.credit_qualified(self.store, self.customer, order, quantity=3)

        account = StoreLoyaltyAccount.objects.get(store=self.store, user=self.customer)
        self.assertEqual(account.qualified_count, 3)
        self.assertEqual(StoreLoyaltyTransaction.objects.filter(account=account).count(), 1)

    def test_redeem_registra_resgate(self):
        order = self._order()
        LoyaltyService.credit_qualified(self.store, self.customer, order, quantity=10)
        redeem_order = self._order()
        LoyaltyService.redeem(self.store, self.customer, redeem_order, rewards=1)

        account = StoreLoyaltyAccount.objects.get(store=self.store, user=self.customer)
        self.assertEqual(account.redeemed_count, 1)
        self.assertEqual(
            StoreLoyaltyTransaction.objects.filter(account=account, kind='redeem').count(), 1,
        )

    def test_status_usa_saldo_persistido(self):
        order = self._order()
        # threshold 5: 12 qualificados = 2 ganhos
        LoyaltyService.credit_qualified(self.store, self.customer, order, quantity=12)
        status = LoyaltyService.get_status(self.store, self.customer)

        self.assertEqual(status['qualified_salads'], 12)
        self.assertEqual(status['rewards_earned'], 2)
        self.assertEqual(status['available_rewards'], 2)
        self.assertEqual(status['remaining'], 3)  # 12 % 5 = 2 → faltam 3
        self.assertTrue(status['can_redeem'])

    def test_status_anonimo_zerado(self):
        status = LoyaltyService.get_status(self.store, None)
        self.assertEqual(status['qualified_salads'], 0)
        self.assertFalse(status['can_redeem'])

    def test_redeem_sem_saldo_levanta_erro(self):
        with self.assertRaises(ValueError):
            LoyaltyService.redeem(self.store, self.customer, self._order(), rewards=1)

    def test_get_loyalty_status_faz_backfill_do_historico_legado(self):
        from apps.stores.services.checkout_service import CheckoutService

        # Pedido legado com resgate gravado em metadata (formato antigo)
        self._order(metadata={'loyalty_reward': {'applied': True, 'count': 1}})

        status = CheckoutService.get_loyalty_status(self.store, self.customer)

        # Conta criada e resgate legado migrado para a trilha persistida
        account = StoreLoyaltyAccount.objects.get(store=self.store, user=self.customer)
        self.assertEqual(account.redeemed_count, 1)
        self.assertEqual(status['rewards_redeemed'], 1)
        self.assertEqual(
            StoreLoyaltyTransaction.objects.filter(account=account, kind='redeem', order=None).count(), 1,
        )

        # Segunda chamada não duplica o backfill
        CheckoutService.get_loyalty_status(self.store, self.customer)
        account.refresh_from_db()
        self.assertEqual(account.redeemed_count, 1)
