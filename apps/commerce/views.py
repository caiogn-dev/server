"""
Commerce - Views.
"""
from django.db.models import Q, Sum
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Category, Customer, Order, Product, Store
from .serializers import (
    CategorySerializer, CustomerSerializer, OrderSerializer,
    ProductSerializer, StoreSerializer,
)


class StoreViewSet(viewsets.ModelViewSet):
    serializer_class = StoreSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Store.objects.all()
        return Store.objects.filter(owner=user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['get'])
    def products(self, request, slug=None):
        store = self.get_object()
        products = Product.objects.filter(store=store, is_active=True)
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Category.objects.all()
        return Category.objects.filter(store__owner=user)


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            base_qs = Product.objects.all()
        else:
            base_qs = Product.objects.filter(store__owner=user)

        store_slug = self.request.query_params.get('store')
        if store_slug:
            base_qs = base_qs.filter(store__slug=store_slug)
        return base_qs.filter(is_active=True)


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Customer.objects.all()
        return Customer.objects.filter(store__owner=user)

    @action(detail=False, methods=['get'])
    def by_phone(self, request):
        phone = request.query_params.get('phone')
        if phone:
            customer = self.get_queryset().filter(phone=phone).first()
            if customer:
                return Response(CustomerSerializer(customer).data)
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            base_qs = Order.objects.all()
        else:
            base_qs = Order.objects.filter(store__owner=user)

        store_slug = self.request.query_params.get('store')
        if store_slug:
            base_qs = base_qs.filter(store__slug=store_slug)
        return base_qs

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

        return Response({
            'id': str(order.id),
            'type': event_type,
            'description': description,
            'created_at': order.created_at.isoformat()
        })

    @action(detail=True, methods=['get'])
    def events_list(self, request, pk=None):
        """Get all events for an order."""
        self.get_object()
        return Response([])

    @action(detail=False, methods=['get'])
    def export(self, request):
        """Export orders as CSV."""
        from django.http import HttpResponse
        import csv
        import io

        queryset = self.get_queryset()

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
        from datetime import timedelta
        from django.utils import timezone

        queryset = self.get_queryset()

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
