"""Aggregated dashboard metrics helper."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, Union

from django.db.models import Count, Sum, Q, F
from django.utils import timezone

from apps.stores import metrics
from apps.stores.models import Store, StoreOrder, StoreProduct


@dataclass
class DashboardSummary:
    today: Decimal
    week: Decimal
    month: Decimal
    today_orders: int
    week_orders: int
    month_orders: int
    yesterday_revenue: Decimal
    pending_orders: int
    low_stock_products: int


class DashboardStatsAggregator:
    """Service to build dashboard stats for a single store."""

    IN_PROGRESS_STATUSES = (
        StoreOrder.OrderStatus.PENDING,
        StoreOrder.OrderStatus.CONFIRMED,
        StoreOrder.OrderStatus.PROCESSING,
        StoreOrder.OrderStatus.PREPARING,
    )
    PAID_STATUSES = (StoreOrder.PaymentStatus.PAID,)

    def __init__(self, store: Store) -> None:
        self.store = store
        now = timezone.localtime(timezone.now())
        self.today = now.date()
        self.yesterday = self.today - timedelta(days=1)
        self.week_start = self.today - timedelta(days=7)
        self.month_start = self.today - timedelta(days=30)

    def build_payload(self) -> Dict[str, Any]:
        aggregates = self._aggregate_orders()
        summary = DashboardSummary(
            today=self._to_decimal(aggregates.get('today_revenue')),
            week=self._to_decimal(aggregates.get('week_revenue')),
            month=self._to_decimal(aggregates.get('month_revenue')),
            today_orders=int(aggregates.get('today_orders') or 0),
            week_orders=int(aggregates.get('week_orders') or 0),
            month_orders=int(aggregates.get('month_orders') or 0),
            yesterday_revenue=self._to_decimal(aggregates.get('yesterday_revenue')),
            pending_orders=int(aggregates.get('pending_orders') or 0),
            low_stock_products=self._calculate_low_stock_count(),
        )

        revenue_change = summary.today - summary.yesterday_revenue
        revenue_change_percent = (
            (revenue_change / summary.yesterday_revenue * Decimal('100'))
            if summary.yesterday_revenue > 0
            else Decimal('0')
        )

        return {
            'today': {
                'orders': summary.today_orders,
                'revenue': float(summary.today),
                # Campos antigos: o painel em produção lê estes. Mantidos.
                'revenue_change': float(revenue_change),
                'revenue_change_percent': float(revenue_change_percent),
                'comparativo': self._comparativo(metrics.hoje(), 'ontem'),
            },
            'week': {
                'orders': summary.week_orders,
                'revenue': float(summary.week),
                'avg_daily_revenue': self._avg_daily(summary.week, 7),
                'comparativo': self._comparativo(
                    metrics.ultimos_dias(8), '8 dias anteriores',
                ),
            },
            'month': {
                'orders': summary.month_orders,
                'revenue': float(summary.month),
                'avg_daily_revenue': self._avg_daily(summary.month, 30),
                'comparativo': self._comparativo(
                    metrics.ultimos_dias(31), '31 dias anteriores',
                ),
            },
            'alerts': {
                'pending_orders': summary.pending_orders,
                'low_stock_products': summary.low_stock_products,
            },
            'generated_at': timezone.localtime(timezone.now()).isoformat(),
        }

    def _aggregate_orders(self) -> Dict[str, Any]:
        """Contagem operacional vem do queryset cru; dinheiro vem do núcleo.

        Antes o dinheiro era filtrado por `paid_at__date`. Pedido pago em
        dinheiro na entrega ou com baixa manual não tem `paid_at` — sumia do
        faturamento em silêncio. O núcleo usa Coalesce(paid_at, created_at),
        então esses continuam contando, no dia certo.
        """
        queryset = StoreOrder.objects.filter(store=self.store, is_active=True)
        contagens = queryset.aggregate(
            today_orders=Count('id', filter=Q(created_at__date=self.today)),
            week_orders=Count('id', filter=Q(created_at__date__gte=self.week_start)),
            month_orders=Count('id', filter=Q(created_at__date__gte=self.month_start)),
            pending_orders=Count('id', filter=Q(status__in=self.IN_PROGRESS_STATUSES)),
        )

        def receita(janela):
            return metrics.totais(self.store, janela)['receita']

        contagens.update(
            today_revenue=receita(metrics.hoje()),
            yesterday_revenue=receita(metrics.ontem()),
            week_revenue=receita(metrics.ultimos_dias(8)),
            month_revenue=receita(metrics.ultimos_dias(31)),
        )
        return contagens

    def _comparativo(self, janela, rotulo: str) -> Dict[str, Any]:
        """Quanto este período variou contra o anterior, do mesmo tamanho.

        Número sozinho não informa: R$ 1.557 pode ser o melhor mês do ano ou
        metade do normal, e quem olha não tem como saber.

        `variacao_pct` vem None quando o período anterior foi ZERO. O código
        antigo devolvia 0% ali, que lê como "estável" — mas ontem zerado com
        R$ 500 hoje não é 0% de variação, é uma conta que não existe. Cabe à
        interface mostrar "sem base de comparação" em vez de um número falso.
        """
        cmp = metrics.comparar_periodo(self.store, janela)
        variacao = cmp['variacao_pct']
        return {
            'atual': float(cmp['atual']['receita']),
            'anterior': float(cmp['anterior']['receita']),
            'delta': float(cmp['delta']),
            'variacao_pct': round(float(variacao), 1) if variacao is not None else None,
            'pedidos_atual': cmp['atual']['pedidos'],
            'pedidos_anterior': cmp['anterior']['pedidos'],
            'rotulo': f'vs {rotulo}',
        }

    def _calculate_low_stock_count(self) -> int:
        return StoreProduct.objects.filter(
            store=self.store,
            status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=True,
            stock_quantity__lte=F('low_stock_threshold'),
        ).count()

    def _avg_daily(self, revenue: Decimal, days: int) -> float:
        if days <= 0:
            return 0.0
        return float((revenue / Decimal(days)).quantize(Decimal('0.01')))

    def _to_decimal(self, value: Union[Decimal, int, float, None]) -> Decimal:
        if value is None:
            return Decimal('0')
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
