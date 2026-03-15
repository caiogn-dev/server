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

from apps.stores.models import Store, StoreOrder, StoreOrderItem, StoreCustomer
from apps.stores.services.realtime_service import broadcast_order_event
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

    def perform_create(self, serializer):
        order = serializer.save()
        self._notify_order_update(order, 'order.created')

    def update(self, request, *args, **kwargs):
        return self._update_with_full_response(request, partial=False, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return self._update_with_full_response(request, partial=True, *args, **kwargs)

    def _update_with_full_response(self, request, partial=False, *args, **kwargs):
        """Run DRF update validation but always return the full order payload."""
        instance = self.get_object()
        previous_status = instance.status
        previous_payment_status = instance.payment_status

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        instance.refresh_from_db()

        if previous_payment_status != instance.payment_status and instance.payment_status == StoreOrder.PaymentStatus.PAID:
            self._notify_order_update(instance, 'order.paid')
        elif previous_status != instance.status or previous_payment_status != instance.payment_status:
            self._notify_order_update(instance, 'order.updated')

        return Response(StoreOrderSerializer(instance).data)
    
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
    
    def _notify_order_update(self, order, event_type='order.updated'):
        """Send WebSocket notification for order updates."""
        broadcast_order_event(order, event_type=event_type)

    @action(detail=True, methods=['post'], url_path='add_tracking')
    def add_tracking(self, request, pk=None):
        """Attach tracking details and mark order as shipped."""
        order = self.get_object()
        order.tracking_code = request.data.get('tracking_code', order.tracking_code or '')
        order.tracking_url = request.data.get('tracking_url', order.tracking_url or '')
        order.carrier = request.data.get('carrier', order.carrier or '')

        if order.status not in ['shipped', 'out_for_delivery', 'delivered', 'completed']:
            order.status = 'shipped'
            if not order.shipped_at:
                order.shipped_at = timezone.now()

        order.save(update_fields=[
            'tracking_code', 'tracking_url', 'carrier',
            'status', 'shipped_at', 'updated_at'
        ])

        self._notify_order_update(order, 'order.shipped')
        return Response(StoreOrderSerializer(order).data)

    @action(detail=True, methods=['post'], url_path='add_note')
    def add_note(self, request, pk=None):
        """Append note to internal or customer notes."""
        order = self.get_object()
        note = (request.data.get('note') or '').strip()
        is_internal = request.data.get('is_internal', True)

        if not note:
            return Response(
                {'error': 'note is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        target_field = 'internal_notes' if is_internal else 'customer_notes'
        existing = getattr(order, target_field) or ''
        combined = f"{existing}\n{note}".strip() if existing else note
        setattr(order, target_field, combined)
        order.save(update_fields=[target_field, 'updated_at'])

        self._notify_order_update(order, 'order.updated')
        return Response(StoreOrderSerializer(order).data)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Return a lightweight timeline for the order."""
        order = self.get_object()
        events = [
            {
                'id': f'{order.id}-created',
                'order_id': str(order.id),
                'event_type': 'created',
                'description': f'Pedido criado com status {order.status}',
                'created_at': order.created_at.isoformat(),
            }
        ]

        if order.paid_at:
            events.append({
                'id': f'{order.id}-paid',
                'order_id': str(order.id),
                'event_type': 'payment_paid',
                'description': 'Pagamento confirmado',
                'created_at': order.paid_at.isoformat(),
            })
        if order.shipped_at:
            events.append({
                'id': f'{order.id}-shipped',
                'order_id': str(order.id),
                'event_type': 'shipped',
                'description': 'Pedido enviado',
                'created_at': order.shipped_at.isoformat(),
            })
        if order.delivered_at:
            events.append({
                'id': f'{order.id}-delivered',
                'order_id': str(order.id),
                'event_type': 'delivered',
                'description': 'Pedido entregue',
                'created_at': order.delivered_at.isoformat(),
            })
        if order.cancelled_at:
            events.append({
                'id': f'{order.id}-cancelled',
                'order_id': str(order.id),
                'event_type': 'cancelled',
                'description': 'Pedido cancelado',
                'created_at': order.cancelled_at.isoformat(),
            })

        events.sort(key=lambda event: event['created_at'], reverse=True)
        return Response(events)
    
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
