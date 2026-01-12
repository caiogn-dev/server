"""
Unified API views for aggregating data across multiple systems.
Provides a single interface for the dashboard to access orders, stats, and products.

This module aggregates data from:
- apps.stores.models.StoreOrder (unified system - primary)
- apps.orders.models.Order (legacy orders system)
"""
import logging
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import TruncDate
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class UnifiedOrdersViewSet(viewsets.ViewSet):
    """
    Unified orders API that aggregates orders from:
    - apps.stores.models.StoreOrder (multi-store orders - primary)
    - apps.orders.models.Order (legacy orders)
    
    All orders are normalized to a common format.
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """
        List all orders, optionally filtered by store.
        
        Query params:
        - store: Filter by store ID
        - status: Filter by order status
        - date_from: Filter orders from this date
        - date_to: Filter orders until this date
        - search: Search by customer name, email, or order number
        - page: Page number
        - page_size: Items per page (default 20)
        """
        store_id = request.query_params.get('store')
        status_filter = request.query_params.get('status')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        search = request.query_params.get('search')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        
        orders = []
        
        # Get StoreOrders
        try:
            from apps.stores.models import StoreOrder
            store_orders = StoreOrder.objects.all()
            
            if store_id:
                store_orders = store_orders.filter(store_id=store_id)
            if status_filter:
                store_orders = store_orders.filter(status=status_filter)
            if date_from:
                store_orders = store_orders.filter(created_at__date__gte=date_from)
            if date_to:
                store_orders = store_orders.filter(created_at__date__lte=date_to)
            if search:
                store_orders = store_orders.filter(
                    Q(customer_name__icontains=search) |
                    Q(customer_email__icontains=search) |
                    Q(order_number__icontains=search)
                )
            
            for order in store_orders.select_related('store')[:500]:
                orders.append({
                    'id': str(order.id),
                    'source': 'stores',
                    'store_id': str(order.store_id) if order.store_id else None,
                    'store_name': order.store.name if order.store else None,
                    'order_number': order.order_number,
                    'customer_name': order.customer_name,
                    'customer_email': order.customer_email,
                    'customer_phone': order.customer_phone,
                    'status': order.status,
                    'payment_status': order.payment_status,
                    'subtotal': float(order.subtotal),
                    'discount': float(order.discount),
                    'delivery_fee': float(order.delivery_fee),
                    'total': float(order.total),
                    'delivery_method': order.delivery_method,
                    'delivery_address': order.delivery_address,
                    'items_count': order.items.count(),
                    'created_at': order.created_at.isoformat(),
                    'updated_at': order.updated_at.isoformat(),
                })
        except Exception as e:
            logger.warning(f"Could not fetch StoreOrders: {e}")
        
        # Get legacy Orders
        try:
            from apps.orders.models import Order
            
            legacy_orders = Order.objects.all()
            
            if status_filter:
                legacy_orders = legacy_orders.filter(status=status_filter)
            if date_from:
                legacy_orders = legacy_orders.filter(created_at__date__gte=date_from)
            if date_to:
                legacy_orders = legacy_orders.filter(created_at__date__lte=date_to)
            if search:
                legacy_orders = legacy_orders.filter(
                    Q(customer_name__icontains=search) |
                    Q(customer_email__icontains=search) |
                    Q(order_number__icontains=search)
                )
            
            for order in legacy_orders[:500]:
                orders.append({
                    'id': str(order.id),
                    'source': 'orders',
                    'store_id': None,
                    'store_name': 'Sistema Legado',
                    'order_number': order.order_number,
                    'customer_name': order.customer_name,
                    'customer_email': order.customer_email,
                    'customer_phone': order.customer_phone,
                    'status': order.status,
                    'payment_status': order.payment_status,
                    'subtotal': float(order.subtotal),
                    'discount': float(order.discount),
                    'delivery_fee': float(order.shipping_cost),
                    'total': float(order.total),
                    'delivery_method': order.shipping_method,
                    'delivery_address': order.shipping_address,
                    'items_count': order.items.count() if hasattr(order, 'items') else 0,
                    'created_at': order.created_at.isoformat(),
                    'updated_at': order.updated_at.isoformat(),
                })
        except Exception as e:
            logger.warning(f"Could not fetch legacy Orders: {e}")
        
        # Sort by created_at descending
        orders.sort(key=lambda x: x['created_at'], reverse=True)
        
        # Paginate
        total = len(orders)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_orders = orders[start:end]
        
        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
            'results': paginated_orders,
        })
    
    def retrieve(self, request, pk=None):
        """
        Get a single order by ID.
        Searches in both StoreOrders and legacy Orders.
        """
        # Try StoreOrder first
        try:
            from apps.stores.models import StoreOrder
            order = StoreOrder.objects.select_related('store').get(id=pk)
            return Response({
                'id': str(order.id),
                'source': 'stores',
                'store_id': str(order.store_id) if order.store_id else None,
                'store_name': order.store.name if order.store else None,
                'order_number': order.order_number,
                'customer_name': order.customer_name,
                'customer_email': order.customer_email,
                'customer_phone': order.customer_phone,
                'status': order.status,
                'payment_status': order.payment_status,
                'subtotal': float(order.subtotal),
                'discount': float(order.discount),
                'delivery_fee': float(order.delivery_fee),
                'total': float(order.total),
                'delivery_method': order.delivery_method,
                'delivery_address': order.delivery_address,
                'items_count': order.items.count(),
                'created_at': order.created_at.isoformat(),
                'updated_at': order.updated_at.isoformat(),
            })
        except:
            pass
        
        # Try legacy Order
        try:
            from apps.orders.models import Order
            order = Order.objects.get(id=pk)
            return Response({
                'id': str(order.id),
                'source': 'orders',
                'store_id': None,
                'store_name': 'Sistema Legado',
                'order_number': order.order_number,
                'customer_name': order.customer_name,
                'customer_email': order.customer_email,
                'customer_phone': order.customer_phone,
                'status': order.status,
                'payment_status': order.payment_status,
                'subtotal': float(order.subtotal),
                'discount': float(order.discount),
                'delivery_fee': float(order.shipping_cost),
                'total': float(order.total),
                'delivery_method': order.shipping_method,
                'delivery_address': order.shipping_address,
                'items_count': order.items.count() if hasattr(order, 'items') else 0,
                'created_at': order.created_at.isoformat(),
                'updated_at': order.updated_at.isoformat(),
            })
        except:
            pass
        
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['patch'], url_path='status')
    def update_status(self, request, pk=None):
        """
        Update order status.
        
        Body:
        - status: New status
        - tracking_code: (optional) Tracking code for shipped orders
        - carrier: (optional) Carrier name
        - payment_reference: (optional) Payment reference
        - reason: (optional) Cancellation reason
        """
        new_status = request.data.get('status')
        if not new_status:
            return Response({'error': 'Status is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Try StoreOrder first
        try:
            from apps.stores.models import StoreOrder
            order = StoreOrder.objects.get(id=pk)
            
            order.status = new_status
            
            # Handle additional fields based on status
            if new_status == 'shipped':
                if request.data.get('tracking_code'):
                    order.tracking_code = request.data.get('tracking_code')
                if request.data.get('carrier'):
                    order.carrier = request.data.get('carrier')
            elif new_status == 'paid':
                order.payment_status = 'paid'
                if request.data.get('payment_reference'):
                    order.payment_reference = request.data.get('payment_reference')
            elif new_status == 'cancelled':
                if request.data.get('reason'):
                    order.cancellation_reason = request.data.get('reason')
            
            order.save()
            
            return Response({
                'id': str(order.id),
                'source': 'stores',
                'status': order.status,
                'payment_status': order.payment_status,
                'message': f'Status updated to {new_status}'
            })
        except:
            pass
        
        # Try legacy Order
        try:
            from apps.orders.models import Order
            order = Order.objects.get(id=pk)
            
            order.status = new_status
            
            if new_status == 'paid':
                order.payment_status = 'paid'
            
            order.save()
            
            return Response({
                'id': str(order.id),
                'source': 'orders',
                'status': order.status,
                'payment_status': order.payment_status,
                'message': f'Status updated to {new_status}'
            })
        except:
            pass
        
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Get unified order statistics.
        
        Query params:
        - store: Filter by store ID
        - period: 'today', 'week', 'month', 'year' (default: 'month')
        """
        store_id = request.query_params.get('store')
        period = request.query_params.get('period', 'month')
        
        now = timezone.now()
        today = now.date()
        
        if period == 'today':
            date_from = today
        elif period == 'week':
            date_from = today - timedelta(days=7)
        elif period == 'year':
            date_from = today - timedelta(days=365)
        else:  # month
            date_from = today - timedelta(days=30)
        
        stats = {
            'total_orders': 0,
            'total_revenue': Decimal('0.00'),
            'orders_today': 0,
            'revenue_today': Decimal('0.00'),
            'orders_period': 0,
            'revenue_period': Decimal('0.00'),
            'average_order_value': Decimal('0.00'),
            'pending_orders': 0,
            'processing_orders': 0,
            'completed_orders': 0,
            'cancelled_orders': 0,
            'by_source': {},
            'daily_orders': [],
        }
        
        # StoreOrders stats
        try:
            from apps.stores.models import StoreOrder
            
            queryset = StoreOrder.objects.all()
            if store_id:
                queryset = queryset.filter(store_id=store_id)
            
            paid_orders = queryset.filter(payment_status='paid')
            
            store_stats = paid_orders.aggregate(
                total=Sum('total'),
                count=Count('id')
            )
            
            stats['total_orders'] += store_stats['count'] or 0
            stats['total_revenue'] += store_stats['total'] or Decimal('0.00')
            
            # Today
            today_stats = paid_orders.filter(created_at__date=today).aggregate(
                total=Sum('total'),
                count=Count('id')
            )
            stats['orders_today'] += today_stats['count'] or 0
            stats['revenue_today'] += today_stats['total'] or Decimal('0.00')
            
            # Period
            period_stats = paid_orders.filter(created_at__date__gte=date_from).aggregate(
                total=Sum('total'),
                count=Count('id')
            )
            stats['orders_period'] += period_stats['count'] or 0
            stats['revenue_period'] += period_stats['total'] or Decimal('0.00')
            
            # Status counts
            status_counts = queryset.values('status').annotate(count=Count('id'))
            for sc in status_counts:
                if sc['status'] == 'pending':
                    stats['pending_orders'] += sc['count']
                elif sc['status'] in ['processing', 'preparing', 'ready']:
                    stats['processing_orders'] += sc['count']
                elif sc['status'] in ['completed', 'delivered']:
                    stats['completed_orders'] += sc['count']
                elif sc['status'] == 'cancelled':
                    stats['cancelled_orders'] += sc['count']
            
            stats['by_source']['stores'] = {
                'orders': store_stats['count'] or 0,
                'revenue': float(store_stats['total'] or 0)
            }
            
            # Daily orders for chart
            daily = paid_orders.filter(
                created_at__date__gte=date_from
            ).annotate(
                date=TruncDate('created_at')
            ).values('date').annotate(
                count=Count('id'),
                revenue=Sum('total')
            ).order_by('date')
            
            for d in daily:
                stats['daily_orders'].append({
                    'date': d['date'].isoformat(),
                    'count': d['count'],
                    'revenue': float(d['revenue'] or 0),
                    'source': 'stores'
                })
                
        except Exception as e:
            logger.warning(f"Could not get StoreOrder stats: {e}")
        
        # Calculate average
        if stats['total_orders'] > 0:
            stats['average_order_value'] = stats['total_revenue'] / stats['total_orders']
        
        # Convert Decimals to float for JSON
        stats['total_revenue'] = float(stats['total_revenue'])
        stats['revenue_today'] = float(stats['revenue_today'])
        stats['revenue_period'] = float(stats['revenue_period'])
        stats['average_order_value'] = float(stats['average_order_value'])
        
        return Response(stats)


class UnifiedStatsView(APIView):
    """
    Unified statistics view for dashboard overview.
    Aggregates stats from all systems.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        Get unified dashboard statistics.
        
        Query params:
        - store: Filter by store ID
        """
        store_id = request.query_params.get('store')
        
        now = timezone.now()
        today = now.date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        stats = {
            'orders': {
                'total': 0,
                'today': 0,
                'this_week': 0,
                'this_month': 0,
                'pending': 0,
            },
            'revenue': {
                'total': 0.0,
                'today': 0.0,
                'this_week': 0.0,
                'this_month': 0.0,
            },
            'customers': {
                'total': 0,
                'new_this_month': 0,
            },
            'products': {
                'total': 0,
                'active': 0,
                'low_stock': 0,
            },
        }
        
        # StoreOrders
        try:
            from apps.stores.models import StoreOrder, StoreProduct, StoreCustomer
            
            orders = StoreOrder.objects.all()
            if store_id:
                orders = orders.filter(store_id=store_id)
            
            stats['orders']['total'] += orders.count()
            stats['orders']['today'] += orders.filter(created_at__date=today).count()
            stats['orders']['this_week'] += orders.filter(created_at__date__gte=week_ago).count()
            stats['orders']['this_month'] += orders.filter(created_at__date__gte=month_ago).count()
            stats['orders']['pending'] += orders.filter(status='pending').count()
            
            paid = orders.filter(payment_status='paid')
            revenue = paid.aggregate(total=Sum('total'))['total'] or Decimal('0')
            stats['revenue']['total'] += float(revenue)
            stats['revenue']['today'] += float(paid.filter(created_at__date=today).aggregate(total=Sum('total'))['total'] or 0)
            stats['revenue']['this_week'] += float(paid.filter(created_at__date__gte=week_ago).aggregate(total=Sum('total'))['total'] or 0)
            stats['revenue']['this_month'] += float(paid.filter(created_at__date__gte=month_ago).aggregate(total=Sum('total'))['total'] or 0)
            
            # Products
            products = StoreProduct.objects.all()
            if store_id:
                products = products.filter(store_id=store_id)
            stats['products']['total'] += products.count()
            stats['products']['active'] += products.filter(status='active').count()
            stats['products']['low_stock'] += products.filter(
                track_stock=True,
                stock_quantity__lte=10
            ).count()
            
            # Customers
            customers = StoreCustomer.objects.all()
            if store_id:
                customers = customers.filter(store_id=store_id)
            stats['customers']['total'] += customers.count()
            stats['customers']['new_this_month'] += customers.filter(created_at__date__gte=month_ago).count()
            
        except Exception as e:
            logger.warning(f"Could not get Store stats: {e}")
        
        return Response(stats)
