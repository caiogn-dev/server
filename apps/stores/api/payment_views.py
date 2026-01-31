"""
Payment API Views.

ViewSets for StorePayment and StorePaymentGateway.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from apps.stores.models import (
    StorePayment,
    StorePaymentGateway,
    StorePaymentWebhookEvent,
)
from apps.stores.services import PaymentService, get_payment_service
from .payment_serializers import (
    StorePaymentSerializer,
    StorePaymentListSerializer,
    StorePaymentGatewaySerializer,
    StorePaymentGatewayListSerializer,
    StorePaymentWebhookEventSerializer,
    CreatePaymentSerializer,
    ProcessPaymentSerializer,
    ConfirmPaymentSerializer,
    FailPaymentSerializer,
    RefundPaymentSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(summary="List payment gateways", description="Get all payment gateways for the authenticated user's stores"),
    retrieve=extend_schema(summary="Get payment gateway details"),
    create=extend_schema(summary="Create payment gateway", request=StorePaymentGatewaySerializer),
    update=extend_schema(summary="Update payment gateway"),
    partial_update=extend_schema(summary="Partial update payment gateway"),
    destroy=extend_schema(summary="Delete payment gateway"),
)
class StorePaymentGatewayViewSet(viewsets.ModelViewSet):
    """ViewSet for managing payment gateways."""
    
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['store', 'gateway_type', 'is_enabled', 'is_default']
    
    def get_queryset(self):
        user = self.request.user
        queryset = StorePaymentGateway.objects.select_related('store')
        
        if not user.is_staff:
            queryset = queryset.filter(
                store__owner=user
            ) | queryset.filter(
                store__staff=user
            )
        
        # Filter by store if provided
        store_id = self.request.query_params.get('store')
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        
        return queryset.distinct()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return StorePaymentGatewayListSerializer
        return StorePaymentGatewaySerializer
    
    def perform_destroy(self, instance):
        """Soft delete - mark as inactive."""
        instance.is_active = False
        instance.is_enabled = False
        instance.save()
    
    @extend_schema(summary="Set as default gateway")
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set this gateway as the default for its store."""
        gateway = self.get_object()
        gateway.is_default = True
        gateway.save()
        return Response(StorePaymentGatewaySerializer(gateway).data)


@extend_schema_view(
    list=extend_schema(summary="List payments", description="Get all payments for the authenticated user's stores"),
    retrieve=extend_schema(summary="Get payment details"),
    create=extend_schema(summary="Create payment", request=CreatePaymentSerializer),
)
class StorePaymentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing payments."""
    
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['order', 'status', 'payment_method', 'gateway']
    lookup_field = 'pk'
    
    def get_queryset(self):
        user = self.request.user
        queryset = StorePayment.objects.select_related(
            'order', 'order__store', 'gateway'
        )
        
        if not user.is_staff:
            queryset = queryset.filter(
                order__store__owner=user
            ) | queryset.filter(
                order__store__staff=user
            )
        
        # Filter by store if provided
        store_id = self.request.query_params.get('store')
        if store_id:
            queryset = queryset.filter(order__store_id=store_id)
        
        # Filter by order_number if provided
        order_number = self.request.query_params.get('order_number')
        if order_number:
            queryset = queryset.filter(order__order_number__icontains=order_number)
        
        return queryset.distinct().order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action == 'list':
            return StorePaymentListSerializer
        return StorePaymentSerializer
    
    def create(self, request, *args, **kwargs):
        """Create a new payment."""
        serializer = CreatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = get_payment_service()
        
        try:
            payment = service.create_payment(
                order_id=str(serializer.validated_data['order_id']),
                gateway_id=str(serializer.validated_data['gateway_id']) if serializer.validated_data.get('gateway_id') else None,
                amount=serializer.validated_data.get('amount'),
                payment_method=serializer.validated_data.get('payment_method', ''),
                payer_email=serializer.validated_data.get('payer_email', ''),
                payer_name=serializer.validated_data.get('payer_name', ''),
                payer_document=serializer.validated_data.get('payer_document', ''),
                metadata=serializer.validated_data.get('metadata', {}),
            )
            
            return Response(
                StorePaymentSerializer(payment).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(summary="Process payment", request=ProcessPaymentSerializer)
    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """Process a payment through the gateway."""
        payment = self.get_object()
        
        serializer = ProcessPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = get_payment_service()
        
        try:
            payment = service.process_payment(
                payment_id=str(payment.id),
                gateway_type=serializer.validated_data.get('gateway_type')
            )
            return Response(StorePaymentSerializer(payment).data)
        except Exception as e:
            logger.error(f"Error processing payment {payment.id}: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(summary="Confirm payment", request=ConfirmPaymentSerializer)
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm a payment as completed."""
        payment = self.get_object()
        
        serializer = ConfirmPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = get_payment_service()
        
        try:
            payment = service.confirm_payment(
                payment_id=str(payment.id),
                external_id=serializer.validated_data.get('external_id', ''),
                gateway_response=serializer.validated_data.get('gateway_response', {})
            )
            return Response(StorePaymentSerializer(payment).data)
        except Exception as e:
            logger.error(f"Error confirming payment {payment.id}: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(summary="Fail payment", request=FailPaymentSerializer)
    @action(detail=True, methods=['post'])
    def fail(self, request, pk=None):
        """Mark a payment as failed."""
        payment = self.get_object()
        
        serializer = FailPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = get_payment_service()
        
        try:
            payment = service.fail_payment(
                payment_id=str(payment.id),
                error_code=serializer.validated_data['error_code'],
                error_message=serializer.validated_data['error_message'],
                gateway_response=serializer.validated_data.get('gateway_response', {})
            )
            return Response(StorePaymentSerializer(payment).data)
        except Exception as e:
            logger.error(f"Error failing payment {payment.id}: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(summary="Cancel payment")
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a payment."""
        payment = self.get_object()
        
        service = get_payment_service()
        
        try:
            payment = service.cancel_payment(str(payment.id))
            return Response(StorePaymentSerializer(payment).data)
        except Exception as e:
            logger.error(f"Error cancelling payment {payment.id}: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(summary="Refund payment", request=RefundPaymentSerializer)
    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """Refund a payment (partial or full)."""
        payment = self.get_object()
        
        serializer = RefundPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = get_payment_service()
        
        try:
            payment = service.refund_payment(
                payment_id=str(payment.id),
                amount=serializer.validated_data.get('amount'),
                reason=serializer.validated_data.get('reason', '')
            )
            return Response(StorePaymentSerializer(payment).data)
        except Exception as e:
            logger.error(f"Error refunding payment {payment.id}: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(summary="Get payments by order")
    @action(detail=False, methods=['get'])
    def by_order(self, request):
        """Get all payments for a specific order."""
        order_id = request.query_params.get('order_id')
        
        if not order_id:
            return Response(
                {'error': 'order_id query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = get_payment_service()
        payments = service.list_order_payments(order_id)
        
        serializer = StorePaymentListSerializer(payments, many=True)
        return Response(serializer.data)
    
    @extend_schema(summary="Get payment statistics")
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get payment statistics."""
        from django.db.models import Sum, Count, Q
        from django.utils import timezone
        from datetime import timedelta
        
        queryset = self.get_queryset()
        
        # Time filters
        period = request.query_params.get('period', 'month')
        now = timezone.now()
        
        if period == 'today':
            date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'week':
            date_from = now - timedelta(days=7)
        elif period == 'year':
            date_from = now - timedelta(days=365)
        else:  # month
            date_from = now - timedelta(days=30)
        
        queryset = queryset.filter(created_at__gte=date_from)
        
        # Calculate stats
        total_payments = queryset.count()
        
        status_counts = queryset.values('status').annotate(
            count=Count('id'),
            total=Sum('amount')
        )
        
        completed_stats = queryset.filter(
            status=StorePayment.PaymentStatus.COMPLETED
        ).aggregate(
            count=Count('id'),
            total_amount=Sum('amount'),
            total_fees=Sum('fee'),
            total_net=Sum('net_amount')
        )
        
        return Response({
            'period': period,
            'date_from': date_from.isoformat(),
            'total_payments': total_payments,
            'status_breakdown': list(status_counts),
            'completed': {
                'count': completed_stats['count'] or 0,
                'amount': str(completed_stats['total_amount'] or 0),
                'fees': str(completed_stats['total_fees'] or 0),
                'net_amount': str(completed_stats['total_net'] or 0),
            }
        })


class StorePaymentWebhookEventViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing payment webhook events (read-only)."""
    
    permission_classes = [IsAuthenticated]
    serializer_class = StorePaymentWebhookEventSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['gateway', 'payment', 'event_type', 'processing_status']
    
    def get_queryset(self):
        user = self.request.user
        queryset = StorePaymentWebhookEvent.objects.select_related(
            'gateway', 'payment', 'order'
        )
        
        if not user.is_staff:
            queryset = queryset.filter(
                gateway__store__owner=user
            ) | queryset.filter(
                gateway__store__staff=user
            )
        
        return queryset.distinct().order_by('-created_at')
