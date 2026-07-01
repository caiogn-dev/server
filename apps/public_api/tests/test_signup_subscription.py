from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreSubscription
from apps.stores.tasks import enforce_subscription_lifecycle


class SignupCreatesTrialingSubscriptionTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('public_api:owner-signup')

    def _payload(self, **overrides):
        payload = {
            'name': 'Fulano da Silva',
            'password': 'SenhaForte!2026',
            'email': 'fulano@example.com',
            'phone': '',
            'store_name': 'Loja do Fulano',
        }
        payload.update(overrides)
        return payload

    def test_signup_cria_subscription_trialing(self):
        resp = self.client.post(self.url, self._payload(), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)

        store_id = resp.data['store']['id']
        store = Store.objects.get(id=store_id)

        sub = StoreSubscription.objects.get(store=store)
        self.assertEqual(sub.status, StoreSubscription.Status.TRIALING)
        self.assertEqual(sub.plan, 'starter')
        self.assertEqual(store.plan, Store.StorePlan.STARTER)

    def test_signup_e_fim_do_trial_rebaixa_para_free(self):
        resp = self.client.post(
            self.url, self._payload(email='outra@example.com'), format='json'
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        store_id = resp.data['store']['id']
        store = Store.objects.get(id=store_id)
        store.trial_ends_at = timezone.now() - timedelta(days=1)
        store.save(update_fields=['trial_ends_at'])

        with override_settings(BILLING_ENFORCEMENT_ENABLED=True):
            enforce_subscription_lifecycle()

        store.refresh_from_db()
        sub = StoreSubscription.objects.get(store=store)
        self.assertEqual(store.plan, 'free')
        self.assertEqual(sub.status, 'canceled')
