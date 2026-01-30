"""
API views for the stores app.
"""
import logging
import uuid as uuid_module
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone


def filter_by_store(queryset, store_param):
    """Filter queryset by store UUID or slug."""
    if not store_param:
        return queryset, False
    
    try:
        uuid_module.UUID(store_param)
        return queryset.filter(store_id=store_param), True
    except (ValueError, AttributeError):
        return queryset.filter(store__slug=store_param), True

from apps.stores.models import (
    Store, StoreIntegration, StoreWebhook, StoreCategory,
    StoreProduct, StoreProductVariant, StoreOrder, StoreOrderItem,
    StoreCustomer
)
from apps.stores.services import store_service, webhook_service
from .serializers import (
    StoreSerializer, StoreCreateSerializer,
    StoreIntegrationSerializer, StoreIntegrationCreateSerializer,
    StoreWebhookSerializer,
    StoreCategorySerializer,
    StoreProductSerializer, StoreProductCreateSerializer,
    StoreProductVariantSerializer,
    StoreOrderSerializer, StoreOrderCreateSerializer, StoreOrderUpdateSerializer,
    StoreCustomerSerializer,
    StoreStatsSerializer
)

logger = logging.getLogger(__name__)


class IsStoreOwnerOrStaff(permissions.BasePermission):
    """Permission to check if user owns or manages the store."""
    
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'store'):
            store = obj.store
        elif isinstance(obj, Store):
            store = obj
        else:
            return False
        
        return (
            store.owner == request.user or
            request.user in store.staff.all() or
            request.user.is_staff
        )


class StoreViewSet(viewsets.ModelViewSet):
    """ViewSet for managing stores."""
    
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    lookup_field = 'pk'
    
    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Store.objects.all()
        return Store.objects.filter(
            Q(owner=user) | Q(staff=user)
        ).distinct()
    
    def get_object(self):
        """
        Override to support both UUID and slug lookups.
        This allows endpoints like /stores/stores/pastita/ to work.
        """
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]
        
        # Try UUID first, then slug
        try:
            uuid_module.UUID(lookup_value)
            filter_kwargs = {'pk': lookup_value}
        except (ValueError, AttributeError):
            filter_kwargs = {'slug': lookup_value}
        
        obj = get_object_or_404(queryset, **filter_kwargs)
        self.check_object_permissions(self.request, obj)
        return obj
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StoreCreateSerializer
        return StoreSerializer
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get store statistics."""
        store = self.get_object()
        stats = store_service.get_store_stats(store)
        return Response(StoreStatsSerializer(stats).data)
    
    @action(detail=True, methods=['post'])
    def sync_pastita(self, request, pk=None):
        """Sync Pastita products to this store."""
        store = self.get_object()
        result = store_service.sync_pastita_to_store(store)
        return Response({
            'message': 'Pastita products synced successfully',
            'synced': result
        })
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a store."""
        store = self.get_object()
        store.status = Store.StoreStatus.ACTIVE
        store.save(update_fields=['status', 'updated_at'])
        return Response({'status': 'activated'})
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a store."""
        store = self.get_object()
        store.status = Store.StoreStatus.INACTIVE
        store.save(update_fields=['status', 'updated_at'])
        return Response({'status': 'deactivated'})


class StoreIntegrationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store integrations."""
    
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        queryset = StoreIntegration.objects.all()
        
        queryset, filtered = filter_by_store(queryset, store_param)
        if filtered:
            return queryset
        
        user = self.request.user
        if user.is_staff:
            return queryset
        return queryset.filter(
            Q(store__owner=user) | Q(store__staff=user)
        ).distinct()
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return StoreIntegrationCreateSerializer
        return StoreIntegrationSerializer
    
    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Test an integration connection."""
        integration = self.get_object()
        # Implementation depends on integration type
        return Response({'status': 'test_pending', 'message': 'Test not implemented for this integration type'})
    
    @action(detail=True, methods=['post'])
    def refresh_token(self, request, pk=None):
        """Refresh integration access token."""
        integration = self.get_object()
        # Implementation depends on integration type
        return Response({'status': 'refresh_pending', 'message': 'Token refresh not implemented for this integration type'})


class StoreWebhookViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store webhooks."""
    
    serializer_class = StoreWebhookSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        queryset = StoreWebhook.objects.all()
        queryset, filtered = filter_by_store(queryset, store_param)
        if filtered:
            return queryset
        
        user = self.request.user
        if user.is_staff:
            return queryset
        return queryset.filter(
            Q(store__owner=user) | Q(store__staff=user)
        ).distinct()
    
    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Send a test webhook."""
        webhook = self.get_object()
        result = webhook_service.test_webhook(webhook)
        return Response(result)


class StoreCategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store categories."""
    
    serializer_class = StoreCategorySerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        queryset = StoreCategory.objects.all()
        queryset, filtered = filter_by_store(queryset, store_param)
        if filtered:
            return queryset.order_by('sort_order', 'name')
        
        user = self.request.user
        if user.is_staff:
            return queryset.order_by('sort_order', 'name')
        return queryset.filter(
            Q(store__owner=user) | Q(store__staff=user)
        ).distinct().order_by('sort_order', 'name')


class StoreProductViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store products."""
    
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        queryset = StoreProduct.objects.all()
        
        queryset, filtered = filter_by_store(queryset, store_param)
        if not filtered:
            user = self.request.user
            if not user.is_staff:
                queryset = queryset.filter(
                    Q(store__owner=user) | Q(store__staff=user)
                ).distinct()
        
        # Filters
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category_id=category)
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        featured = self.request.query_params.get('featured')
        if featured:
            queryset = queryset.filter(featured=featured.lower() == 'true')
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(sku__icontains=search) |
                Q(description__icontains=search)
            )
        
        return queryset.select_related('category', 'store')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return StoreProductCreateSerializer
        return StoreProductSerializer
    
    @action(detail=True, methods=['post'])
    def toggle_status(self, request, pk=None):
        """Toggle product active/inactive status."""
        product = self.get_object()
        if product.status == 'active':
            product.status = 'inactive'
        else:
            product.status = 'active'
        product.save(update_fields=['status', 'updated_at'])
        return Response({'status': product.status})
    
    @action(detail=True, methods=['post'])
    def toggle_featured(self, request, pk=None):
        """Toggle product featured status."""
        product = self.get_object()
        product.featured = not product.featured
        product.save(update_fields=['featured', 'updated_at'])
        return Response({'featured': product.featured})
    
    @action(detail=True, methods=['post'])
    def update_stock(self, request, pk=None):
        """Update product stock quantity."""
        product = self.get_object()
        quantity = request.data.get('quantity')
        if quantity is None:
            return Response(
                {'error': 'quantity is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        product.stock_quantity = int(quantity)
        product.save(update_fields=['stock_quantity', 'updated_at'])
        return Response({'stock_quantity': product.stock_quantity})
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Duplicate a product."""
        product = self.get_object()
        
        # Create a copy
        new_product = StoreProduct.objects.create(
            store=product.store,
            category=product.category,
            name=f"{product.name} (Copy)",
            slug=f"{product.slug}-copy",
            description=product.description,
            short_description=product.short_description,
            price=product.price,
            compare_at_price=product.compare_at_price,
            cost_price=product.cost_price,
            track_stock=product.track_stock,
            stock_quantity=0,
            low_stock_threshold=product.low_stock_threshold,
            status='inactive',
            attributes=product.attributes,
            tags=product.tags
        )
        
        return Response(StoreProductSerializer(new_product).data)


class StoreProductVariantViewSet(viewsets.ModelViewSet):
    """ViewSet for managing product variants."""
    
    serializer_class = StoreProductVariantSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        product_id = self.kwargs.get('product_pk')
        if product_id:
            return StoreProductVariant.objects.filter(product_id=product_id)
        return StoreProductVariant.objects.none()


class StoreOrderViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store orders."""
    
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')
        queryset = StoreOrder.objects.all()
        
        if store_param:
            # Check if it's a UUID or a slug
            try:
                import uuid
                uuid.UUID(store_param)
                queryset = queryset.filter(store_id=store_param)
            except (ValueError, AttributeError):
                # It's a slug, filter by store slug
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
        
        # Optimize queries with select_related and prefetch_related
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
    
    def create(self, request, *args, **kwargs):
        """Create a new order."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        store_id = self.kwargs.get('store_pk') or request.data.get('store')
        store = get_object_or_404(Store, id=store_id)
        
        data = serializer.validated_data
        
        order = store_service.create_order(
            store=store,
            customer_data={
                'name': data['customer_name'],
                'email': data['customer_email'],
                'phone': data['customer_phone'],
                'notes': data.get('customer_notes', '')
            },
            items=data['items'],
            delivery_data={
                'method': data.get('delivery_method', 'delivery'),
                'address': data.get('delivery_address', {}),
                'notes': data.get('delivery_notes', ''),
                'fee': data.get('delivery_fee'),
                'scheduled_date': data.get('scheduled_date'),
                'scheduled_time': data.get('scheduled_time', '')
            },
            coupon_code=data.get('coupon_code')
        )
        
        return Response(
            StoreOrderSerializer(order).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update order status."""
        order = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in dict(StoreOrder.OrderStatus.choices):
            return Response(
                {'error': 'Invalid status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order.update_status(new_status, notify=True)
        return Response(StoreOrderSerializer(order).data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an order."""
        order = self.get_object()
        reason = request.data.get('reason', '')
        
        order.status = StoreOrder.OrderStatus.CANCELLED
        order.cancelled_at = timezone.now()
        order.internal_notes = f"{order.internal_notes}\nCancelled: {reason}".strip()
        order.save()

        # Trigger WhatsApp notification
        try:
            order._trigger_status_whatsapp_notification(StoreOrder.OrderStatus.CANCELLED)
        except Exception as e:
            logger.error(f"Failed to trigger WhatsApp notification for order {order.order_number}: {e}")
        
        # Restore stock
        for item in order.items.all():
            if item.product and item.product.track_stock:
                item.product.stock_quantity += item.quantity
                item.product.save(update_fields=['stock_quantity'])
        
        # Trigger webhook
        webhook_service.trigger_webhooks(order.store, 'order.cancelled', {
            'order_id': str(order.id),
            'order_number': order.order_number,
            'reason': reason
        })
        
        return Response(StoreOrderSerializer(order).data)
    
    @action(detail=True, methods=['post'])
    def add_tracking(self, request, pk=None):
        """Add tracking information to an order."""
        from apps.stores.services.checkout_service import trigger_order_email_automation
        
        order = self.get_object()
        
        order.tracking_code = request.data.get('tracking_code', '')
        order.tracking_url = request.data.get('tracking_url', '')
        order.carrier = request.data.get('carrier', '')
        order.status = StoreOrder.OrderStatus.SHIPPED
        order.save(update_fields=['tracking_code', 'tracking_url', 'carrier', 'status', 'updated_at'])
        
        # Trigger order shipped email automation
        trigger_order_email_automation(order, 'order_shipped', {
            'tracking_code': order.tracking_code,
            'tracking_url': order.tracking_url,
            'carrier': order.carrier,
        })

        # Trigger WhatsApp notification
        try:
            order._trigger_status_whatsapp_notification(StoreOrder.OrderStatus.SHIPPED)
        except Exception as e:
            logger.error(f"Failed to trigger WhatsApp notification for order {order.order_number}: {e}")
        
        return Response(StoreOrderSerializer(order).data)

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """Mark order as paid (manual payment confirmation for cash, transfer, etc)."""
        order = self.get_object()
        
        # Update payment status
        order.payment_status = StoreOrder.PaymentStatus.PAID
        order.paid_at = timezone.now()
        
        # Also update order status to confirmed if it's still pending/processing
        if order.status in [StoreOrder.OrderStatus.PENDING, StoreOrder.OrderStatus.PROCESSING]:
            order.status = StoreOrder.OrderStatus.CONFIRMED
        
        order.save(update_fields=['payment_status', 'paid_at', 'status', 'updated_at'])
        
        # Trigger webhooks (non-blocking)
        try:
            webhook_service.trigger_webhooks(order.store, 'order.paid', {
                'order_id': str(order.id),
                'order_number': order.order_number,
                'total': float(order.total),
                'payment_status': order.payment_status,
                'status': order.status
            })
        except Exception as e:
            logger.error(f"Failed to trigger webhooks for order {order.order_number}: {e}")
        
        # Trigger payment confirmed email automation (non-blocking)
        try:
            from apps.stores.services.checkout_service import trigger_order_email_automation
            trigger_order_email_automation(order, 'payment_confirmed')
        except Exception as e:
            logger.error(f"Failed to trigger email automation for order {order.order_number}: {e}")

        # Trigger WhatsApp payment notification
        try:
            order._trigger_status_whatsapp_notification(StoreOrder.OrderStatus.PAID)
        except Exception as e:
            logger.error(f"Failed to trigger WhatsApp notification for order {order.order_number}: {e}")
        
        # Refresh from database to ensure we have latest data
        order.refresh_from_db()
        return Response(StoreOrderSerializer(order).data)
    
    @action(detail=True, methods=['post'])
    def update_payment_status(self, request, pk=None):
        """Update payment status only (for manual control)."""
        order = self.get_object()
        new_payment_status = request.data.get('payment_status')
        
        valid_statuses = dict(StoreOrder.PaymentStatus.choices)
        if new_payment_status not in valid_statuses:
            return Response(
                {'error': f'Invalid payment status. Valid options: {list(valid_statuses.keys())}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_payment_status = order.payment_status
        order.payment_status = new_payment_status
        
        # If marking as paid, update paid_at timestamp
        if new_payment_status == StoreOrder.PaymentStatus.PAID and not order.paid_at:
            order.paid_at = timezone.now()
            # Also update order status to confirmed if pending
            if order.status in [StoreOrder.OrderStatus.PENDING, StoreOrder.OrderStatus.PROCESSING]:
                order.status = StoreOrder.OrderStatus.CONFIRMED
        
        order.save(update_fields=['payment_status', 'paid_at', 'status', 'updated_at'])

        logger.info(f"Order {order.order_number} payment status changed: {old_payment_status} -> {new_payment_status}")

        # Trigger WhatsApp notification when payment is confirmed
        if new_payment_status == StoreOrder.PaymentStatus.PAID:
            try:
                order._trigger_status_whatsapp_notification(StoreOrder.OrderStatus.PAID)
            except Exception as e:
                logger.error(f"Failed to trigger WhatsApp notification for order {order.order_number}: {e}")

        return Response(StoreOrderSerializer(order).data)

    @action(detail=True, methods=['post'])
    def add_note(self, request, pk=None):
        """Add internal note to order."""
        order = self.get_object()
        note = request.data.get('note', '')
        is_internal = request.data.get('is_internal', True)
        if note:
            prefix = "[INTERNAL] " if is_internal else ""
            current = order.internal_notes or ""
            order.internal_notes = (current + "\n" + prefix + note).strip()
            order.save(update_fields=['internal_notes', 'updated_at'])
        return Response(StoreOrderSerializer(order).data)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Get order history/events."""
        order = self.get_object()
        events = []
        if order.internal_notes:
            for i, note in enumerate(order.internal_notes.split("\n")):
                if note.strip():
                    events.append({
                        'id': i,
                        'event': note.strip(),
                        'created_at': order.updated_at.isoformat()
                    })
        return Response(events)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get order statistics."""
        from django.db.models import Sum, Count, Avg
        from django.db.models.functions import TruncDate
        from datetime import timedelta

        store_id = request.query_params.get('store')
        period = request.query_params.get('period', 'month')
        queryset = self.get_queryset()
        if store_id:
            queryset = queryset.filter(store_id=store_id)

        now = timezone.now()
        today = now.date()
        if period == 'today':
            date_from = today
        elif period == 'week':
            date_from = today - timedelta(days=7)
        elif period == 'year':
            date_from = today - timedelta(days=365)
        else:
            date_from = today - timedelta(days=30)

        paid_orders = queryset.filter(payment_status='paid')
        total_stats = paid_orders.aggregate(
            total_orders=Count('id'),
            total_revenue=Sum('total'),
            average_order=Avg('total')
        )
        today_stats = paid_orders.filter(created_at__date=today).aggregate(
            orders_today=Count('id'),
            revenue_today=Sum('total')
        )
        period_stats = paid_orders.filter(created_at__date__gte=date_from).aggregate(
            orders_period=Count('id'),
            revenue_period=Sum('total')
        )
        week_stats = paid_orders.filter(created_at__date__gte=today - timedelta(days=7)).aggregate(
            orders_week=Count('id'),
            revenue_week=Sum('total')
        )
        month_stats = paid_orders.filter(created_at__date__gte=today - timedelta(days=30)).aggregate(
            orders_month=Count('id'),
            revenue_month=Sum('total')
        )
        status_counts = queryset.values('status').annotate(count=Count('id'))
        pending = sum(s['count'] for s in status_counts if s['status'] == 'pending')
        processing = sum(s['count'] for s in status_counts if s['status'] in ['confirmed', 'preparing', 'ready'])
        completed = sum(s['count'] for s in status_counts if s['status'] in ['delivered', 'completed'])
        cancelled = sum(s['count'] for s in status_counts if s['status'] == 'cancelled')

        daily = paid_orders.filter(created_at__date__gte=date_from).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(count=Count('id'), revenue=Sum('total')).order_by('date')

        return Response({
            'total_orders': total_stats['total_orders'] or 0,
            'total_revenue': float(total_stats['total_revenue'] or 0),
            'average_order_value': float(total_stats['average_order'] or 0),
            'orders_today': today_stats['orders_today'] or 0,
            'revenue_today': float(today_stats['revenue_today'] or 0),
            'orders_period': period_stats['orders_period'] or 0,
            'revenue_period': float(period_stats['revenue_period'] or 0),
            'orders_week': week_stats['orders_week'] or 0,
            'revenue_week': float(week_stats['revenue_week'] or 0),
            'orders_month': month_stats['orders_month'] or 0,
            'revenue_month': float(month_stats['revenue_month'] or 0),
            'pending_orders': pending,
            'processing_orders': processing,
            'completed_orders': completed,
            'cancelled_orders': cancelled,
            'daily_orders': [{'date': d['date'].isoformat(), 'count': d['count'], 'revenue': float(d['revenue'] or 0)} for d in daily]
        })


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


from apps.stores.models import StoreCart, StoreCartItem, StoreCombo, StoreProductType
from apps.stores.services import cart_service, checkout_service
from .serializers import (
    StoreCartSerializer, AddToCartSerializer, UpdateCartItemSerializer,
    CheckoutSerializer, CheckoutResponseSerializer,
    StoreComboSerializer, StoreProductTypeSerializer, StoreCatalogSerializer
)


# =============================================================================
# CART VIEWS
# =============================================================================

class StoreCartViewSet(viewsets.ViewSet):
    """ViewSet for managing shopping carts."""
    
    permission_classes = [permissions.AllowAny]
    
    def get_store(self, store_slug):
        return get_object_or_404(Store, slug=store_slug, status='active')
    
    def get_cart(self, request, store):
        """Get or create cart for current user/session."""
        user = request.user if request.user.is_authenticated else None
        session_key = request.session.session_key
        
        if not session_key and not user:
            request.session.create()
            session_key = request.session.session_key
        
        return cart_service.get_cart(store, user=user, session_key=session_key)
    
    @action(detail=False, methods=['get'], url_path='(?P<store_slug>[^/.]+)')
    def get_cart_by_store(self, request, store_slug=None):
        """Get cart for a specific store."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        return Response(StoreCartSerializer(cart).data)
    
    @action(detail=False, methods=['post'], url_path='(?P<store_slug>[^/.]+)/add')
    def add_item(self, request, store_slug=None):
        """Add item to cart."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        try:
            if data.get('product_id'):
                product = get_object_or_404(StoreProduct, id=data['product_id'], store=store)
                variant = None
                if data.get('variant_id'):
                    variant = get_object_or_404(StoreProductVariant, id=data['variant_id'], product=product)
                
                cart_service.add_product(
                    cart=cart,
                    product=product,
                    quantity=data['quantity'],
                    variant=variant,
                    options=data.get('options'),
                    notes=data.get('notes', '')
                )
            
            elif data.get('combo_id'):
                combo = get_object_or_404(StoreCombo, id=data['combo_id'], store=store)
                cart_service.add_combo(
                    cart=cart,
                    combo=combo,
                    quantity=data['quantity'],
                    customizations=data.get('options'),
                    notes=data.get('notes', '')
                )
            
            return Response(StoreCartSerializer(cart).data)
        
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['patch'], url_path='(?P<store_slug>[^/.]+)/item/(?P<item_id>[^/.]+)')
    def update_item(self, request, store_slug=None, item_id=None):
        """Update cart item quantity."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data['quantity']
        
        try:
            # Try regular item first
            item = cart.items.filter(id=item_id).first()
            if item:
                cart_service.update_item_quantity(item, quantity)
            else:
                # Try combo item
                combo_item = cart.combo_items.filter(id=item_id).first()
                if combo_item:
                    cart_service.update_combo_quantity(combo_item, quantity)
                else:
                    return Response({'error': 'Item não encontrado'}, status=status.HTTP_404_NOT_FOUND)
            
            cart.refresh_from_db()
            return Response(StoreCartSerializer(cart).data)
        
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['delete'], url_path='(?P<store_slug>[^/.]+)/item/(?P<item_id>[^/.]+)')
    def remove_item(self, request, store_slug=None, item_id=None):
        """Remove item from cart."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        
        # Try regular item first
        item = cart.items.filter(id=item_id).first()
        if item:
            cart_service.remove_item(item)
        else:
            # Try combo item
            combo_item = cart.combo_items.filter(id=item_id).first()
            if combo_item:
                cart_service.remove_combo(combo_item)
            else:
                return Response({'error': 'Item não encontrado'}, status=status.HTTP_404_NOT_FOUND)
        
        cart.refresh_from_db()
        return Response(StoreCartSerializer(cart).data)
    
    @action(detail=False, methods=['delete'], url_path='(?P<store_slug>[^/.]+)/clear')
    def clear_cart(self, request, store_slug=None):
        """Clear all items from cart."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        cart_service.clear_cart(cart)
        return Response(StoreCartSerializer(cart).data)


# =============================================================================
# CHECKOUT VIEWS
# =============================================================================

class StoreCheckoutView(APIView):
    """View for processing checkout."""
    
    permission_classes = [permissions.AllowAny]
    
    def get_store(self, store_slug):
        return get_object_or_404(Store, slug=store_slug, status='active')
    
    def get_cart(self, request, store):
        user = request.user if request.user.is_authenticated else None
        session_key = request.session.session_key
        return cart_service.get_cart(store, user=user, session_key=session_key)
    
    def post(self, request, store_slug):
        """Process checkout and create order."""
        store = self.get_store(store_slug)
        cart = self.get_cart(request, store)
        
        if cart.is_empty:
            return Response(
                {'success': False, 'error': 'Carrinho vazio'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        try:
            # Create order
            order = checkout_service.create_order(
                cart=cart,
                customer_data={
                    'name': data['customer_name'],
                    'email': data['customer_email'],
                    'phone': data['customer_phone'],
                },
                delivery_data={
                    'method': data['delivery_method'],
                    'address': data.get('delivery_address', {}),
                    'notes': data.get('delivery_notes', ''),
                    'distance_km': data.get('distance_km'),
                    'zip_code': data.get('delivery_address', {}).get('zip_code'),
                },
                coupon_code=data.get('coupon_code'),
                notes=data.get('notes', '')
            )
            
            # Send WebSocket notification for new order
            try:
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f"store_{store.slug}_orders",
                        {
                            'type': 'order_created',
                            'order_id': str(order.id),
                            'order_number': order.order_number,
                            'customer_name': data['customer_name'],
                            'total': float(order.total),
                            'created_at': order.created_at.isoformat(),
                        }
                    )
                    logger.info(f"WebSocket: order_created sent for {order.order_number}")
            except Exception as e:
                logger.warning(f"Failed to send order_created WebSocket: {e}")
            
            # Create payment
            payment_result = checkout_service.create_payment(
                order=order,
                payment_method=data.get('payment_method', 'pix')
            )
            
            if payment_result.get('success'):
                response_data = {
                    'success': True,
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'access_token': order.access_token,  # Secure token for payment page
                    'payment_id': payment_result.get('payment_id'),
                    'payment_status': payment_result.get('status'),
                    'pix_code': payment_result.get('pix_code'),
                    'pix_qr_code': payment_result.get('pix_qr_code'),
                    'pix_ticket_url': payment_result.get('pix_ticket_url'),  # MP payment page
                    'redirect_url': payment_result.get('init_point'),
                    'subtotal': float(order.subtotal),
                    'delivery_fee': float(order.delivery_fee),
                    'discount': float(order.discount),
                    'total': float(order.total),
                }
                return Response(response_data, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'error': payment_result.get('error', 'Erro ao processar pagamento'),
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'access_token': order.access_token,  # Include token even on payment error
                }, status=status.HTTP_400_BAD_REQUEST)
        
        except ValueError as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Checkout error: {e}", exc_info=True)
            return Response(
                {'success': False, 'error': 'Erro interno ao processar pedido'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StoreDeliveryFeeView(APIView):
    """View for calculating delivery fee."""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug, status='active')
        
        distance_km = request.query_params.get('distance_km')
        zip_code = request.query_params.get('zip_code')
        
        result = checkout_service.calculate_delivery_fee(
            store,
            distance_km=Decimal(distance_km) if distance_km else None,
            zip_code=zip_code
        )
        
        return Response(result)


class StoreCouponValidateView(APIView):
    """View for validating coupons."""
    
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug, status='active')
        
        code = request.data.get('code')
        subtotal = request.data.get('subtotal', 0)
        
        if not code:
            return Response({'valid': False, 'error': 'Código do cupom é obrigatório'})
        
        result = checkout_service.validate_coupon(store, code, Decimal(str(subtotal)))
        return Response(result)


# =============================================================================
# CATALOG VIEWS
# =============================================================================

class StoreCatalogView(APIView):
    """
    View for getting store catalog (public).
    
    Returns the full catalog including:
    - Store info
    - Categories
    - Product types (dynamic, configurable per store)
    - Products grouped by type and category
    - Combos
    - Featured products
    
    This is the main endpoint for Pastita-3D and other store frontends.
    """
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, store_slug):
        """Get full catalog for a store."""
        store = get_object_or_404(Store, slug=store_slug, status='active')
        
        # Get categories
        categories = store.categories.filter(is_active=True).order_by('sort_order', 'name')
        
        # Get product types (dynamic - configured per store)
        product_types = store.product_types.filter(is_active=True, show_in_menu=True).order_by('sort_order', 'name')
        
        # Get products with their types
        products = store.products.filter(status='active').select_related(
            'category', 'product_type'
        ).order_by('sort_order', '-created_at')
        
        # Get combos
        combos = store.combos.filter(is_active=True).prefetch_related('items__product').order_by('-featured', '-created_at')
        
        # Get featured products
        featured = products.filter(featured=True)[:10]
        
        # Get featured combos (destaque)
        featured_combos = combos.filter(featured=True)[:5]
        
        # Group products by category
        products_by_category = {}
        for product in products:
            cat_id = str(product.category_id) if product.category_id else 'uncategorized'
            if cat_id not in products_by_category:
                products_by_category[cat_id] = []
            products_by_category[cat_id].append(StoreProductSerializer(product, context={'request': request}).data)
        
        # Group products by product type (for Pastita: molho, carne, rondelli)
        products_by_type = {}
        for product in products:
            type_slug = product.product_type.slug if product.product_type else 'generic'
            if type_slug not in products_by_type:
                products_by_type[type_slug] = []
            products_by_type[type_slug].append(StoreProductSerializer(product, context={'request': request}).data)
        
        return Response({
            'store': StoreSerializer(store, context={'request': request}).data,
            'categories': StoreCategorySerializer(categories, many=True).data,
            'product_types': StoreProductTypeSerializer(product_types, many=True).data,
            'products': StoreProductSerializer(products, many=True, context={'request': request}).data,
            'products_by_category': products_by_category,
            'products_by_type': products_by_type,
            'combos': StoreComboSerializer(combos, many=True, context={'request': request}).data,
            'combos_destaque': StoreComboSerializer(featured_combos, many=True, context={'request': request}).data,
            'featured_products': StoreProductSerializer(featured, many=True, context={'request': request}).data,
        })


class StorePublicView(APIView):
    """View for getting public store info."""
    
    permission_classes = [permissions.AllowAny]
    
    def get(self, request, store_slug):
        """Get public store information."""
        store = get_object_or_404(Store, slug=store_slug, status='active')
        return Response(StoreSerializer(store, context={'request': request}).data)


# =============================================================================
# COMBO VIEWS
# =============================================================================

class StoreComboViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store combos."""
    
    serializer_class = StoreComboSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        store_param = self.request.query_params.get('store')
        store_slug = self.kwargs.get('store_slug')
        
        queryset = StoreCombo.objects.all()
        
        if store_slug:
            queryset = queryset.filter(store__slug=store_slug)
        elif store_param:
            # Support both UUID and slug for the store parameter
            try:
                uuid_module.UUID(store_param)
                queryset = queryset.filter(store_id=store_param)
            except (ValueError, AttributeError):
                queryset = queryset.filter(store__slug=store_param)
        
        if self.action == 'list' and not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        
        return queryset.select_related('store').prefetch_related('items__product')


# =============================================================================
# PRODUCT TYPE VIEWS
# =============================================================================

class StoreProductTypeViewSet(viewsets.ModelViewSet):
    """ViewSet for managing product types."""
    
    serializer_class = StoreProductTypeSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        store_param = self.request.query_params.get('store')
        store_slug = self.kwargs.get('store_slug')
        
        queryset = StoreProductType.objects.all()
        
        if store_slug:
            queryset = queryset.filter(store__slug=store_slug)
        elif store_param:
            # Support both UUID and slug for the store parameter
            try:
                uuid_module.UUID(store_param)
                queryset = queryset.filter(store_id=store_param)
            except (ValueError, AttributeError):
                queryset = queryset.filter(store__slug=store_param)
        
        if self.action == 'list' and not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        
        return queryset.select_related('store').order_by('sort_order', 'name')


# =============================================================================
# COUPON VIEWS
# =============================================================================

from apps.stores.models import StoreCoupon, StoreDeliveryZone
from .serializers import (
    StoreCouponSerializer, StoreCouponCreateSerializer,
    StoreDeliveryZoneSerializer, StoreDeliveryZoneCreateSerializer
)


class StoreCouponViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store coupons."""
    
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        user = self.request.user
        store_param = self.request.query_params.get('store')
        
        if user.is_staff:
            queryset = StoreCoupon.objects.all()
        else:
            # Get stores user owns or manages
            user_stores = Store.objects.filter(
                Q(owner=user) | Q(staff=user)
            ).values_list('id', flat=True)
            queryset = StoreCoupon.objects.filter(store_id__in=user_stores)
        
        if store_param:
            # Support both UUID and slug for the store parameter
            try:
                uuid_module.UUID(store_param)
                queryset = queryset.filter(store_id=store_param)
            except (ValueError, AttributeError):
                queryset = queryset.filter(store__slug=store_param)
        
        return queryset.select_related('store').order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return StoreCouponCreateSerializer
        return StoreCouponSerializer
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle coupon active status."""
        coupon = self.get_object()
        coupon.is_active = not coupon.is_active
        coupon.save(update_fields=['is_active', 'updated_at'])
        return Response({
            'id': str(coupon.id),
            'is_active': coupon.is_active,
            'message': f"Cupom {'ativado' if coupon.is_active else 'desativado'}"
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get coupon statistics."""
        store_id = request.query_params.get('store')
        queryset = self.get_queryset()
        
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        
        from django.db.models import Sum, Count
        from django.utils import timezone
        
        now = timezone.now()
        stats = {
            'total': queryset.count(),
            'active': queryset.filter(is_active=True, valid_from__lte=now, valid_until__gte=now).count(),
            'expired': queryset.filter(valid_until__lt=now).count(),
            'total_usage': queryset.aggregate(total=Sum('used_count'))['total'] or 0,
        }
        
        return Response(stats)


# =============================================================================
# DELIVERY ZONE VIEWS
# =============================================================================

class StoreDeliveryZoneViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store delivery zones."""
    
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        user = self.request.user
        store_param = self.request.query_params.get('store')
        
        if user.is_staff:
            queryset = StoreDeliveryZone.objects.all()
        else:
            user_stores = Store.objects.filter(
                Q(owner=user) | Q(staff=user)
            ).values_list('id', flat=True)
            queryset = StoreDeliveryZone.objects.filter(store_id__in=user_stores)
        
        if store_param:
            # Support both UUID and slug for the store parameter
            try:
                uuid_module.UUID(store_param)
                queryset = queryset.filter(store_id=store_param)
            except (ValueError, AttributeError):
                queryset = queryset.filter(store__slug=store_param)
        
        return queryset.select_related('store').order_by('sort_order', 'distance_band', 'min_km')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return StoreDeliveryZoneCreateSerializer
        return StoreDeliveryZoneSerializer
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle zone active status."""
        zone = self.get_object()
        zone.is_active = not zone.is_active
        zone.save(update_fields=['is_active', 'updated_at'])
        return Response({
            'id': str(zone.id),
            'is_active': zone.is_active,
            'message': f"Zona {'ativada' if zone.is_active else 'desativada'}"
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get delivery zone statistics."""
        from django.db.models import Avg
        
        store_id = request.query_params.get('store')
        queryset = self.get_queryset()
        
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        
        # Calculate averages
        active_zones = queryset.filter(is_active=True)
        aggregates = active_zones.aggregate(
            avg_fee=Avg('delivery_fee'),
            avg_days=Avg('estimated_days')
        )
        
        stats = {
            'total': queryset.count(),
            'active': active_zones.count(),
            'inactive': queryset.filter(is_active=False).count(),
            'avg_fee': float(aggregates['avg_fee'] or 0),
            'avg_days': float(aggregates['avg_days'] or 0),
            'by_type': {}
        }
        
        for zone_type, _ in StoreDeliveryZone.ZoneType.choices:
            stats['by_type'][zone_type] = queryset.filter(zone_type=zone_type).count()
        
        return Response(stats)
    
    @action(detail=False, methods=['post'])
    def calculate_fee(self, request):
        """Calculate delivery fee for a given location."""
        store_id = request.data.get('store')
        distance_km = request.data.get('distance_km')
        zip_code = request.data.get('zip_code')
        
        if not store_id:
            return Response({'error': 'store is required'}, status=400)
        
        zones = StoreDeliveryZone.objects.filter(
            store_id=store_id,
            is_active=True
        ).order_by('sort_order')
        
        # Try to find matching zone
        for zone in zones:
            if distance_km and zone.matches_distance(distance_km):
                return Response({
                    'fee': str(zone.calculate_fee(distance_km)),
                    'zone_id': str(zone.id),
                    'zone_name': zone.name,
                    'estimated_minutes': zone.estimated_minutes,
                    'available': True
                })
            elif zip_code and zone.matches_zip_code(zip_code):
                return Response({
                    'fee': str(zone.delivery_fee),
                    'zone_id': str(zone.id),
                    'zone_name': zone.name,
                    'estimated_minutes': zone.estimated_minutes,
                    'available': True
                })
        
        # No matching zone found - use store default
        store = get_object_or_404(Store, id=store_id)
        return Response({
            'fee': str(store.default_delivery_fee),
            'zone_id': None,
            'zone_name': 'Padrão',
            'estimated_minutes': 45,
            'available': True
        })


# =============================================================================
# WISHLIST VIEWSET
# =============================================================================

from apps.stores.models import StoreWishlist
from .serializers import StoreWishlistSerializer, WishlistAddRemoveSerializer


class StoreWishlistViewSet(viewsets.ViewSet):
    """
    ViewSet for managing user wishlists per store.
    
    Endpoints:
    - GET /stores/{store_slug}/wishlist/ - Get user's wishlist (legacy /stores/s/{store_slug}/ paths also remain)
    - POST /stores/{store_slug}/wishlist/add/ - Add product to wishlist (legacy /stores/s/{store_slug}/ paths also remain)
    - POST /stores/{store_slug}/wishlist/remove/ - Remove product from wishlist (legacy /stores/s/{store_slug}/ paths also remain)
    - POST /stores/{store_slug}/wishlist/toggle/ - Toggle product in wishlist (legacy /stores/s/{store_slug}/ paths also remain)
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_store(self, store_slug):
        return get_object_or_404(Store, slug=store_slug, status='active')
    
    def get_wishlist(self, user, store):
        wishlist, _ = StoreWishlist.objects.get_or_create(user=user, store=store)
        return wishlist
    
    def list(self, request, store_slug=None):
        """Get user's wishlist for a store."""
        store = self.get_store(store_slug)
        wishlist = self.get_wishlist(request.user, store)
        serializer = StoreWishlistSerializer(wishlist)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def add(self, request, store_slug=None):
        """Add a product to the wishlist."""
        store = self.get_store(store_slug)
        serializer = WishlistAddRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = serializer.validated_data['product_id']
        product = get_object_or_404(StoreProduct, id=product_id, store=store, status='active')
        
        wishlist = self.get_wishlist(request.user, store)
        wishlist.products.add(product)
        
        return Response({
            'message': 'Product added to wishlist',
            'product_id': str(product_id),
            'wishlist_count': wishlist.products.count()
        })
    
    @action(detail=False, methods=['post'])
    def remove(self, request, store_slug=None):
        """Remove a product from the wishlist."""
        store = self.get_store(store_slug)
        serializer = WishlistAddRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = serializer.validated_data['product_id']
        
        wishlist = self.get_wishlist(request.user, store)
        wishlist.products.filter(id=product_id).delete()
        
        return Response({
            'message': 'Product removed from wishlist',
            'product_id': str(product_id),
            'wishlist_count': wishlist.products.count()
        })
    
    @action(detail=False, methods=['post'])
    def toggle(self, request, store_slug=None):
        """Toggle a product in the wishlist."""
        store = self.get_store(store_slug)
        serializer = WishlistAddRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product_id = serializer.validated_data['product_id']
        product = get_object_or_404(StoreProduct, id=product_id, store=store, status='active')
        
        wishlist = self.get_wishlist(request.user, store)
        
        if wishlist.products.filter(id=product_id).exists():
            wishlist.products.remove(product)
            added = False
        else:
            wishlist.products.add(product)
            added = True
        
        return Response({
            'message': 'Product added to wishlist' if added else 'Product removed from wishlist',
            'product_id': str(product_id),
            'in_wishlist': added,
            'wishlist_count': wishlist.products.count()
        })


# =============================================================================
# ENHANCED PRODUCT TYPE VIEWSET (Full CRUD for Dashboard)
# =============================================================================

from .serializers import StoreProductTypeSerializer, StoreProductTypeCreateSerializer, StoreProductWithTypeSerializer


class StoreProductTypeAdminViewSet(viewsets.ModelViewSet):
    """
    Full CRUD ViewSet for managing product types per store.
    
    Product types are fully dynamic - stores can create their own types
    with custom field definitions. For example, Pastita can create:
    - Molho (Sauce) with fields: tipo, quantidade
    - Carne (Meat) with fields: tipo, quantidade, molhos_compativeis
    - Rondelli (Pasta) with fields: categoria, sabor, quantidade
    
    Endpoints:
    - GET /stores/product-types/ - List all product types
    - POST /stores/product-types/ - Create new product type
    - GET /stores/product-types/{id}/ - Get product type details
    - PUT /stores/product-types/{id}/ - Update product type
    - DELETE /stores/product-types/{id}/ - Delete product type
    - GET /stores/product-types/?store={store_id} - Filter by store
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = StoreProductType.objects.all()
        
        # Filter by store (supports both UUID and slug)
        store_param = self.request.query_params.get('store')
        if store_param:
            try:
                uuid_module.UUID(store_param)
                queryset = queryset.filter(store_id=store_param)
            except (ValueError, AttributeError):
                queryset = queryset.filter(store__slug=store_param)
        
        store_slug = self.request.query_params.get('store_slug')
        if store_slug:
            queryset = queryset.filter(store__slug=store_slug)
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        return queryset.order_by('store', 'sort_order', 'name')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return StoreProductTypeCreateSerializer
        return StoreProductTypeSerializer
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle product type active status."""
        product_type = self.get_object()
        product_type.is_active = not product_type.is_active
        product_type.save()
        return Response({
            'id': str(product_type.id),
            'is_active': product_type.is_active,
            'message': f'Product type {"activated" if product_type.is_active else "deactivated"}'
        })
    
    @action(detail=True, methods=['get'])
    def products(self, request, pk=None):
        """Get all products of this type."""
        product_type = self.get_object()
        products = product_type.products.filter(status='active')
        serializer = StoreProductWithTypeSerializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_store(self, request):
        """Get product types grouped by store."""
        from collections import defaultdict
        
        queryset = self.get_queryset().filter(is_active=True)
        grouped = defaultdict(list)
        
        for pt in queryset:
            grouped[str(pt.store_id)].append(StoreProductTypeSerializer(pt).data)
        
        return Response(dict(grouped))
