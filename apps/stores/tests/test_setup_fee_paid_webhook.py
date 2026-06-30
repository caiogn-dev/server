from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.stores.models import Store, StoreSubscription
from apps.stores.services import subscription_service

User = get_user_model()


class SetupFeePaidTest(TestCase):
    def test_marks_setup_fee_paid_on_approved(self):
        owner = User.objects.create_user(username='owner-sf1', password='x')
        store = Store.objects.create(name='Loja', slug='loja-sf', owner=owner)
        StoreSubscription.objects.create(store=store, mp_setup_payment_id='PREF-9')
        res = subscription_service.mark_setup_fee_paid('setup:loja-sf', 'approved')
        self.assertTrue(res['processed'])
        sub = StoreSubscription.objects.get(store=store)
        self.assertTrue(sub.setup_fee_paid)

    def test_ignores_non_approved(self):
        owner = User.objects.create_user(username='owner-sf2', password='x')
        store = Store.objects.create(name='Loja', slug='loja-sf2', owner=owner)
        StoreSubscription.objects.create(store=store, mp_setup_payment_id='PREF-8')
        res = subscription_service.mark_setup_fee_paid('setup:loja-sf2', 'pending')
        self.assertFalse(res['processed'])
        self.assertFalse(StoreSubscription.objects.get(store=store).setup_fee_paid)

    def test_unknown_store_is_safe(self):
        res = subscription_service.mark_setup_fee_paid('setup:nao-existe', 'approved')
        self.assertFalse(res['processed'])
