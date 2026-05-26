from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreCart

User = get_user_model()


class CleanupCartsCommandTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='cart-cleanup-owner', password='x')
        self.store = Store.objects.create(
            name='Cleanup Store', slug='cleanup-store',
            owner=self.owner, status='active', store_type='food',
        )

    def _cart(self, user=None, is_active=True, days_old=0):
        cart = StoreCart.objects.create(store=self.store, user=user, is_active=is_active)
        StoreCart.objects.filter(pk=cart.pk).update(
            updated_at=timezone.now() - timedelta(days=days_old)
        )
        return cart

    def test_dry_run_nao_deleta(self):
        self._cart(user=None, days_old=40)
        out = StringIO()
        call_command('cleanup_carts', '--dry-run', stdout=out)
        self.assertEqual(StoreCart.objects.count(), 1)
        self.assertIn('DRY RUN', out.getvalue())

    def test_deleta_guest_antigo(self):
        self._cart(user=None, days_old=31)   # deve ser deletado
        self._cart(user=None, days_old=10)   # deve ficar
        call_command('cleanup_carts', '--guest-days=30', stdout=StringIO())
        self.assertEqual(StoreCart.objects.count(), 1)

    def test_deleta_inativo_antigo(self):
        self._cart(is_active=False, days_old=8)  # deve ser deletado
        self._cart(is_active=False, days_old=3)  # deve ficar
        call_command('cleanup_carts', '--inactive-days=7', stdout=StringIO())
        self.assertEqual(StoreCart.objects.count(), 1)

    def test_nao_deleta_carrinho_ativo_recente(self):
        self._cart(user=None, days_old=5, is_active=True)
        call_command('cleanup_carts', stdout=StringIO())
        self.assertEqual(StoreCart.objects.count(), 1)
