"""
Endpoints de analytics/BI — Fase 1 do plano de relatórios
(docs/PLANO_RELATORIOS_BI_2026-07-31.md).

Todos usam apenas campos que já existem: nenhuma migração. Receita segue a
regra canônica payment_status='paid' (mesma do RevenueReportView).
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay, TruncDate
from django.utils import timezone
from rest_framework.response import Response

from itertools import combinations

from apps.automation.models import CustomerSession
from ..models import (
    StoreCashMovement,
    StoreCashSession,
    StoreCoupon,
    StoreCustomer,
    StoreOrder,
    StoreOrderItem,
    StorePayment,
    StoreProduct,
    StoreReview,
)
from .export_views import BaseExportView


class BaseAnalyticsView(BaseExportView):
    """Resolve loja + período e o queryset canônico de pedidos pagos.

    Relatórios avançados são feature Pro/Premium (`advanced_reports`);
    subclasses liberadas para todos os planos zeram `plan_feature`.
    """

    plan_feature = 'advanced_reports'

    def resolve(self, request):
        store = self.get_store(request)
        if not store:
            return None, None, None, Response({'error': 'Store parameter required'}, status=400)
        if self.plan_feature:
            from apps.stores.billing import advanced_reports_allowed
            if not advanced_reports_allowed(store):
                return None, None, None, Response(
                    {
                        'error': 'Relatórios avançados são do plano Pro. Faça upgrade para liberar.',
                        'code': 'plan_upgrade_required',
                        'feature': self.plan_feature,
                    },
                    status=403,
                )
        start, end = self.get_date_range(request)
        return store, start, end, None

    def paid_orders(self, store, start, end):
        """Queryset canônico de faturamento — núcleo em `apps/stores/metrics/`.

        Ponto único de entrada dos 20 relatórios desta camada: eles compõem em
        cima deste queryset. Consertar aqui conserta todos de uma vez — e
        introduzir divergência aqui a espalha para todos.

        Duas correções em cima do que existia antes:

        - filtrava só `payment_status='paid'`, contando venda cancelada e
          pedido de teste do dono como receita;
        - recortava o período por `created_at`, enquanto o resto do painel usa
          a data do PAGAMENTO. Pedido feito 31/07 23h40 e pago 01/08 00h05
          caía em meses diferentes conforme a tela, e o BI não conciliava com
          o extrato do Mercado Pago.
        """
        from apps.stores import metrics

        return metrics.pedidos_de_receita(loja=store, inicio=start, fim=end)


def _round2(value):
    return round(float(value or 0), 2)


def _p90(sorted_values):
    if not sorted_values:
        return None
    idx = int(round(0.9 * (len(sorted_values) - 1)))
    return sorted_values[idx]


class HeatmapReportView(BaseAnalyticsView):
    """Grade dia-da-semana × hora (horários de pico) em fuso local."""

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        tz = timezone.get_current_timezone()
        rows = (
            self.paid_orders(store, start, end)
            .annotate(
                wd=ExtractIsoWeekDay('created_at', tzinfo=tz),
                hr=ExtractHour('created_at', tzinfo=tz),
            )
            .values('wd', 'hr')
            .annotate(orders=Count('id'), revenue=Sum('total'))
            .order_by('wd', 'hr')
        )
        cells = [
            {
                # ISO: 1=segunda…7=domingo → 0=segunda…6=domingo (weekday())
                'weekday': row['wd'] - 1,
                'hour': row['hr'],
                'orders': row['orders'],
                'revenue': _round2(row['revenue']),
            }
            for row in rows
        ]
        peak = max(cells, key=lambda c: c['orders'], default=None)
        return Response({'cells': cells, 'peak': peak})


class AbcReportView(BaseAnalyticsView):
    """Curva ABC de produtos por receita (A ≤80%, B ≤95%, C resto)."""

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        rows = list(
            StoreOrderItem.objects.filter(
                order__in=self.paid_orders(store, start, end)
            )
            .values('product_name')
            .annotate(quantity=Sum('quantity'), revenue=Sum('subtotal'), order_count=Count('order', distinct=True))
            .order_by('-revenue')
        )
        total_revenue = sum((r['revenue'] or Decimal('0')) for r in rows) or Decimal('0')
        products = []
        cumulative = Decimal('0')
        for r in rows:
            revenue = r['revenue'] or Decimal('0')
            cumulative += revenue
            pct = float(revenue / total_revenue * 100) if total_revenue else 0.0
            cum_pct = float(cumulative / total_revenue * 100) if total_revenue else 0.0
            products.append({
                'product_name': r['product_name'],
                'quantity': r['quantity'],
                'revenue': _round2(revenue),
                'order_count': r['order_count'],
                'revenue_pct': round(pct, 2),
                'cumulative_pct': round(cum_pct, 2),
                'abc_class': 'A' if cum_pct <= 80 else ('B' if cum_pct <= 95 else 'C'),
            })
        summary = {
            'total_revenue': _round2(total_revenue),
            'a_count': sum(1 for p in products if p['abc_class'] == 'A'),
            'b_count': sum(1 for p in products if p['abc_class'] == 'B'),
            'c_count': sum(1 for p in products if p['abc_class'] == 'C'),
        }
        return Response({'products': products, 'summary': summary})


def _map_channel(source):
    if not source:
        return 'web'
    if source.startswith('whatsapp'):
        return 'bot'
    if source.startswith('dashboard') or source == 'pdv':
        return 'pdv'
    return 'web'


class ChannelsReportView(BaseAnalyticsView):
    """Mix por canal (bot/web/PDV), forma de pagamento e entrega/retirada."""

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        qs = self.paid_orders(store, start, end)

        # Coluna `source` (BI Fase 2) — indexada; '' só em legado sem backfill
        by_channel = defaultdict(lambda: {'orders': 0, 'revenue': Decimal('0')})
        for source, metadata_source, total in qs.values_list('source', 'metadata__source', 'total'):
            channel = source or _map_channel(metadata_source)
            if channel == 'whatsapp':
                channel = 'bot'  # nome do canal na API/painel
            bucket = by_channel[channel]
            bucket['orders'] += 1
            bucket['revenue'] += total or Decimal('0')

        def channel_rows():
            rows = []
            for channel, agg in sorted(by_channel.items(), key=lambda kv: -kv[1]['revenue']):
                rows.append({
                    'channel': channel,
                    'orders': agg['orders'],
                    'revenue': _round2(agg['revenue']),
                    'avg_ticket': _round2(agg['revenue'] / agg['orders']) if agg['orders'] else 0,
                })
            return rows

        def dimension(field, label):
            # `qs` e paid_orders() — ja passou pelo nucleo la em cima.
            rows = (
                qs.values(field)
                .annotate(orders=Count('id'), revenue=Sum('total'), avg_ticket=Avg('total'))
                .order_by('-revenue')
            )
            return [
                {
                    label: r[field] or 'nao_informado',
                    'orders': r['orders'],
                    'revenue': _round2(r['revenue']),
                    'avg_ticket': _round2(r['avg_ticket']),
                }
                for r in rows
            ]

        return Response({
            'by_source': channel_rows(),
            'by_payment_method': dimension('payment_method', 'payment_method'),
            'by_delivery_method': dimension('delivery_method', 'delivery_method'),
        })


DISTANCE_BANDS = ((0, 2, '0-2 km'), (2, 4, '2-4 km'), (4, 6, '4-6 km'), (6, None, '6+ km'))
MAX_GEO_POINTS = 500


class GeographyReportView(BaseAnalyticsView):
    """Bairros, anéis de distância, pontos lat/lng e zonas de entrega."""

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        orders = self.paid_orders(store, start, end).filter(delivery_method='delivery')

        hoods = defaultdict(lambda: {'orders': 0, 'revenue': Decimal('0'), 'city': ''})
        bands = defaultdict(lambda: {'orders': 0, 'revenue': Decimal('0')})
        zones = defaultdict(lambda: {'orders': 0, 'revenue': Decimal('0')})
        points = []

        point_fields = orders.values_list(
            'delivery_address', 'metadata', 'total', 'order_number', 'customer_name', 'created_at', 'id',
            'delivery_lat', 'delivery_lng',
        )
        for address, metadata, total, order_number, customer_name, created_at, order_id, col_lat, col_lng in point_fields:
            address = address or {}
            metadata = metadata or {}
            total = total or Decimal('0')

            raw_hood = (address.get('neighborhood') or '').strip()
            if raw_hood:
                key = raw_hood.title()
                hoods[key]['orders'] += 1
                hoods[key]['revenue'] += total
                hoods[key]['city'] = (address.get('city') or '').strip() or hoods[key]['city']

            quote = metadata.get('delivery_quote') or {}
            distance = quote.get('distance_km')
            if isinstance(distance, (int, float)):
                for low, high, label in DISTANCE_BANDS:
                    if distance >= low and (high is None or distance < high):
                        bands[label]['orders'] += 1
                        bands[label]['revenue'] += total
                        break

            zone_name = (quote.get('zone_name') or '').strip()
            if zone_name:
                zones[zone_name]['orders'] += 1
                zones[zone_name]['revenue'] += total

            # Colunas denormalizadas primeiro (BI Fase 2); JSON como legado
            if col_lat is not None and col_lng is not None:
                lat, lng = float(col_lat), float(col_lng)
            else:
                lat, lng = address.get('lat'), address.get('lng')
            if isinstance(lat, (int, float)) and isinstance(lng, (int, float)) and len(points) < MAX_GEO_POINTS:
                points.append({
                    'lat': lat,
                    'lng': lng,
                    'total': _round2(total),
                    'order_id': str(order_id),
                    'order_number': order_number,
                    'customer_name': customer_name or '',
                    'neighborhood': (address.get('neighborhood') or '').strip().title(),
                    'created_at': created_at,
                })

        def rows(mapping, key_label, extra=None):
            out = []
            for name, agg in sorted(mapping.items(), key=lambda kv: -kv[1]['revenue']):
                row = {key_label: name, 'orders': agg['orders'], 'revenue': _round2(agg['revenue'])}
                if extra:
                    row.update({k: agg[k] for k in extra})
                out.append(row)
            return out

        band_order = [label for _, _, label in DISTANCE_BANDS]
        distance_rows = [
            {'band': label, 'orders': bands[label]['orders'], 'revenue': _round2(bands[label]['revenue'])}
            for label in band_order
            if label in bands
        ]
        return Response({
            'neighborhoods': rows(hoods, 'name', extra=['city']),
            'distance_bands': distance_rows,
            'points': points,
            'zones': rows(zones, 'name'),
        })


SLA_STAGES = (
    ('confirmacao', 'created_at', 'confirmed_at'),
    ('preparo', 'confirmed_at', 'ready_at'),
    ('entrega', 'out_for_delivery_at', 'delivered_at'),
    ('total', 'created_at', None),  # fim = delivered_at ou picked_up_at
)


class SlaReportView(BaseAnalyticsView):
    """Tempo médio e p90 por etapa do pedido (timestamps de ciclo de vida)."""

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        fields = ['created_at', 'confirmed_at', 'ready_at', 'out_for_delivery_at', 'delivered_at', 'picked_up_at', 'delivery_method']
        rows = list(
            StoreOrder.objects.filter(store=store, created_at__date__range=(start, end))
            .exclude(status__in=('cancelled', 'failed', 'refunded'))
            .values(*fields)
        )
        durations = defaultdict(list)
        for row in rows:
            for stage, start_field, end_field in SLA_STAGES:
                begin = row[start_field]
                finish = row[end_field] if end_field else (row['delivered_at'] or row['picked_up_at'])
                if begin and finish and finish >= begin:
                    durations[stage].append((finish - begin).total_seconds() / 60)

        stages = []
        for stage, _, _ in SLA_STAGES:
            values = sorted(durations[stage])
            stages.append({
                'stage': stage,
                'count': len(values),
                'avg_minutes': round(sum(values) / len(values), 1) if values else None,
                'p90_minutes': round(_p90(values), 1) if values else None,
            })
        return Response({'stages': stages})


class FinanceReportView(BaseAnalyticsView):
    """Bruto × taxa de gateway × líquido, incluindo o que não passou por gateway.

    Esta tela partia só de `StorePayment`, que existe apenas quando houve
    cobrança por gateway. Venda em DINHEIRO e baixa manual não geram esse
    registro — e sumiam do relatório financeiro.

    Em 07/ago a Cê Saladas tinha 5 vendas assim (R$ 297,56): o BI mostrava
    R$ 1.508,49 enquanto o relatório de faturamento mostrava R$ 1.557,04, e o
    dono não tinha como saber de onde vinha a diferença. Um card chamado
    "bruto" que ignora o dinheiro do caixa não é bruto.

    Agora o dinheiro sem gateway entra como uma linha própria, com taxa zero —
    o total concilia com o resto do painel e a quebra por taxa continua exata.
    """

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        # Parte dos PEDIDOS DE RECEITA e busca os pagamentos deles — não o
        # contrário. Filtrar StorePayment por conta própria trazia cobrança de
        # pedido cancelado, cobrança avulsa de assinatura e pagamento fora da
        # janela: o "bruto" estourava o faturamento real.
        pedidos = self.paid_orders(store, start, end)
        payments = StorePayment.objects.filter(
            order__in=pedidos, status='completed',
        )
        sem_gateway = self._receita_sem_gateway(store, start, end)
        summary = payments.aggregate(
            gross=Sum('amount'), fees=Sum('fee'), net=Sum('net_amount'), refunded=Sum('refunded_amount'),
        )
        # Sem gateway não há taxa: entra igual no bruto e no líquido.
        summary['gross'] = (summary['gross'] or 0) + sem_gateway['total']
        summary['net'] = (summary['net'] or 0) + sem_gateway['total']

        def group(field, label):
            rows = (
                payments.values(field)
                .annotate(gross=Sum('amount'), fees=Sum('fee'), net=Sum('net_amount'), count=Count('id'))
                .order_by('-gross')
            )
            return [
                {
                    label: r[field] or 'nao_informado',
                    'count': r['count'],
                    'gross': _round2(r['gross']),
                    'fees': _round2(r['fees']),
                    'net': _round2(r['net']),
                }
                for r in rows
            ]

        # Timeline = quando o dinheiro entrou.
        #
        # Dois cuidados que faltavam:
        #
        # 1. EIXO — usa o `paid_at` do PRÓPRIO pagamento, que é a data que o
        #    Mercado Pago carimba. É essa que aparece no extrato, e é por ela
        #    que se confere repasse. Cai para a data do pedido quando o
        #    gateway não informou.
        # 2. O dinheiro SEM gateway não entrava aqui. O total dizia
        #    R$ 1.557,04 e a soma do gráfico dava R$ 1.259,48 — o gráfico
        #    mentia sobre o próprio card que estava em cima dele.
        from django.db.models.functions import Coalesce as _Coalesce

        from apps.stores.metrics import eixo_de_receita as _eixo_de_receita

        por_dia = defaultdict(lambda: {'gross': Decimal('0'), 'net': Decimal('0')})
        for r in (
            payments.annotate(
                day=TruncDate(_Coalesce('paid_at', 'order__paid_at', 'order__created_at'))
            )
            .values('day')
            .annotate(gross=Sum('amount'), net=Sum('net_amount'))
        ):
            bucket = por_dia[r['day']]
            bucket['gross'] += r['gross'] or Decimal('0')
            bucket['net'] += r['net'] or Decimal('0')

        for r in (
            sem_gateway['queryset']
            .annotate(day=TruncDate(_eixo_de_receita()))
            .values('day')
            .annotate(total=Sum('total'))
        ):
            bucket = por_dia[r['day']]
            # Sem gateway não há taxa: entra igual no bruto e no líquido.
            bucket['gross'] += r['total'] or Decimal('0')
            bucket['net'] += r['total'] or Decimal('0')

        timeline = [
            {'date': dia, 'gross': _round2(v['gross']), 'net': _round2(v['net'])}
            for dia, v in sorted(por_dia.items(), key=lambda kv: (kv[0] is None, kv[0]))
        ]
        linha_sem_gateway = {
            'count': sem_gateway['pedidos'],
            'gross': _round2(sem_gateway['total']),
            'fees': 0.0,
            'net': _round2(sem_gateway['total']),
        }
        por_gateway = group('gateway__name', 'gateway')
        por_metodo = group('payment_method', 'payment_method')
        if sem_gateway['pedidos']:
            por_gateway.append({'gateway': 'sem gateway (dinheiro/baixa manual)', **linha_sem_gateway})
            por_metodo.append({'payment_method': 'sem gateway (dinheiro/baixa manual)', **linha_sem_gateway})

        return Response({
            'summary': {k: _round2(v) for k, v in summary.items()},
            'by_gateway': por_gateway,
            'by_method': por_metodo,
            'timeline': timeline,
        })

    @staticmethod
    def _receita_sem_gateway(store, start, end):
        """Receita real que NÃO gerou registro de pagamento.

        Dinheiro na entrega e baixa manual no painel: o pedido é receita
        legítima (passa pelo núcleo), mas nunca houve cobrança por gateway.
        """
        from django.db.models import Sum as _Sum

        from apps.stores import metrics

        qs = metrics.pedidos_de_receita(
            loja=store, inicio=start, fim=end,
        ).filter(payments__isnull=True)
        agg = qs.aggregate(total=_Sum('total'), pedidos=Count('id'))
        return {
            'total': agg['total'] or 0,
            'pedidos': agg['pedidos'] or 0,
            'queryset': qs,
        }


RFM_SEGMENT_LABELS = {
    'campeoes': 'Campeões',
    'leais': 'Leais',
    'novos': 'Novos',
    'em_risco': 'Em risco',
    'perdidos': 'Perdidos',
    'sem_pedido': 'Sem pedido',
}
INACTIVE_DAYS = 60
INACTIVE_LIMIT = 100


def _rfm_segment(recency_days, frequency):
    if not frequency or recency_days is None:
        return 'sem_pedido'
    if recency_days <= 30 and frequency >= 4:
        return 'campeoes'
    if frequency == 1:
        return 'novos' if recency_days <= 60 else 'perdidos'
    if recency_days <= 60:
        return 'leais'
    if recency_days <= 120:
        return 'em_risco'
    return 'perdidos'


class RfmReportView(BaseAnalyticsView):
    """Segmentação RFM + lista acionável de inativos (reengajamento)."""

    @staticmethod
    def _cadence_by_phone(store):
        """Gap médio entre pedidos (dias) por telefone — só clientes 2+ pedidos."""
        orders_by_phone = defaultdict(list)
        # metrics-ok: `payment_status='paid'` aqui e proxy de "pedido real do
        # cliente" para medir RECORRENCIA — nao ha soma de dinheiro nenhuma.
        pairs = StoreOrder.objects.filter(store=store, payment_status='paid').exclude(
            customer_phone=''
        ).values_list('customer_phone', 'created_at')
        for phone, created in pairs:
            orders_by_phone[phone.strip()].append(created)
        cadence = {}
        for phone, dates in orders_by_phone.items():
            if len(dates) < 2:
                continue
            dates.sort()
            gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
            cadence[phone] = max(1, round(sum(gaps) / len(gaps)))
        return cadence

    def get(self, request):
        store, _, _, err = self.resolve(request)
        if err:
            return err
        now = timezone.now()
        cadence = self._cadence_by_phone(store)
        segments = defaultdict(lambda: {'count': 0, 'revenue': Decimal('0')})
        inactive = []
        top_customers = []
        customers = StoreCustomer.objects.filter(store=store).values(
            'unified_user__name', 'user__first_name', 'phone', 'whatsapp',
            'total_orders', 'total_spent', 'last_order_at',
        )
        for c in customers:
            days = (now - c['last_order_at']).days if c['last_order_at'] else None
            segment = _rfm_segment(days, c['total_orders'])
            segments[segment]['count'] += 1
            segments[segment]['revenue'] += c['total_spent'] or Decimal('0')
            if c['total_orders']:
                phone_key = (c['whatsapp'] or c['phone'] or '').strip()
                spent = c['total_spent'] or Decimal('0')
                top_customers.append({
                    'name': c['unified_user__name'] or c['user__first_name'] or '',
                    'phone': phone_key,
                    'segment': segment,
                    'total_orders': c['total_orders'],
                    'total_spent': _round2(spent),
                    'avg_ticket': _round2(spent / c['total_orders']),
                    'typical_gap_days': cadence.get(phone_key),
                    'days_since': days,
                })
            if c['total_orders'] and days is not None and days >= INACTIVE_DAYS:
                phone = (c['whatsapp'] or c['phone'] or '').strip()
                typical_gap = cadence.get(phone)
                inactive.append({
                    'name': c['unified_user__name'] or c['user__first_name'] or '',
                    'phone': phone,
                    'days_since': days,
                    'total_orders': c['total_orders'],
                    'total_spent': _round2(c['total_spent']),
                    # cadência: "pedia a cada Xd" e quantas vezes o gap normal
                    # já estourou — quanto maior, mais urgente o resgate
                    'typical_gap_days': typical_gap,
                    'overdue_factor': round(days / typical_gap, 1) if typical_gap else None,
                })
        inactive.sort(key=lambda c: -c['total_spent'])
        cadence_values = sorted(cadence.values())
        avg_cadence = round(sum(cadence_values) / len(cadence_values)) if cadence_values else None
        segment_rows = [
            {
                'segment': key,
                'label': RFM_SEGMENT_LABELS[key],
                'count': agg['count'],
                'revenue': _round2(agg['revenue']),
            }
            for key, agg in segments.items()
        ]
        segment_rows.sort(key=lambda r: -r['revenue'])
        top_customers.sort(key=lambda c: -c['total_spent'])
        return Response({
            'segments': segment_rows,
            'customers': top_customers[:50],
            'inactive': inactive[:INACTIVE_LIMIT],
            'cadence': {
                'avg_days_between_orders': avg_cadence,
                'customers_with_repeat': len(cadence_values),
            },
        })


class BotFunnelReportView(BaseAnalyticsView):
    """Funil do bot (CustomerSession) + conversão sessão→pedido."""

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        sessions = CustomerSession.objects.filter(
            company__store=store,
            created_at__date__range=(start, end),
        )
        funnel = [
            {'status': r['status'], 'count': r['count']}
            for r in sessions.values('status').annotate(count=Count('id')).order_by('-count')
        ]
        total = sessions.count()
        with_order = sessions.filter(order__isnull=False).count()

        # Tempo de resposta: conversas ligadas às sessões da loja em que o
        # atendente/bot respondeu depois da última mensagem do cliente.
        response_rows = sessions.filter(
            conversation__isnull=False,
            conversation__last_customer_message_at__isnull=False,
            conversation__last_agent_message_at__isnull=False,
            conversation__last_agent_message_at__gte=F('conversation__last_customer_message_at'),
        ).values_list('conversation__last_customer_message_at', 'conversation__last_agent_message_at')
        deltas = [(agent - customer).total_seconds() / 60 for customer, agent in response_rows]

        return Response({
            'funnel': funnel,
            'conversion': {
                'sessions': total,
                'with_order': with_order,
                'rate': round(with_order / total * 100, 1) if total else 0.0,
            },
            'response_time': {
                'avg_minutes': round(sum(deltas) / len(deltas), 1) if deltas else None,
                'conversations': len(deltas),
            },
        })


class OverviewReportView(BaseAnalyticsView):
    """Resumo executivo: KPIs do período atual × período anterior + deltas.

    Livre para todos os planos — é a Visão Geral do painel.
    """

    plan_feature = None

    _doc = """
    O período anterior tem a MESMA duração, imediatamente antes do atual —
    todo relatório vira comparável sem o front fazer duas chamadas.
    """

    def _kpis(self, store, start, end):
        from datetime import datetime, time as dtime
        from django.utils.timezone import make_aware
        start_dt = make_aware(datetime.combine(start, dtime.min))
        end_dt = make_aware(datetime.combine(end, dtime.max))

        all_orders = StoreOrder.objects.filter(store=store, created_at__range=(start_dt, end_dt))
        # `payment_status='paid'` sozinho conta venda cancelada depois do
        # pagamento e pedido de teste do dono — a nota da loja saía inflada.
        paid = self.paid_orders(store, start, end)
        agg = paid.aggregate(orders=Count('id'), revenue=Sum('total'), avg_ticket=Avg('total'))
        total = all_orders.count()
        cancelled = all_orders.filter(status__in=('cancelled', 'failed', 'refunded')).count()

        new_customers = StoreCustomer.objects.filter(
            store=store, created_at__range=(start_dt, end_dt)
        ).count()
        rating = StoreReview.objects.filter(
            store=store, created_at__range=(start_dt, end_dt)
        ).aggregate(avg=Avg('rating'), count=Count('id'))
        sessions = CustomerSession.objects.filter(
            company__store=store, created_at__range=(start_dt, end_dt)
        )
        session_count = sessions.count()
        with_order = sessions.filter(order__isnull=False).count()

        return {
            'orders': agg['orders'] or 0,
            'revenue': _round2(agg['revenue']),
            'avg_ticket': _round2(agg['avg_ticket']),
            'cancel_rate': round(cancelled / total * 100, 1) if total else 0.0,
            'new_customers': new_customers,
            'avg_rating': round(float(rating['avg']), 2) if rating['avg'] else None,
            'reviews': rating['count'],
            'bot_sessions': session_count,
            'bot_conversion': round(with_order / session_count * 100, 1) if session_count else 0.0,
        }

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        span = (end - start).days or 1
        from datetime import timedelta
        prev_start = start - timedelta(days=span)
        prev_end = start - timedelta(days=1)

        current = self._kpis(store, start, end)
        previous = self._kpis(store, prev_start, prev_end)

        def pct(cur, prev):
            if not prev:
                return None
            return round((float(cur or 0) - float(prev)) / float(prev) * 100, 1)

        delta = {
            'revenue_pct': pct(current['revenue'], previous['revenue']),
            'orders_pct': pct(current['orders'], previous['orders']),
            'avg_ticket_pct': pct(current['avg_ticket'], previous['avg_ticket']),
            'new_customers_pct': pct(current['new_customers'], previous['new_customers']),
        }
        return Response({
            'current': current,
            'previous': previous,
            'delta': delta,
            'period': {'start': start, 'end': end, 'prev_start': prev_start, 'prev_end': prev_end},
        })


SCORE_LEVELS = ((85, 'diamante'), (65, 'ouro'), (40, 'prata'), (0, 'bronze'))


class StoreScoreView(BaseAnalyticsView):
    """Score da Loja (gamificação do lojista): 100 pontos distribuídos em
    conquistas acionáveis — cada uma é uma alavanca real de venda que também
    alimenta os relatórios (custo → matriz, Google → reviews, fotos → conversão).

    Livre para todos os planos: é o motor de engajamento/onboarding.
    """

    plan_feature = None

    def get(self, request):
        store, _, _, err = self.resolve(request)
        if err:
            return err

        products = StoreProduct.objects.filter(store=store, status='active')
        total_products = products.count()

        def pct(qs_count):
            return (qs_count / total_products) if total_products else 0.0

        # foto pode estar no ImageField OU na URL externa
        with_photo = pct(products.filter(
            Q(main_image_url__gt='') | Q(main_image__isnull=False) & ~Q(main_image='')
        ).count())
        with_desc = pct(products.exclude(description='').count())
        with_cost = pct(products.filter(cost_price__gt=0).count())

        metadata = store.metadata or {}
        avg_rating = StoreReview.objects.filter(store=store).aggregate(avg=Avg('rating'))['avg']

        from datetime import timedelta as _td
        recent = StoreOrder.objects.filter(store=store, created_at__gte=timezone.now() - _td(days=90))
        recent_total = recent.count()
        recent_cancel_rate = (
            recent.filter(status__in=('cancelled', 'failed', 'refunded')).count() / recent_total
            if recent_total else 0.0
        )

        checklist = [
            # (key, label, points, done, cta)
            ('logo', 'Logo da loja', 6, bool(store.logo or store.logo_url),
             'Suba a logo em Configurações da loja'),
            ('descricao_loja', 'Descrição da loja', 4, bool((store.description or '').strip()),
             'Conte a história da loja em Configurações'),
            ('horarios', 'Horários de funcionamento', 6, bool(store.operating_hours),
             'Defina os horários em Configurações'),
            ('produtos_com_foto', 'Fotos em 80%+ dos produtos', 14, with_photo >= 0.8,
             'Produto com foto vende até 2× mais — complete o catálogo'),
            ('produtos_com_descricao', 'Descrição em 80%+ dos produtos', 10, with_desc >= 0.8,
             'Use *negrito* e listas — o cardápio formata'),
            ('produtos_com_custo', 'Custo em 80%+ dos produtos', 12, with_cost >= 0.8,
             'Preencha o Custo e libere a Engenharia de Cardápio'),
            ('cupom_boas_vindas', 'Cupom de boas-vindas ativo', 8,
             StoreCoupon.objects.filter(store=store, is_active=True, first_order_only=True,
                                        valid_until__gt=timezone.now()).exists(),
             'Crie um cupom só de primeiro pedido — converte visitante em cliente'),
            ('google_review_url', 'Link de avaliação do Google', 10, bool(metadata.get('google_review_url')),
             'Cole o link em Configurações → Avaliações no Google e ligue o cupom 5★'),
            ('nota_media', 'Nota média 4.5★ ou mais', 12, bool(avg_rating and avg_rating >= 4.5),
             'Responda avaliações e cuide dos pratos com nota baixa (aba Bot & Avaliações)'),
            ('cancelamento_baixo', 'Cancelamento abaixo de 15% (90d)', 10,
             recent_total > 0 and recent_cancel_rate < 0.15,
             'Investigue os motivos na aba Operação'),
            ('fidelidade_ativa', 'Clube de fidelidade ligado', 8, bool(metadata.get('loyalty_enabled')),
             'Ative o cartão de selos — recorrência no piloto automático'),
        ]

        items = [
            {'key': k, 'label': label, 'points': pts, 'done': done, 'cta': cta}
            for k, label, pts, done, cta in checklist
        ]
        score = sum(i['points'] for i in items if i['done'])
        level = next(name for minimum, name in SCORE_LEVELS if score >= minimum)
        next_up = sorted((i for i in items if not i['done']), key=lambda i: -i['points'])[:3]

        return Response({
            'score': score,
            'level': level,
            'checklist': items,
            'next_up': next_up,
        })


class CouponsReportView(BaseAnalyticsView):
    """ROI de cupom: uso, desconto concedido e receita gerada por código."""

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        qs = self.paid_orders(store, start, end)
        total_orders = qs.count()
        coupons = defaultdict(lambda: {'orders': 0, 'discount': Decimal('0'), 'revenue': Decimal('0')})
        for code, discount, total in qs.exclude(coupon_code='').values_list('coupon_code', 'discount', 'total'):
            key = (code or '').strip().upper()
            if not key:
                continue
            coupons[key]['orders'] += 1
            coupons[key]['discount'] += discount or Decimal('0')
            coupons[key]['revenue'] += total or Decimal('0')
        rows = [
            {
                'code': code,
                'orders': agg['orders'],
                'discount_total': _round2(agg['discount']),
                'revenue': _round2(agg['revenue']),
                'avg_ticket': _round2(agg['revenue'] / agg['orders']) if agg['orders'] else 0,
            }
            for code, agg in sorted(coupons.items(), key=lambda kv: -kv[1]['revenue'])
        ]
        with_coupon = sum(r['orders'] for r in rows)
        return Response({
            'coupons': rows,
            'summary': {
                'orders_with_coupon': with_coupon,
                'total_orders': total_orders,
                'coupon_usage_pct': round(with_coupon / total_orders * 100, 1) if total_orders else 0.0,
                'total_discount': _round2(sum(Decimal(str(r['discount_total'])) for r in rows)),
            },
        })


MAX_BASKET_ORDERS = 5000
TOP_PAIRS = 20


class BasketReportView(BaseAnalyticsView):
    """Cesta: pares de produtos mais pedidos juntos (upsell/combos novos)."""

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        order_ids = list(self.paid_orders(store, start, end).values_list('id', flat=True)[:MAX_BASKET_ORDERS])
        items_by_order = defaultdict(set)
        for order_id, name in StoreOrderItem.objects.filter(order_id__in=order_ids).values_list('order_id', 'product_name'):
            if name:
                items_by_order[order_id].add(name)
        pair_counts = defaultdict(int)
        for names in items_by_order.values():
            for a, b in combinations(sorted(names), 2):
                pair_counts[(a, b)] += 1
        pairs = [
            {'product_a': a, 'product_b': b, 'orders_together': count}
            for (a, b), count in sorted(pair_counts.items(), key=lambda kv: -kv[1])[:TOP_PAIRS]
        ]
        return Response({'pairs': pairs, 'orders_analyzed': len(items_by_order)})


class CancellationsReportView(BaseAnalyticsView):
    """Cancelamentos: taxa, valor perdido e série diária."""

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        qs = StoreOrder.objects.filter(store=store, created_at__date__range=(start, end))
        total_orders = qs.count()
        cancelled = qs.filter(status__in=('cancelled', 'failed', 'refunded'))
        # metrics-ok: `lost` e receita PERDIDA — o oposto de faturamento.
        # Passar pelo nucleo aqui zeraria o numero, que e justamente o dado.
        agg = cancelled.aggregate(count=Count('id'), lost=Sum('total'))
        timeline = [
            {'date': r['day'], 'cancelled': r['count'], 'lost_value': _round2(r['lost'])}
            for r in cancelled.annotate(day=TruncDate('created_at'))
            .values('day')
            # metrics-ok: receita perdida de cancelados, nao faturamento.
            .annotate(count=Count('id'), lost=Sum('total'))
            .order_by('day')
        ]
        by_status = [
            {'status': r['status'], 'count': r['count'], 'lost_value': _round2(r['lost'])}
            # metrics-ok: receita perdida por status de cancelamento.
            for r in cancelled.values('status').annotate(count=Count('id'), lost=Sum('total')).order_by('-count')
        ]
        by_reason = [
            {'reason': r['cancel_reason'], 'count': r['count'], 'lost_value': _round2(r['lost'])}
            for r in cancelled.exclude(cancel_reason='')
            # metrics-ok: receita perdida por motivo de cancelamento.
            .values('cancel_reason').annotate(count=Count('id'), lost=Sum('total')).order_by('-count')[:10]
        ]
        count = agg['count'] or 0
        return Response({
            'summary': {
                'cancelled': count,
                'total_orders': total_orders,
                'rate': round(count / total_orders * 100, 1) if total_orders else 0.0,
                'lost_value': _round2(agg['lost']),
            },
            'by_status': by_status,
            'by_reason': by_reason,
            'timeline': timeline,
        })


class SchedulingReportView(BaseAnalyticsView):
    """Pedidos agendados por data e por janela de horário."""

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        # Montava queryset proprio e so excluia cancelado/falho: pedido NAO
        # PAGO entrava como receita agendada. Agora parte do nucleo.
        qs = self.paid_orders(store, start, end).filter(scheduled_date__isnull=False)
        by_date = [
            {'date': r['scheduled_date'], 'orders': r['orders'], 'revenue': _round2(r['revenue'])}
            for r in qs.values('scheduled_date').annotate(orders=Count('id'), revenue=Sum('total')).order_by('scheduled_date')
        ]
        by_slot = [
            {'slot': r['scheduled_time'] or 'sem_horario', 'orders': r['orders']}
            for r in qs.values('scheduled_time').annotate(orders=Count('id')).order_by('-orders')
        ]
        return Response({'by_date': by_date, 'by_slot': by_slot, 'total': qs.count()})


class CashHistoryReportView(BaseAnalyticsView):
    """Histórico de caixas fechados: esperado × contado × quebra por operador."""

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        sessions = (
            StoreCashSession.objects.filter(
                store=store, status='closed', opened_at__date__range=(start, end)
            )
            .select_related('opened_by', 'closed_by')
            .annotate(
                total_reinforcement=Sum(
                    'movements__amount',
                    filter=Q(movements__kind=StoreCashMovement.Kind.REINFORCEMENT),
                ),
                total_withdrawal=Sum(
                    'movements__amount',
                    filter=Q(movements__kind=StoreCashMovement.Kind.WITHDRAWAL),
                ),
            )
            .order_by('-opened_at')[:100]
        )
        rows = []
        total_difference = Decimal('0')
        for s in sessions:
            diff = s.difference or Decimal('0')
            total_difference += diff
            rows.append({
                'id': str(s.id),
                'opened_at': s.opened_at,
                'closed_at': s.closed_at,
                'opened_by': getattr(s.opened_by, 'username', None),
                'closed_by': getattr(s.closed_by, 'username', None),
                'opening_amount': _round2(s.opening_amount),
                'expected_amount': _round2(s.expected_amount),
                'counted_amount': _round2(s.counted_amount),
                'difference': _round2(diff),
                'reinforcement': _round2(s.total_reinforcement),
                'withdrawal': _round2(s.total_withdrawal),
            })
        return Response({
            'sessions': rows,
            'summary': {
                'count': len(rows),
                'total_difference': _round2(total_difference),
                'with_shortage': sum(1 for r in rows if (r['difference'] or 0) < 0),
            },
        })


class StaffReportView(BaseAnalyticsView):
    """Produtividade do PDV: pedidos, receita e descontos manuais por operador."""

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        rows = (
            self.paid_orders(store, start, end)
            .filter(created_by_staff__isnull=False)
            .values('created_by_staff__username', 'created_by_staff__first_name')
            .annotate(
                orders=Count('id'),
                revenue=Sum('total'),
                avg_ticket=Avg('total'),
                manual_discounts=Sum('manual_discount_value'),
            )
            .order_by('-revenue')
        )
        staff = [
            {
                'username': r['created_by_staff__username'],
                'name': r['created_by_staff__first_name'] or r['created_by_staff__username'],
                'orders': r['orders'],
                'revenue': _round2(r['revenue']),
                'avg_ticket': _round2(r['avg_ticket']),
                'manual_discounts': _round2(r['manual_discounts']),
            }
            for r in rows
        ]
        return Response({'staff': staff})


class MenuMatrixReportView(BaseAnalyticsView):
    """Engenharia de cardápio (Kasavana-Smith): popularidade × margem de
    contribuição. Quadrantes: estrela, burro_de_carga (vende muito/lucra
    pouco), enigma (lucra muito/vende pouco), abacaxi. Usa o cost_price
    ATUAL do produto — aproximação até existir snapshot de custo no item.
    """

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        from django.db.models.functions import Coalesce
        # Custo por item: snapshot unit_cost (BI Fase 2) com fallback no
        # cost_price atual do produto para o legado sem backfill.
        rows = list(
            StoreOrderItem.objects.filter(order__in=self.paid_orders(store, start, end), product__isnull=False)
            .values('product_id', 'product__name')
            .annotate(
                # cost_total ANTES de quantity: a annotation quantity=Sum(...)
                # sombreia o campo e o F('quantity') viraria agregado (FieldError)
                cost_total=Sum(F('quantity') * Coalesce(F('unit_cost'), F('product__cost_price'))),
                quantity=Sum('quantity'),
                revenue=Sum('subtotal'),
            )
            .order_by('-quantity')
        )
        with_cost, missing_cost = [], []
        for r in rows:
            entry = {
                'product_name': r['product__name'],
                'quantity': r['quantity'],
                'revenue': _round2(r['revenue']),
            }
            cost_total = r['cost_total']
            if cost_total and cost_total > 0 and r['quantity']:
                avg_price = (r['revenue'] or Decimal('0')) / r['quantity']
                avg_cost = cost_total / r['quantity']
                entry['unit_margin'] = _round2(avg_price - avg_cost)
                entry['margin_pct'] = round(float((avg_price - avg_cost) / avg_price * 100), 1) if avg_price else 0.0
                with_cost.append(entry)
            else:
                missing_cost.append(entry)

        products = []
        if with_cost:
            total_qty = sum(e['quantity'] for e in with_cost)
            # Regra dos 70%: popular se vende >= 70% da média por item
            popularity_threshold = total_qty / len(with_cost) * 0.7
            avg_margin = sum(e['unit_margin'] * e['quantity'] for e in with_cost) / total_qty
            for e in with_cost:
                popular = e['quantity'] >= popularity_threshold
                profitable = e['unit_margin'] >= avg_margin
                e['quadrant'] = (
                    'estrela' if popular and profitable
                    else 'burro_de_carga' if popular
                    else 'enigma' if profitable
                    else 'abacaxi'
                )
                products.append(e)

        return Response({
            'products': products,
            'missing_cost': missing_cost,
            'summary': {
                'analyzed': len(products),
                'missing_cost': len(missing_cost),
            },
        })


COHORT_MONTHS = 6
COHORT_HORIZON = 5


class CohortReportView(BaseAnalyticsView):
    """Retenção por safra mensal: % dos clientes do 1º pedido no mês X que
    voltaram em M+1..M+5. Cliente = telefone normalizado."""

    def get(self, request):
        store, _, _, err = self.resolve(request)
        if err:
            return err
        tz = timezone.get_current_timezone()
        # metrics-ok: `payment_status='paid'` aqui e proxy de "pedido real do
        # cliente" para medir RECORRENCIA — nao ha soma de dinheiro nenhuma.
        pairs = StoreOrder.objects.filter(store=store, payment_status='paid').exclude(
            customer_phone=''
        ).values_list('customer_phone', 'created_at')

        months_by_phone = defaultdict(set)
        for phone, created in pairs:
            local = created.astimezone(tz)
            months_by_phone[phone.strip()].add(local.year * 12 + (local.month - 1))

        cohorts = defaultdict(lambda: {'size': 0, 'returns': [0] * COHORT_HORIZON})
        for months in months_by_phone.values():
            first = min(months)
            cohorts[first]['size'] += 1
            for offset in range(1, COHORT_HORIZON + 1):
                if first + offset in months:
                    cohorts[first]['returns'][offset - 1] += 1

        now = timezone.now().astimezone(tz)
        current_month = now.year * 12 + (now.month - 1)
        out = []
        for month_key in sorted(cohorts)[-COHORT_MONTHS:]:
            c = cohorts[month_key]
            year, month = divmod(month_key, 12)
            # Meses futuros ao calendário ficam null (safra ainda não viveu M+n)
            retention = [
                round(c['returns'][i] / c['size'] * 100, 1) if month_key + i + 1 <= current_month else None
                for i in range(COHORT_HORIZON)
            ]
            out.append({
                'cohort': f'{year}-{month + 1:02d}',
                'size': c['size'],
                'retention': retention,
            })
        return Response({'cohorts': out, 'horizon': COHORT_HORIZON})


class ReviewsReportView(BaseAnalyticsView):
    """Nota média, distribuição e comentários recentes."""

    def get(self, request):
        store, start, end, err = self.resolve(request)
        if err:
            return err
        reviews = StoreReview.objects.filter(store=store, created_at__date__range=(start, end))
        summary = reviews.aggregate(avg_rating=Avg('rating'), count=Count('id'))
        distribution = [
            {'rating': r['rating'], 'count': r['count']}
            for r in reviews.values('rating').annotate(count=Count('id')).order_by('-rating')
        ]
        recent = [
            {
                'rating': r.rating,
                'comment': r.comment,
                'customer_name': r.customer_name,
                'created_at': r.created_at,
            }
            for r in reviews.order_by('-created_at')[:10]
        ]

        from ..models.review import StoreProductReview
        by_product = [
            {
                'product_name': r['product__name'],
                'avg_rating': round(float(r['avg']), 2),
                'count': r['count'],
            }
            for r in StoreProductReview.objects.filter(
                review__store=store, created_at__date__range=(start, end)
            )
            .values('product__name')
            .annotate(avg=Avg('rating'), count=Count('id'))
            .order_by('avg')  # piores primeiro: é onde o dono precisa agir
        ]
        # ── Pilares ───────────────────────────────────────────────────────
        # "Nota 4,6" não diz o que consertar. Cada pilar leva o PRÓPRIO volume
        # porque eles divergem: quem retira no balcão não avalia entrega, e
        # responder os pilares é opcional. Média sem o volume ao lado repete o
        # problema que a nota geral já tinha.
        PILARES = (
            ('comida', 'rating_comida', 'Qualidade da comida'),
            ('entrega', 'rating_entrega', 'Tempo de entrega'),
            ('atendimento', 'rating_atendimento', 'Atendimento'),
        )
        pilares = []
        for chave, campo, rotulo in PILARES:
            agg = reviews.exclude(**{f'{campo}__isnull': True}).aggregate(
                media=Avg(campo), total=Count('id'),
            )
            pilares.append({
                'chave': chave,
                'rotulo': rotulo,
                # `None` sem nenhuma nota: "Entrega 0,0" leria como serviço
                # péssimo, quando a verdade é que ninguém avaliou esse pilar.
                'media': round(float(agg['media']), 2) if agg['media'] is not None else None,
                'total': agg['total'],
            })

        # O pior pilar é a única leitura que vira ação direta: diz o que atacar
        # primeiro. Só entram pilares com nota — senão o vazio venceria sempre.
        avaliados = [p for p in pilares if p['media'] is not None]
        pior_pilar = min(avaliados, key=lambda p: p['media'])['chave'] if avaliados else None

        return Response({
            'summary': {
                'avg_rating': round(float(summary['avg_rating']), 2) if summary['avg_rating'] else None,
                'count': summary['count'],
            },
            'distribution': distribution,
            'recent': recent,
            'by_product': by_product,
            'pilares': pilares,
            'pior_pilar': pior_pilar,
        })
