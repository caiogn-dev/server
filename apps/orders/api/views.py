"""
Order API views.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from ..models import Order, OrderItem, OrderEvent
from ..services import OrderService
from .serializers import (
    OrderSerializer,
    OrderItemSerializer,
    OrderEventSerializer,
    CreateOrderSerializer,
    AddItemSerializer,
    UpdateShippingSerializer,
    ShipOrderSerializer,
    CancelOrderSerializer,
    AddNoteSerializer,
    PaymentConfirmationSerializer,
)

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(summary="List orders"),
    retrieve=extend_schema(summary="Get order details"),
)
class OrderViewSet(viewsets.ModelViewSet):
    """ViewSet for Order management."""
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['account', 'status', 'customer_phone']

    def get_queryset(self):
        return Order.objects.select_related(
            'account', 'conversation'
        ).prefetch_related('items').filter(is_active=True)

    @extend_schema(
        summary="Create order",
        request=CreateOrderSerializer,
        responses={201: OrderSerializer}
    )
    def create(self, request, *args, **kwargs):
        """Create a new order."""
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = OrderService()
        order = service.create_order(**serializer.validated_data)
        
        return Response(
            OrderSerializer(order).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Confirm order",
        responses={200: OrderSerializer}
    )
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm an order."""
        service = OrderService()
        order = service.confirm_order(str(pk), request.user)
        return Response(OrderSerializer(order).data)

    @extend_schema(
        summary="Mark order as awaiting payment",
        responses={200: OrderSerializer}
    )
    @action(detail=True, methods=['post'])
    def awaiting_payment(self, request, pk=None):
        """Mark order as awaiting payment."""
        service = OrderService()
        order = service.mark_awaiting_payment(str(pk), request.user)
        return Response(OrderSerializer(order).data)

    @extend_schema(
        summary="Mark order as paid",
        request=PaymentConfirmationSerializer,
        responses={200: OrderSerializer}
    )
    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """Mark order as paid."""
        serializer = PaymentConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = OrderService()
        order = service.mark_paid(
            str(pk),
            serializer.validated_data.get('payment_reference', ''),
            request.user
        )
        return Response(OrderSerializer(order).data)

    @extend_schema(
        summary="Ship order",
        request=ShipOrderSerializer,
        responses={200: OrderSerializer}
    )
    @action(detail=True, methods=['post'])
    def ship(self, request, pk=None):
        """Ship an order."""
        serializer = ShipOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = OrderService()
        order = service.mark_shipped(
            str(pk),
            serializer.validated_data.get('tracking_code', ''),
            serializer.validated_data.get('carrier', ''),
            request.user
        )
        return Response(OrderSerializer(order).data)

    @extend_schema(
        summary="Mark order as delivered",
        responses={200: OrderSerializer}
    )
    @action(detail=True, methods=['post'])
    def deliver(self, request, pk=None):
        """Mark order as delivered."""
        service = OrderService()
        order = service.mark_delivered(str(pk), request.user)
        return Response(OrderSerializer(order).data)

    @extend_schema(
        summary="Cancel order",
        request=CancelOrderSerializer,
        responses={200: OrderSerializer}
    )
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an order."""
        serializer = CancelOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = OrderService()
        order = service.cancel_order(
            str(pk),
            serializer.validated_data.get('reason', ''),
            request.user
        )
        return Response(OrderSerializer(order).data)

    @extend_schema(
        summary="Add item to order",
        request=AddItemSerializer,
        responses={201: OrderItemSerializer}
    )
    @action(detail=True, methods=['post'])
    def add_item(self, request, pk=None):
        """Add item to order."""
        serializer = AddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = OrderService()
        item = service.add_item(str(pk), **serializer.validated_data)
        
        return Response(
            OrderItemSerializer(item).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Remove item from order",
        responses={204: None}
    )
    @action(detail=True, methods=['delete'], url_path='items/(?P<item_id>[^/.]+)')
    def remove_item(self, request, pk=None, item_id=None):
        """Remove item from order."""
        service = OrderService()
        service.remove_item(str(pk), item_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Update shipping information",
        request=UpdateShippingSerializer,
        responses={200: OrderSerializer}
    )
    @action(detail=True, methods=['post'])
    def update_shipping(self, request, pk=None):
        """Update shipping information."""
        serializer = UpdateShippingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = OrderService()
        order = service.update_shipping(
            str(pk),
            serializer.validated_data['shipping_address'],
            serializer.validated_data.get('shipping_cost')
        )
        return Response(OrderSerializer(order).data)

    @extend_schema(
        summary="Add note to order",
        request=AddNoteSerializer,
        responses={200: OrderSerializer}
    )
    @action(detail=True, methods=['post'])
    def add_note(self, request, pk=None):
        """Add note to order."""
        serializer = AddNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = OrderService()
        order = service.add_note(
            str(pk),
            serializer.validated_data['note'],
            serializer.validated_data.get('is_internal', False),
            request.user
        )
        return Response(OrderSerializer(order).data)

    @extend_schema(
        summary="Get order events",
        responses={200: OrderEventSerializer(many=True)}
    )
    @action(detail=True, methods=['get'])
    def events(self, request, pk=None):
        """Get order events."""
        service = OrderService()
        events = service.get_order_events(str(pk))
        return Response(OrderEventSerializer(events, many=True).data)

    @extend_schema(
        summary="Get order statistics",
        responses={200: dict}
    )
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get order statistics."""
        account_id = request.query_params.get('account_id')
        
        if not account_id:
            return Response(
                {'error': 'account_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = OrderService()
        stats = service.get_order_stats(account_id)
        return Response(stats)

    @extend_schema(
        summary="Get customer orders",
        responses={200: OrderSerializer(many=True)}
    )
    @action(detail=False, methods=['get'])
    def by_customer(self, request):
        """Get orders by customer phone."""
        customer_phone = request.query_params.get('phone')
        account_id = request.query_params.get('account_id')
        
        if not customer_phone:
            return Response(
                {'error': 'phone is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = OrderService()
        orders = service.list_customer_orders(customer_phone, account_id)
        return Response(OrderSerializer(orders, many=True).data)
