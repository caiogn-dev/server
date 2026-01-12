"""
Order Repository.
"""
import uuid
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from django.db.models import QuerySet, Sum
from django.utils import timezone
from ..models import Order, OrderItem, OrderEvent


class OrderRepository:
    """Repository for Order operations."""

    def get_by_id(self, order_id: UUID) -> Optional[Order]:
        """Get order by ID."""
        try:
            return Order.objects.select_related(
                'account', 'conversation'
            ).prefetch_related('items').get(id=order_id, is_active=True)
        except Order.DoesNotExist:
            return None

    def get_by_order_number(self, order_number: str) -> Optional[Order]:
        """Get order by order number."""
        try:
            return Order.objects.select_related(
                'account', 'conversation'
            ).prefetch_related('items').get(order_number=order_number, is_active=True)
        except Order.DoesNotExist:
            return None

    def get_by_account(
        self,
        account_id: UUID,
        status: Optional[str] = None,
        limit: int = 100
    ) -> QuerySet[Order]:
        """Get orders by account."""
        queryset = Order.objects.filter(
            account_id=account_id,
            is_active=True
        ).select_related('account', 'conversation').prefetch_related('items')
        
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset[:limit]

    def get_by_customer_phone(
        self,
        customer_phone: str,
        account_id: Optional[UUID] = None,
        limit: int = 50
    ) -> QuerySet[Order]:
        """Get orders by customer phone."""
        queryset = Order.objects.filter(
            customer_phone=customer_phone,
            is_active=True
        ).select_related('account').prefetch_related('items')
        
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        return queryset[:limit]

    def get_pending_orders(
        self,
        account_id: Optional[UUID] = None,
        limit: int = 100
    ) -> QuerySet[Order]:
        """Get pending orders."""
        queryset = Order.objects.filter(
            status__in=[
                Order.OrderStatus.PENDING,
                Order.OrderStatus.AWAITING_PAYMENT
            ],
            is_active=True
        ).select_related('account')
        
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        return queryset[:limit]

    def create(self, **kwargs) -> Order:
        """Create a new order."""
        if 'order_number' not in kwargs:
            kwargs['order_number'] = self._generate_order_number()
        
        items_data = kwargs.pop('items', [])
        order = Order.objects.create(**kwargs)
        
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
        
        self._create_event(
            order=order,
            event_type=OrderEvent.EventType.CREATED,
            description=f"Order {order.order_number} created"
        )
        
        return order

    def update(self, order: Order, **kwargs) -> Order:
        """Update an order."""
        for key, value in kwargs.items():
            setattr(order, key, value)
        order.save()
        return order

    def update_status(
        self,
        order: Order,
        new_status: str,
        actor=None,
        description: str = ''
    ) -> Order:
        """
        Update order status with row locking to prevent race conditions.
        Uses select_for_update to ensure atomic status transitions.
        """
        from django.db import transaction
        
        with transaction.atomic():
            # Lock the order row to prevent concurrent updates
            locked_order = Order.objects.select_for_update().get(id=order.id)
            old_status = locked_order.status
            
            # Skip if already in target status (idempotency)
            if old_status == new_status:
                return locked_order
            
            locked_order.status = new_status
            
            now = timezone.now()
            if new_status == Order.OrderStatus.CONFIRMED:
                locked_order.confirmed_at = now
            elif new_status == Order.OrderStatus.PAID:
                locked_order.paid_at = now
            elif new_status == Order.OrderStatus.SHIPPED:
                locked_order.shipped_at = now
            elif new_status == Order.OrderStatus.DELIVERED:
                locked_order.delivered_at = now
            elif new_status == Order.OrderStatus.CANCELLED:
                locked_order.cancelled_at = now
            
            locked_order.save()
            
            self._create_event(
                order=locked_order,
                event_type=OrderEvent.EventType.STATUS_CHANGED,
                description=description or f"Status changed from {old_status} to {new_status}",
                old_status=old_status,
                new_status=new_status,
                actor=actor
            )
            
            # Update the original order object to reflect changes
            order.status = locked_order.status
            order.confirmed_at = locked_order.confirmed_at
            order.paid_at = locked_order.paid_at
            order.shipped_at = locked_order.shipped_at
            order.delivered_at = locked_order.delivered_at
            order.cancelled_at = locked_order.cancelled_at
            
            return locked_order

    def add_item(self, order: Order, **item_data) -> OrderItem:
        """Add item to order."""
        item = OrderItem.objects.create(order=order, **item_data)
        self._recalculate_order_total(order)
        return item

    def remove_item(self, item: OrderItem) -> None:
        """Remove item from order."""
        order = item.order
        item.delete()
        self._recalculate_order_total(order)

    def update_item(self, item: OrderItem, **kwargs) -> OrderItem:
        """Update order item."""
        for key, value in kwargs.items():
            setattr(item, key, value)
        item.save()
        self._recalculate_order_total(item.order)
        return item

    def cancel(self, order: Order, reason: str = '', actor=None) -> Order:
        """Cancel an order and restore stock quantities."""
        # Restore stock for each item
        self._restore_stock(order)
        
        return self.update_status(
            order=order,
            new_status=Order.OrderStatus.CANCELLED,
            actor=actor,
            description=f"Order cancelled. Reason: {reason}" if reason else "Order cancelled"
        )

    def _restore_stock(self, order: Order) -> None:
        """Restore stock quantities for all items in an order."""
        try:
            from apps.stores.models import StoreProduct
            
            for item in order.items.all():
                product_id = item.product_id
                if not product_id:
                    continue
                    
                try:
                    product = StoreProduct.objects.get(id=product_id)
                    if product.track_stock:
                        product.stock_quantity += item.quantity
                        product.save(update_fields=['stock_quantity', 'updated_at'])
                        
                        self._create_event(
                            order=order,
                            event_type=OrderEvent.EventType.NOTE_ADDED,
                            description=f"Stock restored: {item.product_name} +{item.quantity} units",
                            metadata={'product_id': str(product_id), 'quantity_restored': item.quantity}
                        )
                except StoreProduct.DoesNotExist:
                    # Product may have been deleted, log but continue
                    self._create_event(
                        order=order,
                        event_type=OrderEvent.EventType.NOTE_ADDED,
                        description=f"Could not restore stock for {item.product_name}: product not found",
                        metadata={'product_id': str(product_id), 'quantity': item.quantity}
                    )
        except ImportError:
            # Stores app not installed, skip stock restoration
            pass

    def add_note(
        self,
        order: Order,
        note: str,
        is_internal: bool = False,
        actor=None
    ) -> Order:
        """Add note to order."""
        if is_internal:
            order.internal_notes = f"{order.internal_notes}\n{note}".strip()
        else:
            order.notes = f"{order.notes}\n{note}".strip()
        order.save()
        
        self._create_event(
            order=order,
            event_type=OrderEvent.EventType.NOTE_ADDED,
            description=note,
            actor=actor,
            metadata={'is_internal': is_internal}
        )
        
        return order

    def get_events(self, order: Order) -> QuerySet[OrderEvent]:
        """Get order events."""
        return OrderEvent.objects.filter(order=order).select_related('actor')

    def get_order_stats(
        self,
        account_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> dict:
        """Get order statistics."""
        queryset = Order.objects.filter(
            account_id=account_id,
            is_active=True
        )
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        from django.db.models import Count
        
        status_counts = queryset.values('status').annotate(count=Count('id'))
        totals = queryset.aggregate(
            total_revenue=Sum('total'),
            total_orders=Count('id')
        )
        
        return {
            'total_orders': totals['total_orders'] or 0,
            'total_revenue': float(totals['total_revenue'] or 0),
            'by_status': {s['status']: s['count'] for s in status_counts},
        }

    def _generate_order_number(self) -> str:
        """Generate unique order number."""
        prefix = timezone.now().strftime('%Y%m%d')
        suffix = uuid.uuid4().hex[:6].upper()
        return f"ORD-{prefix}-{suffix}"

    def _recalculate_order_total(self, order: Order) -> None:
        """Recalculate order total from items."""
        items = order.items.all()
        order.subtotal = sum(item.total_price for item in items)
        order.calculate_total()
        order.save(update_fields=['subtotal', 'total', 'updated_at'])

    def _create_event(
        self,
        order: Order,
        event_type: str,
        description: str = '',
        old_status: str = '',
        new_status: str = '',
        actor=None,
        metadata: dict = None
    ) -> OrderEvent:
        """Create order event."""
        return OrderEvent.objects.create(
            order=order,
            event_type=event_type,
            description=description,
            old_status=old_status,
            new_status=new_status,
            actor=actor,
            metadata=metadata or {}
        )
