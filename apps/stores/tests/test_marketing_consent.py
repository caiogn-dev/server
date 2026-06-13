"""Consentimento de marketing (LGPD art. 8): opt-in registra accepts_marketing + timestamp."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.services.customer_identity import CustomerIdentityService
from apps.stores.models import Store, StoreCustomer

User = get_user_model()


class MarketingConsentTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='o-mkt', email='o-mkt@t.com', password='x')
        self.store = Store.objects.create(name='L', slug='l-mkt', owner=self.owner, status='active')

    def _sync(self, accepts):
        return CustomerIdentityService.sync_checkout_customer(
            store=self.store, customer_name='Cliente', phone='5599999990000',
            email='c@t.com', accepts_marketing=accepts,
        )

    def test_opt_in_registra_consentimento_e_timestamp(self):
        self._sync(True)
        sc = StoreCustomer.objects.get(store=self.store)
        self.assertTrue(sc.accepts_marketing)
        self.assertIsNotNone(sc.marketing_opt_in_at)

    def test_sem_consentimento_fica_false(self):
        self._sync(False)
        sc = StoreCustomer.objects.get(store=self.store)
        self.assertFalse(sc.accepts_marketing)
        self.assertIsNone(sc.marketing_opt_in_at)

    def test_none_nao_altera(self):
        self._sync(True)
        self._sync(None)  # checkout sem o campo não deve revogar
        sc = StoreCustomer.objects.get(store=self.store)
        self.assertTrue(sc.accepts_marketing)
