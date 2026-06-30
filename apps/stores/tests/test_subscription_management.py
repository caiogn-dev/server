"""
Testes TDD para os endpoints de gestão de assinatura:
  GET  /api/v1/stores/<slug>/subscription/
  POST /api/v1/stores/<slug>/subscription/cancel/
  POST /api/v1/stores/<slug>/subscription/change-plan/
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.stores.models import Store, StoreSubscription

User = get_user_model()


class SubscriptionManagementAPITest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='dono', email='dono@x.com', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja', owner=self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_status_none_when_no_subscription(self):
        r = self.client.get(f'/api/v1/stores/{self.store.slug}/subscription/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'none')

    def test_status_returns_plan_and_status(self):
        StoreSubscription.objects.create(store=self.store, plan='pro', status='active')
        r = self.client.get(f'/api/v1/stores/{self.store.slug}/subscription/')
        self.assertEqual(r.json()['plan'], 'pro')
        self.assertEqual(r.json()['status'], 'active')

    @patch('apps.stores.services.subscription_service._sdk')
    def test_cancel_sets_canceled(self, sdk_p):
        sdk = MagicMock()
        sdk.preapproval().update.return_value = {'status': 200, 'response': {}}
        sdk_p.return_value = sdk
        StoreSubscription.objects.create(
            store=self.store, plan='pro', status='active', mp_preapproval_id='PRE-1')
        r = self.client.post(f'/api/v1/stores/{self.store.slug}/subscription/cancel/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(StoreSubscription.objects.get(store=self.store).status, 'canceled')

    @patch('apps.stores.services.subscription_service.create_subscription')
    def test_change_plan_creates_new_preapproval(self, create_p):
        create_p.return_value = {'init_point': 'https://mp/new', 'preapproval_id': 'PRE-2'}
        StoreSubscription.objects.create(store=self.store, plan='starter', status='active')
        r = self.client.post(
            f'/api/v1/stores/{self.store.slug}/subscription/change-plan/',
            {'plan': 'pro'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['init_point'], 'https://mp/new')
