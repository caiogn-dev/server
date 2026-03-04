"""
Reports and analytics views for Commerce app.
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

from .models import Store, Category, Product, Customer, Order


class BaseReportView(APIView):
    """Base class for report views."""
    
    permission_classes = [IsAuthenticated]
    
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


class DashboardStatsView(BaseReportView):
    """Dashboard stats overview."""
    
    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)
        
        today = timezone.now().date()
        
        # Today's stats
        today_orders = Order.objects.filter(
            store=store,
            created_at__date=today
        )
        today_revenue = today_orders.filter(
            payment_status='paid'
        ).aggregate(total=Sum('total'))['total'] or 0
        
        # Yesterday for comparison
        yesterday = today - timedelta(days=1)
        yesterday_revenue = Order.objects.filter(
            store=store,
            created_at__date=yesterday,
            payment_status='paid'
        ).aggregate(total=Sum('total'))['total'] or 0
        
        revenue_change = today_revenue - yesterday_revenue
        revenue_change_percent = (
            (revenue_change / yesterday_revenue * 100) 
            if yesterday_revenue > 0 else 0
        )
        
        # Week stats
        week_start = today - timedelta(days=today.weekday())
        week_orders = Order.objects.filter(
            store=store,
            created_at__date__gte=week_start
        )
        week_revenue = week_orders.filter(
            payment_status='paid'
        ).aggregate(total=Sum('total'))['total'] or 0
        
        # Month stats
        month_start = today.replace(day=1)
        month_orders = Order.objects.filter(
            store=store,
            created_at__date__gte=month_start
        )
        month_revenue = month_orders.filter(
            payment_status='paid'
        ).aggregate(total=Sum('total'))['total'] or 0
        
        # Alerts
        pending_orders = Order.objects.filter(
            store=store,
            status='pending'
        ).count()
        
        low_stock_products = Product.objects.filter(
            store=store,
            stock_quantity__lte=10,
            is_active=True
        ).count()
        
        return Response({
            'today': {
                'orders': today_orders.count(),
                'revenue': float(today_revenue),
                'revenue_change': float(revenue_change),
                'revenue_change_percent': round(revenue_change_percent, 2)
            },
            'week': {
                'orders': week_orders.count(),
                'revenue': float(week_revenue),
                'avg_daily_revenue': float(week_revenue / (today.weekday() + 1)) if today.weekday() >= 0 else 0
            },
            'month': {
                'orders': month_orders.count(),
                'revenue': float(month_revenue),
                'avg_daily_revenue': float(month_revenue / today.day) if today.day > 0 else 0
            },
            'alerts': {
                'pending_orders': pending_orders,
                'low_stock_products': low_stock_products
            },
            'generated_at': timezone.now().isoformat()
        })


class RevenueReportView(BaseReportView):
    """Revenue report with aggregations."""
    
    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)
        
        start_date, end_date = self.get_date_range(request)
        group_by = request.query_params.get('group_by', 'day')  # day, week, month
        
        orders = Order.objects.filter(
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


class ProductsReportView(BaseReportView):
    """Products performance report."""
    
    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)
        
        start_date, end_date = self.get_date_range(request)
        
        # Get top selling products
        from ..models import OrderItem
        top_products = OrderItem.objects.filter(
            order__store=store,
            order__created_at__date__gte=start_date,
            order__created_at__date__lte=end_date
        ).values(
            'product_id', 'product_name'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('total_price'),
            order_count=Count('order', distinct=True)
        ).order_by('-total_quantity')[:20]
        
        return Response({
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'top_products': [
                {
                    'product_id': item['product_id'],
                    'product_name': item['product_name'],
                    'total_quantity': item['total_quantity'],
                    'total_revenue': float(item['total_revenue'] or 0),
                    'order_count': item['order_count'],
                    'current_stock': None  # Would need to fetch from Product model
                }
                for item in top_products
            ]
        })


class StockReportView(BaseReportView):
    """Stock/inventory report."""
    
    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)
        
        low_stock_threshold = int(request.query_params.get('low_stock', 10))
        
        products = Product.objects.filter(store=store)
        
        total_products = products.count()
        low_stock_products = products.filter(
            stock_quantity__gt=0,
            stock_quantity__lte=low_stock_threshold
        )
        out_of_stock_products = products.filter(stock_quantity=0)
        
        return Response({
            'summary': {
                'total_products': total_products,
                'low_stock_count': low_stock_products.count(),
                'out_of_stock_count': out_of_stock_products.count(),
                'low_stock_threshold': low_stock_threshold
            },
            'low_stock_products': [
                {
                    'id': str(p.id),
                    'name': p.name,
                    'sku': p.sku,
                    'stock_quantity': p.stock_quantity,
                    'price': float(p.price),
                    'status': 'low_stock',
                    'category': p.category.name if p.category else None
                }
                for p in low_stock_products[:50]
            ],
            'out_of_stock_products': [
                {
                    'id': str(p.id),
                    'name': p.name,
                    'sku': p.sku,
                    'category': p.category.name if p.category else None
                }
                for p in out_of_stock_products[:50]
            ]
        })


class CustomersReportView(BaseReportView):
    """Customers report."""
    
    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)
        
        start_date, end_date = self.get_date_range(request)
        
        customers = Customer.objects.filter(store=store)
        
        # New customers in period
        new_customers = customers.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).count()
        
        total_customers = customers.count()
        
        # Top customers by spending
        top_customers = customers.annotate(
            total_spent=Sum('orders__total'),
            order_count=Count('orders')
        ).filter(
            total_spent__gt=0
        ).order_by('-total_spent')[:20]
        
        return Response({
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'summary': {
                'total_customers': total_customers,
                'new_customers': new_customers,
                'returning_customers': total_customers - new_customers,
                'retention_rate': round(
                    (total_customers - new_customers) / total_customers * 100, 2
                ) if total_customers > 0 else 0
            },
            'top_customers': [
                {
                    'email': c.email or '',
                    'name': c.name or '',
                    'phone': c.phone or '',
                    'total_spent': float(c.total_spent or 0),
                    'order_count': c.order_count,
                    'avg_order_value': float(c.total_spent or 0) / c.order_count if c.order_count > 0 else 0
                }
                for c in top_customers
            ]
        })


class OrdersExportView(BaseReportView):
    """Export orders as CSV."""
    
    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Store parameter required'}, status=400)
        
        start_date, end_date = self.get_date_range(request)
        
        orders = Order.objects.filter(
            store=store,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).select_related('customer').prefetch_related('items').order_by('-created_at')
        
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
                order.get_status_display() if hasattr(order, 'get_status_display') else order.status,
                order.get_payment_status_display() if hasattr(order, 'get_payment_status_display') else order.payment_status,
                order.get_delivery_method_display() if hasattr(order, 'get_delivery_method_display') else order.delivery_method,
                float(order.subtotal),
                float(order.delivery_fee) if order.delivery_fee else 0,
                float(order.discount) if order.discount else 0,
                float(order.total),
                items
            ])
        
        output.seek(0)
        response = HttpResponse(output.read(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="pedidos_{store.slug}_{start_date}_{end_date}.csv"'
        return response
