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

    def test_subscription_detail_expoe_downgraded_flag(self):
        StoreSubscription.objects.create(
            store=self.store, plan='pro', downgraded_for_nonpayment=True)
        r = self.client.get(f'/api/v1/stores/{self.store.slug}/subscription/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['downgraded_for_nonpayment'])

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

    def test_non_owner_receives_403(self):
        outro = User.objects.create_user(username='outro', email='outro@x.com', password='x')
        client2 = APIClient()
        client2.force_authenticate(outro)
        r = client2.get(f'/api/v1/stores/{self.store.slug}/subscription/')
        self.assertEqual(r.status_code, 403)

    @patch('apps.stores.services.subscription_service.create_subscription')
    def test_change_plan_creates_new_preapproval(self, create_p):
        create_p.return_value = {'init_point': 'https://mp/new', 'preapproval_id': 'PRE-2'}
        StoreSubscription.objects.create(store=self.store, plan='starter', status='active')
        r = self.client.post(
            f'/api/v1/stores/{self.store.slug}/subscription/change-plan/',
            {'plan': 'pro'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['init_point'], 'https://mp/new')

    def test_cancel_without_subscription_returns_400(self):
        r = self.client.post(f'/api/v1/stores/{self.store.slug}/subscription/cancel/')
        self.assertEqual(r.status_code, 400)

    def test_change_plan_invalid_plan_returns_400(self):
        r = self.client.post(
            f'/api/v1/stores/{self.store.slug}/subscription/change-plan/',
            {'plan': 'inexistente'}, format='json')
        self.assertEqual(r.status_code, 400)

    @patch('apps.stores.services.subscription_service._sdk')
    def test_exempt_store_cancel_blocked_without_touching_mp(self, sdk_p):
        # Loja isenta NÃO pode ter o preapproval cancelado no MP nem o plano
        # resetado: cancel deve recusar (400) ANTES de qualquer chamada ao MP.
        sdk = MagicMock()
        sdk_p.return_value = sdk
        self.store.billing_exempt = True
        self.store.plan = 'pro'
        self.store.save(update_fields=['billing_exempt', 'plan'])
        StoreSubscription.objects.create(
            store=self.store, plan='pro', status='active', mp_preapproval_id='PRE-EXEMPT')
        r = self.client.post(f'/api/v1/stores/{self.store.slug}/subscription/cancel/')
        self.assertEqual(r.status_code, 400)
        sdk.preapproval().update.assert_not_called()
        sub = StoreSubscription.objects.get(store=self.store)
        self.assertEqual(sub.status, 'active')
        self.store.refresh_from_db()
        self.assertEqual(self.store.plan, 'pro')

    @patch('apps.stores.services.subscription_service._sdk')
    def test_exempt_store_change_plan_blocked_without_canceling(self, sdk_p):
        # Loja isenta NÃO pode ser afetada: change-plan deve recusar (400) ANTES
        # de cancelar qualquer preapproval no MP, sem corromper o estado.
        sdk = MagicMock()
        sdk_p.return_value = sdk
        self.store.billing_exempt = True
        self.store.save(update_fields=['billing_exempt'])
        StoreSubscription.objects.create(
            store=self.store, plan='pro', status='active', mp_preapproval_id='PRE-X')
        r = self.client.post(
            f'/api/v1/stores/{self.store.slug}/subscription/change-plan/',
            {'plan': 'premium'}, format='json')
        self.assertEqual(r.status_code, 400)
        sdk.preapproval().update.assert_not_called()
        self.assertEqual(
            StoreSubscription.objects.get(store=self.store).status, 'active')
