"""
Export views for generating reports and CSV exports.
"""
import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal
from django.http import Http404, HttpResponse
from django.db.models import Sum, Count, Avg, F, Q
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import user_can_access_store
from ..models import Store, StoreOrder, StoreProduct, StoreCustomer
from ..metrics import apenas_receita, hoje_local, itens_de_receita
from .views import IsStoreOwnerOrStaff


class BaseExportView(APIView):
    """Base class for export views."""
    
    permission_classes = [IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_store(self, request):
        """Get store from query params.

        Gate de tenant: superuser vê qualquer loja; demais usuários só
        acessam lojas para as quais têm permissão explícita.
        Acesso negado a uma loja existente → Http404 (info-hiding).
        """
        store_param = request.query_params.get('store')
        if not store_param:
            return None

        try:
            import uuid
            uuid.UUID(store_param)
            try:
                store = Store.objects.get(id=store_param)
            except Store.DoesNotExist:
                return None
        except (ValueError, AttributeError):
            store = Store.objects.filter(slug=store_param).first()

        if store is None:
            return None

        if not request.user.is_superuser and not user_can_access_store(request.user, store):
            raise Http404

        return store
    
    def revenue_queryset(self, store, **filtros):
        """Pedidos que contam como faturamento — SSOT em stores/metrics/.

        Os relatórios montavam `payment_status='paid'` na mão em ~10 pontos e
        somavam venda cancelada e pedido de teste do dono como receita.
        `filtros` são lookups extras de período (ex.: `created_at__gte=...`).
        """

        return apenas_receita(StoreOrder.objects.filter(store=store, **filtros))

    def get_date_range(self, request):
        """Get date range from query params."""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        period = request.query_params.get('period', '30d')
        
        if start_date and end_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d').date()
                end = datetime.strptime(end_date, '%Y-%m-%d').date()
                return start, end
            except ValueError:
                pass
        
        # Default periods
        today = hoje_local()
        if period == '7d':
            return today - timedelta(days=7), today
        elif period == '30d':
            return today - timedelta(days=30), today
        elif period == '90d':
            return today - timedelta(days=90), today
        elif period == '1y':
            return today - timedelta(days=365), today
        else:
            return today - timedelta(days=30), today


class OrdersExportView(BaseExportView):
    """Export orders. `?fmt=xlsx` devolve planilha formatada; padrão é CSV.

    O CSV segue exatamente como era — quem já tem rotina montada em cima dele
    não quebra. O Excel é uma opção a mais, com moeda em R$, cabeçalho fixo,
    filtro por coluna e linha de totais.
    """

    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)

        start_date, end_date = self.get_date_range(request)

        orders = StoreOrder.objects.filter(
            store=store,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).select_related('customer').prefetch_related('items__product').order_by('-created_at')

        # `fmt`, não `format`: este último é reservado pelo DRF para content
        # negotiation e faz a requisição virar 404 antes de chegar aqui.
        if (request.query_params.get('fmt') or '').strip().lower() == 'xlsx':
            return self._xlsx(store, orders, start_date, end_date)

        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            'Número do Pedido', 'Data', 'Cliente', 'Email', 'Telefone',
            'Status', 'Status Pagamento', 'Método Entrega', 'Subtotal',
            'Taxa Entrega', 'Desconto', 'Total', 'Itens'
        ])
        
        for order in orders:
            items = ', '.join([
                f"{item.product_name} x{item.quantity}" 
                for item in order.items.all()
            ])
            writer.writerow([
                order.order_number,
                order.created_at.strftime('%Y-%m-%d %H:%M'),
                order.customer_name,
                order.customer_email,
                order.customer_phone,
                order.get_status_display(),
                order.get_payment_status_display(),
                order.get_delivery_method_display(),
                float(order.subtotal),
                float(order.delivery_fee),
                float(order.discount),
                float(order.total),
                items
            ])
        
        output.seek(0)
        response = HttpResponse(output.read(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="pedidos_{store.slug}_{start_date}_{end_date}.csv"'
        return response

    def _xlsx(self, store, orders, start_date, end_date):
        """Mesmos dados do CSV, com os tipos que o Excel entende."""
        from ..services.exports.planilha import Coluna, resposta_xlsx

        linhas = [
            {
                'numero': o.order_number,
                'data': o.created_at,
                'cliente': o.customer_name,
                'email': o.customer_email,
                'telefone': o.customer_phone,
                'status': o.get_status_display(),
                'pagamento': o.get_payment_status_display(),
                'entrega': o.get_delivery_method_display(),
                'subtotal': o.subtotal,
                'taxa': o.delivery_fee,
                'desconto': o.discount,
                'total': o.total,
                'itens': ', '.join(
                    f'{i.product_name} x{i.quantity}' for i in o.items.all()
                ),
            }
            for o in orders
        ]
        colunas = [
            Coluna('Pedido', 'numero'),
            Coluna('Data', 'data', tipo='data_hora'),
            Coluna('Cliente', 'cliente', largura=26),
            Coluna('E-mail', 'email', largura=26),
            Coluna('Telefone', 'telefone'),
            Coluna('Status', 'status'),
            Coluna('Pagamento', 'pagamento'),
            Coluna('Entrega', 'entrega'),
            Coluna('Subtotal', 'subtotal', tipo='dinheiro', somar=True),
            Coluna('Taxa', 'taxa', tipo='dinheiro', somar=True),
            Coluna('Desconto', 'desconto', tipo='dinheiro', somar=True),
            Coluna('Total', 'total', tipo='dinheiro', somar=True),
            Coluna('Itens', 'itens', largura=50),
        ]
        return resposta_xlsx(
            linhas, colunas,
            f'pedidos_{store.slug}_{start_date}_{end_date}.xlsx',
            titulo='Pedidos',
            subtitulo=f'{store.name} · {start_date:%d/%m/%Y} a {end_date:%d/%m/%Y}',
        )


class RevenueReportView(BaseExportView):
    """Revenue report with aggregations."""
    
    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)
        
        start_date, end_date = self.get_date_range(request)
        group_by = request.query_params.get('group_by', 'day')  # day, week, month
        
        # Série e totais vêm do núcleo. Antes filtrava e agrupava por
        # `created_at`; o resto do painel usa a data do pagamento, então este
        # relatório distribuía a receita em dias diferentes das outras telas.
        from apps.stores import metrics

        janela = metrics.de_datas(start_date, end_date)
        granularidade = {'week': 'semana', 'month': 'mes'}.get(group_by, 'dia')

        pontos = metrics.serie_temporal(store, janela, granularidade)
        revenue_data = [
            {
                'period': p['periodo'],
                'total_revenue': p['receita'],
                'order_count': p['pedidos'],
                'avg_order_value': p['ticket_medio'],
                'total_delivery_fees': p['frete'],
                'total_discounts': p['desconto'],
            }
            for p in pontos
        ]

        agregado = metrics.totais(store, janela)
        summary = {
            'total_revenue': agregado['receita'],
            'total_orders': agregado['pedidos'],
            'avg_order_value': agregado['ticket_medio'],
            'total_delivery_fees': agregado['frete'],
            'total_discounts': agregado['desconto'],
        }
        
        return Response({
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'group_by': group_by
            },
            'summary': {
                'total_revenue': float(summary['total_revenue'] or 0),
                'total_orders': summary['total_orders'] or 0,
                'avg_order_value': float(summary['avg_order_value'] or 0),
                'total_delivery_fees': float(summary['total_delivery_fees'] or 0),
                'total_discounts': float(summary['total_discounts'] or 0)
            },
            'data': [
                {
                    'period': item['period'].isoformat() if item['period'] else None,
                    'total_revenue': float(item['total_revenue'] or 0),
                    'order_count': item['order_count'],
                    'avg_order_value': float(item['avg_order_value'] or 0),
                    'total_delivery_fees': float(item['total_delivery_fees'] or 0),
                    'total_discounts': float(item['total_discounts'] or 0)
                }
                for item in revenue_data
            ]
        })


class ProductsReportView(BaseExportView):
    """Products performance report."""
    
    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)
        
        start_date, end_date = self.get_date_range(request)
        
        # Get order items for the period
        from ..models import StoreOrderItem
        
        items = itens_de_receita(loja=store).filter(
            order__created_at__date__gte=start_date,
            order__created_at__date__lte=end_date,
        ).values(
            'product_id', 'product_name'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('subtotal'),
            order_count=Count('order', distinct=True)
        ).order_by('-total_quantity')[:50]
        
        # Stock info
        products = StoreProduct.objects.filter(
            store=store,
            status='active'
        ).values('id', 'name', 'stock_quantity', 'price')
        
        stock_map = {p['id']: p for p in products}
        
        return Response({
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'top_products': [
                {
                    'product_id': str(item['product_id']) if item['product_id'] else None,
                    'product_name': item['product_name'],
                    'total_quantity': item['total_quantity'],
                    'total_revenue': float(item['total_revenue'] or 0),
                    'order_count': item['order_count'],
                    'current_stock': stock_map.get(item['product_id'], {}).get('stock_quantity')
                }
                for item in items
            ]
        })


class StockReportView(BaseExportView):
    """Stock/inventory report."""
    
    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)
        
        low_stock_threshold = int(request.query_params.get('low_stock', 10))
        
        products = StoreProduct.objects.filter(
            store=store
        ).select_related('category').values(
            'id', 'name', 'sku', 'stock_quantity', 'price',
            'status', 'category__name'
        ).order_by('stock_quantity')
        
        low_stock = [p for p in products if (p['stock_quantity'] or 0) <= low_stock_threshold]
        out_of_stock = [p for p in products if (p['stock_quantity'] or 0) == 0]
        
        return Response({
            'summary': {
                'total_products': len(list(products)),
                'low_stock_count': len(low_stock),
                'out_of_stock_count': len(out_of_stock),
                'low_stock_threshold': low_stock_threshold
            },
            'low_stock_products': [
                {
                    'id': str(p['id']),
                    'name': p['name'],
                    'sku': p['sku'],
                    'stock_quantity': p['stock_quantity'],
                    'price': float(p['price'] or 0),
                    'status': p['status'],
                    'category': p['category__name']
                }
                for p in low_stock
            ],
            'out_of_stock_products': [
                {
                    'id': str(p['id']),
                    'name': p['name'],
                    'sku': p['sku'],
                    'category': p['category__name']
                }
                for p in out_of_stock
            ]
        })


class CustomersReportView(BaseExportView):
    """Customers report."""
    
    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)
        
        start_date, end_date = self.get_date_range(request)
        
        # Top customers by order value
        top_customers = self.revenue_queryset(
            store,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        ).values(
            'customer_email', 'customer_name', 'customer_phone'
        ).annotate(
            total_spent=Sum('total'),
            order_count=Count('id'),
            avg_order_value=Avg('total')
        ).order_by('-total_spent')[:50]
        
        # New vs returning customers
        all_customers = StoreOrder.objects.filter(
            store=store,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).values('customer_email').distinct().count()
        
        returning = StoreOrder.objects.filter(
            store=store,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).values('customer_email').annotate(
            order_count=Count('id')
        ).filter(order_count__gt=1).count()
        
        return Response({
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'summary': {
                'total_customers': all_customers,
                'new_customers': all_customers - returning,
                'returning_customers': returning,
                'retention_rate': round((returning / all_customers * 100) if all_customers > 0 else 0, 2)
            },
            'top_customers': [
                {
                    'email': c['customer_email'],
                    'name': c['customer_name'],
                    'phone': c['customer_phone'],
                    'total_spent': float(c['total_spent'] or 0),
                    'order_count': c['order_count'],
                    'avg_order_value': float(c['avg_order_value'] or 0)
                }
                for c in top_customers
            ]
        })


class CustomerInsightsReportView(BaseExportView):
    """Insights de clientes: LTV, inatividade/churn e distribuição de frequência.

    Usa StoreCustomer (identidade deduplicada por loja, stats denormalizados
    total_orders/total_spent/last_order_at) para as métricas lifetime — mais
    confiável que agrupar pedidos por string de telefone/email. O range de datas
    aplica-se apenas à série "novos clientes ao longo do tempo".
    """

    @staticmethod
    def _customer_name(customer):
        # Preferir nome real; nunca expor email placeholder (@pastita.local) nem
        # 'cliente_...' como nome (ver CLAUDE.md).
        user = customer.user
        full = (user.get_full_name() or '').strip()
        if full:
            return full
        unified = getattr(customer, 'unified_user', None)
        uname = (getattr(unified, 'name', '') or '').strip() if unified else ''
        if uname:
            return uname
        email = (user.email or '').strip()
        if email and '@pastita.local' not in email and not email.startswith('cliente_'):
            return email
        return customer.phone or customer.whatsapp or 'Cliente'

    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)

        start_date, end_date = self.get_date_range(request)
        group_by = request.query_params.get('group_by', 'day')
        now = timezone.now()
        cutoff_30 = now - timedelta(days=30)
        cutoff_60 = now - timedelta(days=60)

        customers = StoreCustomer.objects.filter(store=store)

        summary = customers.aggregate(
            total_customers=Count('id'),
            avg_ltv=Avg('total_spent'),
            avg_orders=Avg('total_orders'),
            active_30d=Count('id', filter=Q(last_order_at__gte=cutoff_30)),
            at_risk=Count('id', filter=Q(last_order_at__lt=cutoff_30, last_order_at__gte=cutoff_60)),
            inactive=Count('id', filter=Q(last_order_at__lt=cutoff_60) | Q(last_order_at__isnull=True)),
        )
        total = summary['total_customers'] or 0
        inactive = summary['inactive'] or 0

        freq = customers.aggregate(
            b1=Count('id', filter=Q(total_orders=1)),
            b2=Count('id', filter=Q(total_orders=2)),
            b35=Count('id', filter=Q(total_orders__gte=3, total_orders__lte=5)),
            b6=Count('id', filter=Q(total_orders__gte=6)),
        )

        top = customers.select_related('user', 'unified_user').order_by('-total_spent')[:20]
        top_ltv = [
            {
                'name': self._customer_name(c),
                'phone': c.phone or c.whatsapp or '',
                'total_spent': float(c.total_spent or 0),
                'total_orders': c.total_orders or 0,
                'last_order_at': c.last_order_at.isoformat() if c.last_order_at else None,
            }
            for c in top
        ]

        trunc = {'week': TruncWeek, 'month': TruncMonth}.get(group_by, TruncDate)
        new_rows = (
            customers
            .filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
            .annotate(bucket=trunc('created_at'))
            .values('bucket')
            .annotate(count=Count('id'))
            .order_by('bucket')
        )
        new_over_time = [
            {'period': r['bucket'].isoformat() if r['bucket'] else None, 'count': r['count']}
            for r in new_rows
        ]

        return Response({
            'generated_at': now.isoformat(),
            'period': {'start': start_date.isoformat(), 'end': end_date.isoformat(), 'group_by': group_by},
            'summary': {
                'total_customers': total,
                'avg_ltv': float(summary['avg_ltv'] or 0),
                'avg_orders': float(summary['avg_orders'] or 0),
                'active_30d': summary['active_30d'] or 0,
                'at_risk_30_60d': summary['at_risk'] or 0,
                'inactive_60d': inactive,
                'churn_rate': round((inactive / total * 100) if total else 0, 2),
            },
            'frequency': [
                {'bucket': '1 pedido', 'count': freq['b1'] or 0},
                {'bucket': '2 pedidos', 'count': freq['b2'] or 0},
                {'bucket': '3-5 pedidos', 'count': freq['b35'] or 0},
                {'bucket': '6+ pedidos', 'count': freq['b6'] or 0},
            ],
            'top_ltv': top_ltv,
            'new_over_time': new_over_time,
        })


class StoreDashboardStatsView(BaseExportView):
    """Per-store dashboard statistics (orders, revenue, stock). See core.DashboardStatsView for the global one."""
    
    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)
        
        today = hoje_local()
        yesterday = today - timedelta(days=1)
        last_7_days = today - timedelta(days=7)
        last_30_days = today - timedelta(days=30)
        
        # Faturamento vem do núcleo: janela no fuso da loja e agrupamento pela
        # data do PAGAMENTO. Aqui filtrava por `created_at`, eixo diferente do
        # resto do painel — este resumo não batia com o card da home.
        from apps.stores import metrics

        today_revenue = metrics.totais(store, metrics.hoje())['receita']
        yesterday_revenue = metrics.totais(store, metrics.ontem())['receita']
        week_revenue = metrics.totais(store, metrics.ultimos_dias(8))['receita']
        month_revenue = metrics.totais(store, metrics.ultimos_dias(31))['receita']

        # Contagem operacional continua sobre o queryset cru: a operação
        # precisa ver o pedido cancelado, o faturamento não.
        _op = StoreOrder.objects.filter(store=store)
        today_orders = _op.filter(created_at__date=today)
        week_orders = _op.filter(created_at__date__gte=last_7_days)
        month_orders = _op.filter(created_at__date__gte=last_30_days)
        
        # Pending orders
        pending_orders = StoreOrder.objects.filter(
            store=store,
            status__in=['pending', 'confirmed', 'processing', 'preparing']
        ).count()
        
        # Low stock products
        low_stock = StoreProduct.objects.filter(
            store=store,
            status='active',
            stock_quantity__lte=10
        ).count()
        
        return Response({
            'today': {
                'orders': today_orders.count(),
                'revenue': float(today_revenue),
                'revenue_change': float(today_revenue - yesterday_revenue),
                'revenue_change_percent': round(
                    ((today_revenue - yesterday_revenue) / yesterday_revenue * 100) 
                    if yesterday_revenue > 0 else 0, 2
                )
            },
            'week': {
                'orders': week_orders.count(),
                'revenue': float(week_revenue),
                'avg_daily_revenue': float(week_revenue / 7)
            },
            'month': {
                'orders': month_orders.count(),
                'revenue': float(month_revenue),
                'avg_daily_revenue': float(month_revenue / 30)
            },
            'alerts': {
                'pending_orders': pending_orders,
                'low_stock_products': low_stock
            }
        })


class SaladasReportView(BaseExportView):
    """KPIs consolidados para o dashboard do Ce-Saladas."""

    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)

        period = request.query_params.get('period', 'today')
        today = hoje_local()

        if period == 'today':
            start = today
            end = today
            prev_start = today - timedelta(days=1)
            prev_end = today - timedelta(days=1)
            period_label = 'Hoje'
        elif period == '7d':
            start = today - timedelta(days=6)
            end = today
            prev_start = today - timedelta(days=13)
            prev_end = today - timedelta(days=7)
            period_label = 'Semana'
        else:  # 30d
            start = today - timedelta(days=29)
            end = today
            prev_start = today - timedelta(days=59)
            prev_end = today - timedelta(days=30)
            period_label = 'Mês'

        paid_orders = self.revenue_queryset(
            store,
            created_at__date__gte=start,
            created_at__date__lte=end,
        )
        prev_paid_orders = self.revenue_queryset(
            store,
            created_at__date__gte=prev_start,
            created_at__date__lte=prev_end,
        )

        curr = paid_orders.aggregate(
            revenue=Sum('total'),
            orders=Count('id'),
            avg_ticket=Avg('total'),
        )
        prev = prev_paid_orders.aggregate(
            revenue=Sum('total'),
            orders=Count('id'),
        )

        def pct_change(curr_val, prev_val):
            if prev_val and prev_val > 0:
                return round(float((curr_val - prev_val) / prev_val * 100), 1)
            return None

        curr_revenue = float(curr['revenue'] or 0)
        prev_revenue = float(prev['revenue'] or 0)
        curr_orders = curr['orders'] or 0
        prev_orders = prev['orders'] or 0

        # Gráfico de barras por dia
        chart_data = (
            paid_orders
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(value=Sum('total'))
            .order_by('day')
        )
        revenue_chart = [
            {'label': item['day'].strftime('%d/%m'), 'value': float(item['value'] or 0)}
            for item in chart_data
        ]

        # Top produtos via StoreOrderItem
        from apps.stores.models.order import StoreOrderItem
        top_products_qs = (
            StoreOrderItem.objects.filter(order__in=paid_orders)
            .values('product_name')
            .annotate(quantity=Sum('quantity'), revenue=Sum('subtotal'))
            .order_by('-quantity')[:10]
        )
        top_products = [
            {'name': p['product_name'], 'quantity': p['quantity'], 'revenue': float(p['revenue'] or 0)}
            for p in top_products_qs
        ]

        # Receita por categoria
        cat_qs = (
            StoreOrderItem.objects.filter(order__in=paid_orders, product__isnull=False)
            .values('product__category__name')
            .annotate(revenue=Sum('subtotal'))
            .order_by('-revenue')
        )
        total_cat_revenue = sum(float(c['revenue'] or 0) for c in cat_qs)
        category_revenue = [
            {
                'name': c['product__category__name'] or 'Sem categoria',
                'revenue': float(c['revenue'] or 0),
                'percent': round(float(c['revenue'] or 0) / total_cat_revenue * 100) if total_cat_revenue > 0 else 0,
            }
            for c in cat_qs
        ]

        # Clientes novos vs recorrentes
        period_phones = list(paid_orders.values_list('customer_phone', flat=True).distinct())
        total_period_customers = len(period_phones)
        returning = (
            self.revenue_queryset(
                store,
                customer_phone__in=period_phones,
                created_at__date__lt=start,
            )
            .values('customer_phone')
            .distinct()
            .count()
        )
        new_customers = max(total_period_customers - returning, 0)

        # Top clientes por gasto
        top_customers_qs = (
            paid_orders
            .values('customer_name', 'customer_phone')
            .annotate(total_spent=Sum('total'), order_count=Count('id'), avg_ticket=Avg('total'))
            .order_by('-total_spent')[:10]
        )
        top_customers = [
            {
                'name': c['customer_name'],
                'phone': c['customer_phone'],
                'orders': c['order_count'],
                'total_spent': float(c['total_spent'] or 0),
                'avg_ticket': float(c['avg_ticket'] or 0),
            }
            for c in top_customers_qs
        ]

        # Top bairros
        delivery_orders = StoreOrder.objects.filter(
            store=store,
            created_at__date__gte=start,
            created_at__date__lte=end,
            delivery_method='delivery',
        ).only('delivery_address')
        neighborhoods: dict = {}
        for order in delivery_orders:
            addr = order.delivery_address or {}
            name = addr.get('neighborhood') or addr.get('bairro') or ''
            if name:
                neighborhoods[name] = neighborhoods.get(name, 0) + 1
        top_neighborhoods = [
            {'name': n, 'orders': cnt}
            for n, cnt in sorted(neighborhoods.items(), key=lambda x: -x[1])[:10]
        ]

        return Response({
            'period': {'label': period_label, 'start': start.isoformat(), 'end': end.isoformat()},
            'kpis': {
                'revenue': {'value': curr_revenue, 'change_percent': pct_change(curr_revenue, prev_revenue)},
                'orders': {'value': curr_orders, 'change_abs': curr_orders - prev_orders},
                'avg_ticket': {'value': float(curr['avg_ticket'] or 0), 'change_percent': None},
            },
            'revenue_chart': revenue_chart,
            'top_products': top_products,
            'category_revenue': category_revenue,
            'customers': {'total': total_period_customers, 'new': new_customers, 'returning': returning},
            'top_customers': top_customers,
            'top_neighborhoods': top_neighborhoods,
        })
