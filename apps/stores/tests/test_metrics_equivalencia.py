"""As superfícies de faturamento têm que devolver o MESMO número.

Este é o teste que impede a fragmentação de voltar. Existiam quatro origens
independentes calculando "receita de hoje" — `/orders/stats/` (card da home),
`/core/dashboard-stats/` (KPI), `/core/dashboard/overview/` e
`/stores/reports/revenue/` — cada uma com o seu próprio filtro, o seu próprio
eixo de data e a sua própria conta de início do dia.

Elas divergiram de verdade em produção: em 06/ago/2026 o card da home agrupava
por `created_at` e as demais por `paid_at`, e o "hoje" nascia de
`timezone.now().replace(hour=0)` — 00:00 UTC, que é 21:00 de Brasília do dia
ANTERIOR. Depois das 21h o faturamento do dia inteiro sumia do painel.

Se alguém reintroduzir matemática própria em qualquer view, este teste quebra.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.stores.models import Store, StoreOrder

User = get_user_model()
SP = ZoneInfo('America/Sao_Paulo')


class ReceitaDeHojeEmTodasAsTelasTests(TestCase):
    """Mesmo dia, mesma loja, mesmo número — venha de onde vier."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono-equiv', password='x', email='dono-equiv@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Equivalencia', slug='loja-equivalencia',
            owner=self.owner, status='active',
        )
        self.hoje_local = datetime.now(SP).replace(
            hour=12, minute=0, second=0, microsecond=0,
        )

    def _pedido(self, total, *, quando=None, status=None, payment_status=None):
        quando = quando or self.hoje_local
        pedido = StoreOrder.objects.create(
            store=self.store, customer_name='Cliente',
            customer_phone='5563999990000', customer_email='c-equiv@real.com',
            subtotal=Decimal(total), total=Decimal(total),
            status=status or StoreOrder.OrderStatus.DELIVERED,
            payment_status=payment_status or StoreOrder.PaymentStatus.PAID,
        )
        StoreOrder.objects.filter(pk=pedido.pk).update(
            created_at=quando, paid_at=quando,
        )
        return pedido

    def _chamar(self, view, path_params=None, **params):
        rf = APIRequestFactory(SERVER_NAME='localhost')
        req = rf.get('/x', {'store': self.store.slug, **params})
        force_authenticate(req, user=self.owner)
        return view(req, **(path_params or {})).data

    def _receita_home(self):
        from apps.stores.api.views.order_views import StoreOrderViewSet
        d = self._chamar(StoreOrderViewSet.as_view({'get': 'stats'}))
        return Decimal(str(d['revenue']['today']))

    def _receita_kpi(self):
        from apps.core.dashboard_views import DashboardStatsView
        d = self._chamar(DashboardStatsView.as_view())
        return Decimal(str(d['today']['revenue']))

    def _receita_overview(self):
        from apps.core.dashboard_views import DashboardOverviewView
        d = self._chamar(DashboardOverviewView.as_view())
        return Decimal(str(d['orders']['revenue_today']))

    def _receita_relatorio(self):
        from apps.stores.api.export_views import RevenueReportView
        d = self._chamar(RevenueReportView.as_view())
        dia = self.hoje_local.date().isoformat()
        for ponto in d.get('data', []):
            if str(ponto.get('period')) == dia:
                return Decimal(str(ponto['total_revenue']))
        return Decimal('0')

    def _todas(self):
        return {
            'home': self._receita_home(),
            'kpi': self._receita_kpi(),
            'overview': self._receita_overview(),
            'relatorio': self._receita_relatorio(),
        }

    def test_venda_simples_bate_em_todas_as_telas(self):
        self._pedido('100.00')
        valores = self._todas()
        self.assertEqual(
            len(set(valores.values())), 1,
            f'telas divergiram: {valores}',
        )
        self.assertEqual(valores['home'], Decimal('100.00'))

    def test_pedido_cancelado_nao_conta_em_nenhuma_tela(self):
        self._pedido('100.00')
        # Cancelado depois de pago: o paid_at fica gravado e inflava a receita.
        self._pedido(
            '999.00',
            status=StoreOrder.OrderStatus.CANCELLED,
            payment_status=StoreOrder.PaymentStatus.PAID,
        )
        valores = self._todas()
        self.assertEqual(
            len(set(valores.values())), 1,
            f'telas divergiram com pedido cancelado: {valores}',
        )
        self.assertEqual(valores['home'], Decimal('100.00'))

    def test_pedido_nao_pago_nao_conta_em_nenhuma_tela(self):
        self._pedido('100.00')
        self._pedido(
            '555.00',
            status=StoreOrder.OrderStatus.CONFIRMED,
            payment_status=StoreOrder.PaymentStatus.PENDING,
        )
        valores = self._todas()
        self.assertEqual(len(set(valores.values())), 1, f'divergiram: {valores}')
        self.assertEqual(valores['home'], Decimal('100.00'))

    def test_venda_de_ontem_nao_vaza_para_hoje(self):
        self._pedido('100.00')
        self._pedido('777.00', quando=self.hoje_local - timedelta(days=1))
        valores = self._todas()
        self.assertEqual(len(set(valores.values())), 1, f'divergiram: {valores}')
        self.assertEqual(valores['home'], Decimal('100.00'))

    def test_venda_das_22h_conta_no_dia_certo(self):
        """O bug das 21h: a janela nascia de 00:00 UTC = 21:00 local de ontem.

        Uma venda às 22h é do MESMO dia local; com a janela errada ela era a
        única coisa que sobrava em "hoje" — o resto do dia sumia.
        """
        vinte_e_duas = self.hoje_local.replace(hour=22)
        # Só cria o pedido das 22h se ainda for o mesmo dia local; senão o
        # teste dependeria da hora em que roda.
        if vinte_e_duas > datetime.now(SP):
            self.skipTest('ainda não são 22h locais — cenário coberto pelo teste de fuso')
        self._pedido('100.00', quando=self.hoje_local.replace(hour=9))
        self._pedido('50.00', quando=vinte_e_duas)
        valores = self._todas()
        self.assertEqual(len(set(valores.values())), 1, f'divergiram: {valores}')
        self.assertEqual(valores['home'], Decimal('150.00'))
