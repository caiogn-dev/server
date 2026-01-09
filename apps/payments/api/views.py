"""
Payment API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from ..models import Payment, PaymentGateway
from ..services import PaymentService
from .serializers import (
    PaymentSerializer,
    PaymentGatewaySerializer,
    CreatePaymentSerializer,
    ProcessPaymentSerializer,
    ConfirmPaymentSerializer,
    FailPaymentSerializer,
    RefundPaymentSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(summary="List payments"),
    retrieve=extend_schema(summary="Get payment details"),
)
class PaymentViewSet(viewsets.ModelViewSet):
    """ViewSet for Payment management."""
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['order', 'status', 'payment_method', 'gateway']

    def get_queryset(self):
        return Payment.objects.select_related('order', 'gateway').filter(is_active=True)

    @extend_schema(
        summary="Create payment",
        request=CreatePaymentSerializer,
        responses={201: PaymentSerializer}
    )
    def create(self, request, *args, **kwargs):
        """Create a new payment."""
        serializer = CreatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = PaymentService()
        payment = service.create_payment(**serializer.validated_data)
        
        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Process payment",
        request=ProcessPaymentSerializer,
        responses={200: PaymentSerializer}
    )
    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """Process a payment."""
        serializer = ProcessPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = PaymentService()
        payment = service.process_payment(
            str(pk),
            serializer.validated_data.get('gateway_type')
        )
        return Response(PaymentSerializer(payment).data)

    @extend_schema(
        summary="Confirm payment",
        request=ConfirmPaymentSerializer,
        responses={200: PaymentSerializer}
    )
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm a payment as completed."""
        serializer = ConfirmPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = PaymentService()
        payment = service.confirm_payment(
            str(pk),
            serializer.validated_data.get('external_id', ''),
            serializer.validated_data.get('gateway_response')
        )
        return Response(PaymentSerializer(payment).data)

    @extend_schema(
        summary="Fail payment",
        request=FailPaymentSerializer,
        responses={200: PaymentSerializer}
    )
    @action(detail=True, methods=['post'])
    def fail(self, request, pk=None):
        """Mark a payment as failed."""
        serializer = FailPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = PaymentService()
        payment = service.fail_payment(
            str(pk),
            serializer.validated_data['error_code'],
            serializer.validated_data['error_message'],
            serializer.validated_data.get('gateway_response')
        )
        return Response(PaymentSerializer(payment).data)

    @extend_schema(
        summary="Cancel payment",
        responses={200: PaymentSerializer}
    )
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a payment."""
        service = PaymentService()
        payment = service.cancel_payment(str(pk))
        return Response(PaymentSerializer(payment).data)

    @extend_schema(
        summary="Refund payment",
        request=RefundPaymentSerializer,
        responses={200: PaymentSerializer}
    )
    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """Refund a payment."""
        serializer = RefundPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = PaymentService()
        payment = service.refund_payment(
            str(pk),
            float(serializer.validated_data['amount']) if serializer.validated_data.get('amount') else None,
            serializer.validated_data.get('reason', '')
        )
        return Response(PaymentSerializer(payment).data)

    @extend_schema(
        summary="Get order payments",
        responses={200: PaymentSerializer(many=True)}
    )
    @action(detail=False, methods=['get'])
    def by_order(self, request):
        """Get payments by order."""
        order_id = request.query_params.get('order_id')
        
        if not order_id:
            return Response(
                {'error': 'order_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = PaymentService()
        payments = service.list_order_payments(order_id)
        return Response(PaymentSerializer(payments, many=True).data)


@extend_schema_view(
    list=extend_schema(summary="List payment gateways"),
    retrieve=extend_schema(summary="Get payment gateway details"),
    create=extend_schema(summary="Create payment gateway"),
    update=extend_schema(summary="Update payment gateway"),
    partial_update=extend_schema(summary="Partial update payment gateway"),
    destroy=extend_schema(summary="Delete payment gateway"),
)
class PaymentGatewayViewSet(viewsets.ModelViewSet):
    """ViewSet for Payment Gateway management."""
    serializer_class = PaymentGatewaySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['gateway_type', 'is_enabled']

    def get_queryset(self):
        return PaymentGateway.objects.filter(is_active=True)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()
