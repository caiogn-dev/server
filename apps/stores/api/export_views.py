"""
Export views for generating reports and CSV exports.
"""
import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal
from django.http import HttpResponse
from django.db.models import Sum, Count, Avg, F, Q
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import Store, StoreOrder, StoreProduct, StoreCustomer
from .views import IsStoreOwnerOrStaff


class BaseExportView(APIView):
    """Base class for export views."""
    
    permission_classes = [IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_store(self, request):
        """Get store from query params."""
        store_param = request.query_params.get('store')
        if not store_param:
            return None
        
        try:
            import uuid
            uuid.UUID(store_param)
            return Store.objects.get(id=store_param)
        except (ValueError, AttributeError):
            return Store.objects.filter(slug=store_param).first()
    
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
        today = timezone.now().date()
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
    """Export orders as CSV."""
    
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


class RevenueReportView(BaseExportView):
    """Revenue report with aggregations."""
    
    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)
        
        start_date, end_date = self.get_date_range(request)
        group_by = request.query_params.get('group_by', 'day')  # day, week, month
        
        orders = StoreOrder.objects.filter(
            store=store,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            payment_status='paid'
        )
        
        # Aggregation function based on group_by
        if group_by == 'week':
            trunc_func = TruncWeek('created_at')
        elif group_by == 'month':
            trunc_func = TruncMonth('created_at')
        else:
            trunc_func = TruncDate('created_at')
        
        # Revenue by period
        revenue_data = orders.annotate(
            period=trunc_func
        ).values('period').annotate(
            total_revenue=Sum('total'),
            order_count=Count('id'),
            avg_order_value=Avg('total'),
            total_delivery_fees=Sum('delivery_fee'),
            total_discounts=Sum('discount')
        ).order_by('period')
        
        # Summary
        summary = orders.aggregate(
            total_revenue=Sum('total'),
            total_orders=Count('id'),
            avg_order_value=Avg('total'),
            total_delivery_fees=Sum('delivery_fee'),
            total_discounts=Sum('discount')
        )
        
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
        
        items = StoreOrderItem.objects.filter(
            order__store=store,
            order__created_at__date__gte=start_date,
            order__created_at__date__lte=end_date,
            order__payment_status='paid'
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
        top_customers = StoreOrder.objects.filter(
            store=store,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            payment_status='paid'
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


class DashboardStatsView(BaseExportView):
    """Dashboard statistics overview."""
    
    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)
        
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        last_7_days = today - timedelta(days=7)
        last_30_days = today - timedelta(days=30)
        
        # Today's stats
        today_orders = StoreOrder.objects.filter(
            store=store,
            created_at__date=today
        )
        today_revenue = today_orders.filter(payment_status='paid').aggregate(
            total=Sum('total')
        )['total'] or Decimal('0')
        
        # Yesterday's stats for comparison
        yesterday_orders = StoreOrder.objects.filter(
            store=store,
            created_at__date=yesterday
        )
        yesterday_revenue = yesterday_orders.filter(payment_status='paid').aggregate(
            total=Sum('total')
        )['total'] or Decimal('0')
        
        # Last 7 days
        week_orders = StoreOrder.objects.filter(
            store=store,
            created_at__date__gte=last_7_days
        )
        week_revenue = week_orders.filter(payment_status='paid').aggregate(
            total=Sum('total')
        )['total'] or Decimal('0')
        
        # Last 30 days
        month_orders = StoreOrder.objects.filter(
            store=store,
            created_at__date__gte=last_30_days
        )
        month_revenue = month_orders.filter(payment_status='paid').aggregate(
            total=Sum('total')
        )['total'] or Decimal('0')
        
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
