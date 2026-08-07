"""Todo KPI de dinheiro carrega o comparativo com o período anterior.

Número sozinho não informa. "R$ 1.557" pode ser o melhor mês do ano ou metade
do normal — quem olha não tem como saber. O painel do Prefiro Delivery põe
`-26% vs ontem` em toda métrica, e é isso que transforma o card em decisão.

O núcleo já tinha `comparar_periodo()` pronto e sem nenhum uso. O agregador
comparava só HOJE contra ONTEM, e mesmo assim errado: quando ontem foi zero,
devolvia `0%` — que lê como "estável" quando na verdade é "não dá para
comparar". Ontem zerado com R$ 500 hoje não é 0% de variação.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.services.dashboard_stats import DashboardStatsAggregator
from apps.stores import metrics
from apps.stores.models import Store, StoreOrder

User = get_user_model()


class ComparativoDosKpisTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono-cmp', password='x', email='dono-cmp@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Comparativo', slug='loja-comparativo',
            owner=self.owner, status='active',
        )
        self.hoje = metrics.hoje_local()

    def _pedido(self, total, dia):
        quando = timezone.make_aware(
            datetime.combine(dia, datetime.min.time().replace(hour=12)),
            timezone.get_current_timezone(),
        )
        p = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='5563900000099',
            customer_email='c-cmp@real.com',
            subtotal=Decimal(total), total=Decimal(total),
            status=StoreOrder.OrderStatus.DELIVERED,
            payment_status=StoreOrder.PaymentStatus.PAID,
        )
        StoreOrder.objects.filter(pk=p.pk).update(created_at=quando, paid_at=quando)
        return p

    def _payload(self):
        return DashboardStatsAggregator(self.store).build_payload()

    def test_hoje_traz_comparativo_com_ontem(self):
        self._pedido('100.00', self.hoje)
        self._pedido('50.00', self.hoje - timedelta(days=1))

        cmp = self._payload()['today']['comparativo']

        self.assertEqual(Decimal(str(cmp['anterior'])), Decimal('50.00'))
        self.assertEqual(Decimal(str(cmp['delta'])), Decimal('50.00'))
        self.assertEqual(round(cmp['variacao_pct']), 100)

    def test_semana_e_mes_tambem_comparam(self):
        self._pedido('100.00', self.hoje)
        for w in ('week', 'month'):
            self.assertIn(
                'comparativo', self._payload()[w],
                f'o card de {w} mostra um número sem referência nenhuma',
            )

    def test_periodo_anterior_zerado_nao_vira_zero_por_cento(self):
        """0% lê como 'estável'. Sem base de comparação, o honesto é None."""
        self._pedido('500.00', self.hoje)

        cmp = self._payload()['today']['comparativo']

        self.assertIsNone(
            cmp['variacao_pct'],
            'ontem foi zero e hoje R$ 500 — isso não é 0% de variação',
        )
        self.assertEqual(Decimal(str(cmp['delta'])), Decimal('500.00'))

    def test_queda_vem_negativa(self):
        self._pedido('30.00', self.hoje)
        self._pedido('100.00', self.hoje - timedelta(days=1))

        cmp = self._payload()['today']['comparativo']

        self.assertLess(cmp['variacao_pct'], 0)
        self.assertEqual(Decimal(str(cmp['delta'])), Decimal('-70.00'))

    def test_campos_antigos_continuam_existindo(self):
        """O painel em produção lê `revenue_change`; não pode quebrar."""
        self._pedido('100.00', self.hoje)
        hoje = self._payload()['today']
        for campo in ('orders', 'revenue', 'revenue_change', 'revenue_change_percent'):
            self.assertIn(campo, hoje)
