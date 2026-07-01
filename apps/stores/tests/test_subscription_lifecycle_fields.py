from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.stores.models import Store, StoreSubscription

User = get_user_model()


class SubscriptionLifecycleFieldsTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='testuser_lifecycle', password='x')

    def test_new_fields_exist_and_default_null(self):
        store = Store.objects.create(name='Loja X', slug='loja-x', owner=self.owner)
        sub = StoreSubscription.objects.create(store=store)
        self.assertIsNone(sub.grace_until)
        self.assertIsNone(sub.dunning_since)
        self.assertEqual(sub.mp_setup_payment_id, '')

    def test_grace_until_persists(self):
        store = Store.objects.create(name='Loja Y', slug='loja-y', owner=self.owner)
        sub = StoreSubscription.objects.create(store=store)
        when = timezone.now()
        sub.grace_until = when
        sub.save(update_fields=['grace_until'])
        sub.refresh_from_db()
        self.assertEqual(sub.grace_until, when)
