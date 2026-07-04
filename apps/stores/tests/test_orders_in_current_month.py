"""Performance + correção: contagem de pedidos do mês (gate do plano Grátis)
roda em TODO checkout. Usava `created_at__year/__month` (EXTRACT) → não usa o
índice (store, created_at) e escala com o histórico da loja.

`billing.orders_in_current_month` passa a usar um range [início_do_mês,
início_do_próximo_mês), indexável, preservando a semântica de "mês" em fuso
LOCAL (o cliente vê o mês local, não UTC).

Cenários:
  1. Comportamento: conta só os pedidos do mês corrente (exclui mês passado e
     próximo mês) — invariante que NÃO pode regredir.
  2. Perf: a query não pode conter EXTRACT (senão ignora o índice).
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.stores import billing
from apps.stores.models import Store, StoreOrder

User = get_user_model()


class OrdersInCurrentMonthTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='oim-owner', email='o@t.com', password='x')
        self.store = Store.objects.create(
            owner=self.owner, name='Loja OIM', slug='loja-oim', status=Store.StoreStatus.ACTIVE,
        )

    def _order_at(self, dt):
        o = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='+55',
            subtotal=Decimal('1.00'), total=Decimal('1.00'), payment_status='pending',
        )
        # created_at é auto_now_add → precisa de .update() para backdate.
        StoreOrder.objects.filter(id=o.id).update(created_at=dt)
        return o

    def test_conta_apenas_o_mes_corrente(self):
        now = timezone.localtime(timezone.now())
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (month_start + timedelta(days=32)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0,
        )

        self._order_at(month_start + timedelta(days=1, hours=3))   # mês corrente
        self._order_at(now)                                        # mês corrente
        self._order_at(month_start - timedelta(hours=1))           # mês passado
        self._order_at(next_month + timedelta(hours=1))            # mês seguinte

        self.assertEqual(billing.orders_in_current_month(self.store), 2)

    def test_query_nao_usa_extract(self):
        with CaptureQueriesContext(connection) as ctx:
            billing.orders_in_current_month(self.store)
        sql = ' '.join(q['sql'].upper() for q in ctx.captured_queries)
        self.assertNotIn(
            'EXTRACT', sql,
            'a contagem mensal não pode usar EXTRACT (ignora o índice store+created_at)',
        )
