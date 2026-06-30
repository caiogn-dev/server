"""
Testes do catálogo de planos + helpers de feature-gate + endpoint público + modelo de assinatura.
(Sem enforcement automático nem cobrança — isso é wired depois.)
"""
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from apps.stores.models import Store, StoreSubscription
from apps.stores import billing


class BillingCatalogTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('o', 'o@x.com', 'x')

    def _store(self, plan='starter'):
        return Store.objects.create(name='L', slug=f'l-{plan}', owner=self.owner,
                                    status=Store.StoreStatus.ACTIVE, plan=plan)

    def test_catalog_tem_tres_planos(self):
        self.assertEqual(set(billing.PLAN_CATALOG.keys()), {'free', 'starter', 'pro', 'premium'})

    def test_plan_allows_por_tier(self):
        starter = self._store('starter')
        pro = self._store('pro')
        premium = self._store('premium')
        self.assertFalse(billing.plan_allows(starter, 'custom_domain'))
        self.assertFalse(billing.plan_allows(pro, 'custom_domain'))
        self.assertTrue(billing.plan_allows(pro, 'whatsapp_bot'))
        self.assertFalse(billing.plan_allows(pro, 'ai_agent'))
        self.assertTrue(billing.plan_allows(premium, 'custom_domain'))
        self.assertTrue(billing.plan_allows(premium, 'ai_agent'))

    def test_product_limit(self):
        free = self._store('free')
        starter = self._store('starter')
        pro = self._store('pro')
        # free tem cap 40
        self.assertTrue(billing.within_product_limit(free, 39))
        self.assertFalse(billing.within_product_limit(free, 40))
        # starter e pro são ilimitados
        self.assertTrue(billing.within_product_limit(starter, 9999))
        self.assertTrue(billing.within_product_limit(pro, 9999))

    def test_loja_exempt_ignora_limites(self):
        store = self._store('starter')
        store.billing_exempt = True
        store.save()
        # exempt: sem limite de produto e tudo liberado
        self.assertTrue(billing.within_product_limit(store, 9999))
        self.assertTrue(billing.plan_allows(store, 'custom_domain'))
        self.assertTrue(billing.plan_allows(store, 'ai_agent'))
        self.assertTrue(billing.is_billing_exempt(store))

    def test_get_plan_fallback(self):
        self.assertEqual(billing.get_plan('inexistente')['key'], 'free')

    def test_subscription_model(self):
        store = self._store('pro')
        sub = StoreSubscription.objects.create(store=store, plan='pro')
        self.assertEqual(sub.status, StoreSubscription.Status.TRIALING)
        self.assertEqual(store.subscription, sub)


class PublicPlansEndpointTestCase(TestCase):
    def test_endpoint_retorna_planos(self):
        from django.core.cache import cache
        cache.clear()
        resp = APIClient().get('/api/v1/public/plans/')
        self.assertEqual(resp.status_code, 200)
        plans = resp.json()['plans']
        self.assertEqual(len(plans), 4)
        keys = {p['key'] for p in plans}
        self.assertEqual(keys, {'free', 'starter', 'pro', 'premium'})
        free = next(p for p in plans if p['key'] == 'free')
        self.assertEqual(free['limits']['max_products'], 40)
        starter = next(p for p in plans if p['key'] == 'starter')
        self.assertIsNone(starter['limits']['max_products'])
        self.assertIn('monthly_price', starter)
        self.assertIn('setup_fee', starter)
