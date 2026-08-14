from django.test import TestCase
from apps.stores import billing


class PlanCatalogTest(TestCase):
    def test_quatro_planos_com_precos_aprovados(self):
        self.assertEqual(float(billing.get_plan('free')['monthly_price']), 0.0)
        self.assertEqual(float(billing.get_plan('starter')['monthly_price']), 179.00)
        self.assertEqual(float(billing.get_plan('pro')['monthly_price']), 249.00)
        self.assertEqual(float(billing.get_plan('premium')['monthly_price']), 549.00)
        self.assertEqual(billing.get_plan('starter')['name'], 'Loja')
        self.assertEqual(billing.get_plan('free')['name'], 'Grátis')

    def test_implantacao_cobrada_em_todo_plano_pago(self):
        # Go-live: a implantação de R$ 1.200 deixou de ser exclusiva do topo.
        # Era o item que mais custava e era dado de graça ("monto seu cardápio").
        self.assertFalse(billing.charges_setup_fee('free'))
        self.assertTrue(billing.charges_setup_fee('starter'))
        self.assertTrue(billing.charges_setup_fee('pro'))
        self.assertTrue(billing.charges_setup_fee('premium'))

    def test_default_plan_e_free(self):
        self.assertEqual(billing.DEFAULT_PLAN, 'free')

    def test_limite_de_pedidos_do_free(self):
        self.assertEqual(billing.plan_limits('free')['max_orders_per_month'], 15)
        self.assertIsNone(billing.plan_limits('starter')['max_orders_per_month'])

    def test_features_por_tier(self):
        self.assertFalse(billing.plan_allows('free', 'whatsapp_bot'))
        self.assertTrue(billing.plan_allows('pro', 'whatsapp_bot'))
        self.assertFalse(billing.plan_allows('pro', 'ai_agent'))
        self.assertTrue(billing.plan_allows('premium', 'ai_agent'))
        self.assertTrue(billing.plan_allows('premium', 'custom_domain'))
        # Domínio próprio entra junto com o bot ("Loja + WhatsApp"), não só na Rede.
        self.assertTrue(billing.plan_allows('pro', 'custom_domain'))
        self.assertFalse(billing.plan_allows('starter', 'custom_domain'))


class OrderLimitTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from apps.stores.models import Store
        self.owner = User.objects.create_user('o-ol', 'o-ol@x.com', 'x')
        self.store = Store.objects.create(name='L', slug='l-ol', owner=self.owner, plan='free')

    def test_free_bloqueia_no_limite(self):
        self.assertTrue(billing.within_order_limit(self.store, 14))
        self.assertFalse(billing.within_order_limit(self.store, 15))

    def test_plano_pago_sem_limite(self):
        self.store.plan = 'starter'
        self.assertTrue(billing.within_order_limit(self.store, 9999))

    def test_loja_isenta_passa(self):
        self.store.billing_exempt = True
        self.assertTrue(billing.within_order_limit(self.store, 9999))
