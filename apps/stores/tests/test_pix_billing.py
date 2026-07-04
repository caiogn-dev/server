from django.test import TestCase
from django.contrib.auth.models import User
from apps.stores.models import Store, StoreSubscription


class BillingCycleFieldTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner_pix', 'owner_pix@x.com', 'x')
        self.store = Store.objects.create(name="Loja Teste", slug="loja-teste", owner=self.owner)

    def test_subscription_defaults_monthly_and_not_downgraded(self):
        sub = StoreSubscription.objects.create(store=self.store, plan="pro")
        self.assertEqual(sub.billing_cycle, "monthly")
        self.assertFalse(sub.downgraded_for_nonpayment)

    def test_billing_cycle_accepts_annual(self):
        sub = StoreSubscription.objects.create(store=self.store, plan="pro", billing_cycle="annual")
        self.assertEqual(sub.billing_cycle, "annual")
