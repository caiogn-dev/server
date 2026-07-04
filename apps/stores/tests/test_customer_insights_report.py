"""
Testes do endpoint de insights de clientes (LTV, inatividade/churn, frequência).

Métricas lifetime vêm de StoreCustomer (identidade deduplicada por loja, stats
denormalizados). Os testes setam total_orders/total_spent/last_order_at direto,
então independem do gatilho de update_stats.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCustomer

User = get_user_model()

URL = '/api/v1/stores/reports/customers-insights/'


class CustomerInsightsReportTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', email='owner@x.com', password='x')
        self.store = Store.objects.create(name='Loja', slug='loja', owner=self.owner, status='active')
        now = timezone.now()

        def cust(tag, orders, spent, last_days_ago):
            u = User.objects.create_user(username=f'u_{tag}', email=f'{tag}@x.com', password='x')
            return StoreCustomer.objects.create(
                store=self.store, user=u, phone=f'6399900{tag}',
                total_orders=orders, total_spent=Decimal(spent),
                last_order_at=(now - timedelta(days=last_days_ago)) if last_days_ago is not None else None,
            )

        cust('a', 6, '600.00', 5)    # ativo, 6+
        cust('b', 3, '300.00', 45)   # em risco (30-60d), 3-5
        cust('c', 1, '50.00', 90)    # inativo, 1
        cust('d', 2, '120.00', 10)   # ativo, 2
        cust('e', 0, '0.00', None)   # nunca comprou -> inativo

        self.client.force_authenticate(self.owner)

    def _get(self, **params):
        params.setdefault('store', self.store.slug)
        return self.client.get(URL, params)

    def test_requires_store(self):
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, 400)

    def test_summary_activity_buckets(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200, resp.content)
        s = resp.data['summary']
        self.assertEqual(s['total_customers'], 5)
        self.assertEqual(s['active_30d'], 2)       # a (5d), d (10d)
        self.assertEqual(s['at_risk_30_60d'], 1)   # b (45d)
        self.assertEqual(s['inactive_60d'], 2)     # c (90d), e (null)
        self.assertEqual(s['churn_rate'], 40.0)    # 2/5

    def test_avg_ltv(self):
        resp = self._get()
        # (600+300+50+120+0)/5 = 214
        self.assertAlmostEqual(resp.data['summary']['avg_ltv'], 214.0, places=1)

    def test_frequency_distribution(self):
        resp = self._get()
        freq = {row['bucket']: row['count'] for row in resp.data['frequency']}
        self.assertEqual(freq['1 pedido'], 1)     # c
        self.assertEqual(freq['2 pedidos'], 1)    # d
        self.assertEqual(freq['3-5 pedidos'], 1)  # b
        self.assertEqual(freq['6+ pedidos'], 1)   # a

    def test_top_ltv_sorted_desc(self):
        resp = self._get()
        top = resp.data['top_ltv']
        self.assertGreaterEqual(len(top), 5)
        self.assertEqual(top[0]['total_spent'], 600.0)
        spent = [row['total_spent'] for row in top]
        self.assertEqual(spent, sorted(spent, reverse=True))

    def test_new_over_time_is_list(self):
        resp = self._get()
        self.assertIsInstance(resp.data['new_over_time'], list)

    def test_scoped_to_store(self):
        # cliente de OUTRA loja não entra na contagem
        other_owner = User.objects.create_user(username='o2', email='o2@x.com', password='x')
        other = Store.objects.create(name='Outra', slug='outra', owner=other_owner, status='active')
        u = User.objects.create_user(username='x1', email='x1@x.com', password='x')
        StoreCustomer.objects.create(store=other, user=u, total_orders=9, total_spent=Decimal('999'))
        resp = self._get()
        self.assertEqual(resp.data['summary']['total_customers'], 5)
