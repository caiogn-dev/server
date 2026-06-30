from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.stores.models import Store, StoreSubscription
from apps.stores.tasks import enforce_subscription_lifecycle


def mk(slug, **store_kw):
    owner = User.objects.create_user(username=f'owner_{slug}', password='x')
    return Store.objects.create(name=slug, slug=slug, owner=owner, **store_kw)


@override_settings(BILLING_GRACE_DAYS=3, BILLING_DUNNING_DAYS=3)
class EnforceSubscriptionTaskTest(TestCase):
    def test_expired_trial_starts_grace(self):
        store = mk('s1', trial_ends_at=timezone.now() - timedelta(hours=1))
        sub = StoreSubscription.objects.create(store=store, status='trialing')
        res = enforce_subscription_lifecycle()
        sub.refresh_from_db()
        self.assertIsNotNone(sub.grace_until)
        self.assertEqual(sub.status, 'trialing')
        self.assertEqual(res['grace_started'], 1)

    def test_grace_over_suspends(self):
        store = mk('s2', trial_ends_at=timezone.now() - timedelta(days=5))
        StoreSubscription.objects.create(
            store=store, status='trialing',
            grace_until=timezone.now() - timedelta(hours=1),
        )
        res = enforce_subscription_lifecycle()
        sub = StoreSubscription.objects.get(store=store)
        self.assertEqual(sub.status, 'suspended')
        self.assertEqual(res['suspended'], 1)

    def test_exempt_store_untouched(self):
        store = mk('s3', trial_ends_at=timezone.now() - timedelta(days=99),
                   billing_exempt=True)
        StoreSubscription.objects.create(store=store, status='trialing')
        enforce_subscription_lifecycle()
        sub = StoreSubscription.objects.get(store=store)
        self.assertEqual(sub.status, 'trialing')
        self.assertIsNone(sub.grace_until)

    def test_active_untouched(self):
        store = mk('s4', trial_ends_at=timezone.now() - timedelta(days=30))
        StoreSubscription.objects.create(store=store, status='active')
        enforce_subscription_lifecycle()
        sub = StoreSubscription.objects.get(store=store)
        self.assertEqual(sub.status, 'active')

    def test_past_due_starts_dunning(self):
        """past_due sem dunning_since → grava dunning_since=now; NÃO toca grace_until."""
        store = mk('s5')
        before = timezone.now()
        sub = StoreSubscription.objects.create(
            store=store, status='past_due', dunning_since=None,
        )
        res = enforce_subscription_lifecycle()
        sub.refresh_from_db()
        after = timezone.now()
        self.assertIsNotNone(sub.dunning_since, 'dunning_since deve ser gravado')
        self.assertGreaterEqual(sub.dunning_since, before)
        self.assertLessEqual(sub.dunning_since, after)
        self.assertIsNone(sub.grace_until, 'grace_until não deve ser tocado para past_due')
        self.assertEqual(sub.status, 'past_due', 'status não deve mudar na primeira varredura')
        self.assertEqual(res['grace_started'], 1)
