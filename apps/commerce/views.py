"""
Commerce - Views.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Store, Category, Product, Customer, Order
from .serializers import (
    StoreSerializer, CategorySerializer, ProductSerializer,
    CustomerSerializer, OrderSerializer
)


class StoreViewSet(viewsets.ModelViewSet):
    queryset = Store.objects.all()
    serializer_class = StoreSerializer
    lookup_field = 'slug'
    
    @action(detail=True, methods=['get'])
    def products(self, request, slug=None):
        store = self.get_object()
        products = Product.objects.filter(store=store, is_active=True)
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        store_slug = self.request.query_params.get('store')
        if store_slug:
            queryset = queryset.filter(store__slug=store_slug)
        return queryset.filter(is_active=True)


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    
    @action(detail=False, methods=['get'])
    def by_phone(self, request):
        phone = request.query_params.get('phone')
        if phone:
            customer = Customer.objects.filter(phone=phone).first()
            if customer:
                return Response(CustomerSerializer(customer).data)
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        store_slug = self.request.query_params.get('store')
        if store_slug:
            queryset = queryset.filter(store__slug=store_slug)
        return queryset
    
    @action(detail=True, methods=['get'])
    def payment(self, request, pk=None):
        """Get payment status for an order."""
        order = self.get_object()
        return Response({
            'status': order.payment_status,
            'payment_url': order.payment_url if hasattr(order, 'payment_url') else None
        })
    
    @action(detail=True, methods=['post'])
    def events(self, request, pk=None):
        """Add an event to the order."""
        order = self.get_object()
        event_type = request.data.get('type')
        description = request.data.get('description')
        
        # Create event logic here
        return Response({
            'id': str(order.id),
            'type': event_type,
            'description': description,
            'created_at': order.created_at.isoformat()
        })
    
    @action(detail=True, methods=['get'])
    def events_list(self, request, pk=None):
        """Get all events for an order."""
        order = self.get_object()
        # Return order events
        return Response([])
    
    @action(detail=False, methods=['get'])
    def export(self, request):
        """Export orders as CSV."""
        from django.http import HttpResponse
        import csv
        import io
        
        store_slug = request.query_params.get('store')
        queryset = self.get_queryset()
        
        if store_slug:
            queryset = queryset.filter(store__slug=store_slug)
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Number', 'Customer', 'Total', 'Status', 'Date'])
        
        for order in queryset:
            writer.writerow([
                str(order.id),
                order.order_number if hasattr(order, 'order_number') else str(order.id)[:8],
                order.customer_name if hasattr(order, 'customer_name') else '',
                float(order.total),
                order.status,
                order.created_at.strftime('%Y-%m-%d %H:%M')
            ])
        
        output.seek(0)
        response = HttpResponse(output.read(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="orders.csv"'
        return response
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get order statistics."""
        from django.db.models import Sum, Count
        from django.utils import timezone
        from datetime import timedelta
        
        store_slug = request.query_params.get('store')
        queryset = self.get_queryset()
        
        if store_slug:
            queryset = queryset.filter(store__slug=store_slug)
        
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        stats = {
            'total': queryset.count(),
            'pending': queryset.filter(status='pending').count(),
            'confirmed': queryset.filter(status='confirmed').count(),
            'delivered': queryset.filter(status='delivered').count(),
            'cancelled': queryset.filter(status='cancelled').count(),
            'revenue': float(queryset.filter(payment_status='paid').aggregate(total=Sum('total'))['total'] or 0),
            'week_orders': queryset.filter(created_at__date__gte=week_ago).count(),
            'week_revenue': float(queryset.filter(
                created_at__date__gte=week_ago,
                payment_status='paid'
            ).aggregate(total=Sum('total'))['total'] or 0)
        }
        
        return Response(stats)
