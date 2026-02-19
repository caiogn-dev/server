"""
Order management API views.
"""
import logging
import uuid as uuid_module
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q, Sum, Count
from django.utils import timezone
from datetime import timedelta
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.stores.models import Store, StoreOrder, StoreOrderItem, StoreCustomer
from ..serializers import (
    StoreOrderSerializer, StoreOrderCreateSerializer, StoreOrderUpdateSerializer,
    StoreCustomerSerializer
)
from .base import IsStoreOwnerOrStaff, filter_by_store

logger = logging.getLogger(__name__)


class StoreOrderViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store orders."""
    
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        queryset = StoreOrder.objects.all()
        
        if store_param:
            try:
                uuid_module.UUID(store_param)
                queryset = queryset.filter(store_id=store_param)
            except (ValueError, AttributeError):
                queryset = queryset.filter(store__slug=store_param)
        else:
            user = self.request.user
            if not user.is_staff:
                queryset = queryset.filter(
                    Q(store__owner=user) | Q(store__staff=user)
                ).distinct()
        
        # Filters
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        payment_status = self.request.query_params.get('payment_status')
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(order_number__icontains=search) |
                Q(customer_name__icontains=search) |
                Q(customer_email__icontains=search) |
                Q(customer_phone__icontains=search)
            )
        
        return queryset.select_related(
            'store', 'customer'
        ).prefetch_related(
            'items__product',
            'combo_items__combo'
        ).order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StoreOrderCreateSerializer
        if self.action in ['update', 'partial_update']:
            return StoreOrderUpdateSerializer
        return StoreOrderSerializer
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update order status."""
        order = self.get_object()
        new_status = request.data.get('status')
        
        if not new_status:
            return Response(
                {'error': 'status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        valid_statuses = [s[0] for s in StoreOrder.OrderStatus.choices]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Valid options: {valid_statuses}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order.status = new_status
        order.save(update_fields=['status', 'updated_at'])
        
        logger.info(f"Order {order.order_number} status updated to {new_status}")
        
        # Notify via WebSocket
        self._notify_order_update(order, 'order.updated')
        
        return Response(StoreOrderSerializer(order).data)
    
    def _notify_order_update(self, order, event_type='order.update'):
        """Send WebSocket notification for order updates."""
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"store_{order.store.slug}_orders",
                    {
                        'type': event_type,
                        'order_id': str(order.id),
                        'order_number': order.order_number,
                        'status': order.status,
                        'payment_status': order.payment_status,
                        'updated_at': order.updated_at.isoformat(),
                    }
                )
                logger.info(f"WebSocket notification sent: {event_type} for order {order.order_number}")
        except Exception as e:
            logger.error(f"Error sending WebSocket notification: {e}")
    
    @action(detail=True, methods=['post'])
    def update_payment_status(self, request, pk=None):
        """Update order payment status."""
        order = self.get_object()
        new_status = request.data.get('payment_status')
        
        if not new_status:
            return Response(
                {'error': 'payment_status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        valid_statuses = [s[0] for s in StoreOrder.PaymentStatus.choices]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Valid options: {valid_statuses}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order.payment_status = new_status
        if new_status == 'paid':
            order.paid_at = timezone.now()
        order.save(update_fields=['payment_status', 'paid_at', 'updated_at'])
        
        return Response(StoreOrderSerializer(order).data)
    
    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """Mark order as paid (convenience endpoint)."""
        order = self.get_object()
        
        order.payment_status = StoreOrder.PaymentStatus.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=['payment_status', 'paid_at', 'updated_at'])
        
        logger.info(f"Order {order.order_number} marked as paid")
        
        # Notify via WebSocket
        self._notify_order_update(order, 'order.paid')
        
        return Response(StoreOrderSerializer(order).data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an order."""
        order = self.get_object()
        reason = request.data.get('reason', '')
        
        if order.status == 'cancelled':
            return Response(
                {'error': 'Order is already cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order.status = 'cancelled'
        order.notes = f"{order.notes}\n\nCancellation reason: {reason}".strip()
        order.save(update_fields=['status', 'notes', 'updated_at'])
        
        # Restore stock if needed
        if order.items.exists():
            for item in order.items.all():
                if item.product and item.product.track_stock:
                    item.product.stock_quantity += item.quantity
                    item.product.save(update_fields=['stock_quantity'])
        
        # Notify via WebSocket
        self._notify_order_update(order, 'order.cancelled')
        
        return Response(StoreOrderSerializer(order).data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get order statistics."""
        store_id = request.query_params.get('store')
        queryset = self.get_queryset()
        
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        
        now = timezone.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        stats = {
            'total': queryset.count(),
            'today': queryset.filter(created_at__gte=today).count(),
            'this_week': queryset.filter(created_at__gte=week_ago).count(),
            'this_month': queryset.filter(created_at__gte=month_ago).count(),
            'by_status': {},
            'revenue': {
                'total': queryset.filter(payment_status='paid').aggregate(
                    total=Sum('total')
                )['total'] or 0,
                'today': queryset.filter(
                    payment_status='paid', created_at__gte=today
                ).aggregate(total=Sum('total'))['total'] or 0,
            }
        }
        
        for status_choice, _ in StoreOrder.OrderStatus.choices:
            stats['by_status'][status_choice] = queryset.filter(status=status_choice).count()
        
        return Response(stats)
    
    @action(detail=False, methods=['get'])
    def by_customer(self, request):
        """Get orders by customer phone number."""
        phone = request.query_params.get('phone')
        store_id = request.query_params.get('store')
        
        if not phone:
            return Response(
                {'error': 'phone is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(customer_phone=phone)
        
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        
        return Response(StoreOrderSerializer(queryset[:20], many=True).data)


class StoreCustomerViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store customers."""
    
    serializer_class = StoreCustomerSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        queryset = StoreCustomer.objects.all()
        
        queryset, filtered = filter_by_store(queryset, store_param)
        if not filtered:
            user = self.request.user
            if not user.is_staff:
                queryset = queryset.filter(
                    Q(store__owner=user) | Q(store__staff=user)
                ).distinct()
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search) |
                Q(phone__icontains=search) |
                Q(whatsapp__icontains=search)
            )
        
        return queryset.select_related('user', 'store')
    
    @action(detail=True, methods=['post'])
    def update_stats(self, request, pk=None):
        """Recalculate customer statistics."""
        customer = self.get_object()
        customer.update_stats()
        return Response(StoreCustomerSerializer(customer).data)
