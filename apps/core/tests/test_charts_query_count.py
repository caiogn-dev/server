"""DashboardChartsView: antes montava as séries diárias com um loop em Python
(days * 6 queries .count()/.aggregate()). days=30 explodia em ~63 queries.

Este teste prova que o número de queries é CONSTANTE — independe de `days` —
porque agora cada série é um único GROUP BY (TruncDate).
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder

User = get_user_model()


class ChartsQueryCountTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='ch-owner', email='ch@t.com', password='x'
        )
        self.store = Store.objects.create(
            name='Loja Charts', slug='loja-charts', owner=self.owner, status='active'
        )
        # alguns pedidos espalhados em dias diferentes p/ exercitar o GROUP BY
        now = timezone.now()
        for i in range(5):
            StoreOrder.objects.create(
                store=self.store,
                order_number=f'CH-{i}',
                status='paid',
                subtotal='10.00',
                total='10.00',
                created_at=now - timedelta(days=i),
                paid_at=now - timedelta(days=i),
            )
        self.client.force_authenticate(self.owner)

    def _count(self, days):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(
                f'/api/v1/core/dashboard/charts/?store={self.store.slug}&days={days}',
                SERVER_NAME='localhost',
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        return len(ctx.captured_queries), resp.data

    def test_bucketing_is_correct(self):
        """O GROUP BY tem que somar os 5 pedidos (R$50) nos buckets certos."""
        _, data = self._count(7)
        opd = data['orders_per_day']
        self.assertEqual(len(opd), 7)
        self.assertEqual(sum(d['count'] for d in opd), 5)
        self.assertEqual(sum(d['revenue'] for d in opd), 50.0)

    def test_query_count_is_flat_across_day_ranges(self):
        q7, _ = self._count(7)
        q30, _ = self._count(30)
        q90, _ = self._count(90)
        # O(1) em days: a janela de 90 dias (antes ~63 queries) não pode custar
        # mais que a de 7 dias. Pequenas variações vêm de quais buckets têm dados,
        # nunca do tamanho da janela — por isso travamos num teto pequeno e fixo.
        self.assertLessEqual(
            q90, q7 + 1,
            f'query count cresceu com days: 7d={q7} 30d={q30} 90d={q90}',
        )
        self.assertLess(
            max(q7, q30, q90), 12,
            f'esperado O(1) (~5-6 queries), veio {q7}/{q30}/{q90}',
        )
