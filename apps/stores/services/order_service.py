"""
Order Service - Unified order management for all stores.
Handles order operations including creation, updates, status management, and notifications.
"""
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List
from django.db import transaction
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class OrderService:
    """Service for managing store orders."""

    def get_order_by_id(self, order_id: str):
        """Get an order by its ID."""
        from apps.stores.models import StoreOrder
        try:
            return StoreOrder.objects.select_related(
                'store', 'customer'
            ).prefetch_related(
                'items__product', 'combo_items__combo'
            ).get(id=order_id)
        except StoreOrder.DoesNotExist:
            return None

    def get_order_by_number(self, store, order_number: str):
        """Get an order by its order number within a store."""
        from apps.stores.models import StoreOrder
        try:
            return StoreOrder.objects.select_related(
                'store', 'customer'
            ).prefetch_related(
                'items__product', 'combo_items__combo'
            ).get(store=store, order_number=order_number)
        except StoreOrder.DoesNotExist:
            return None

    def get_order_by_access_token(self, access_token: str):
        """Get an order by its public access token."""
        from apps.stores.models import StoreOrder
        try:
            return StoreOrder.objects.select_related(
                'store', 'customer'
            ).prefetch_related(
                'items__product', 'combo_items__combo'
            ).get(access_token=access_token)
        except StoreOrder.DoesNotExist:
            return None

    def get_store_orders(
        self,
        store,
        status_filter: str = None,
        payment_status: str = None,
        date_from=None,
        date_to=None,
        limit: int = 50
    ):
        """Get orders for a store with optional filters."""
        from apps.stores.models import StoreOrder
        
        queryset = StoreOrder.objects.filter(store=store)
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)
        
        return queryset.select_related(
            'customer'
        ).prefetch_related(
            'items__product'
        ).order_by('-created_at')[:limit]

    def get_customer_orders(self, store, customer_phone: str, limit: int = 20):
        """Get orders for a customer by phone number."""
        from apps.stores.models import StoreOrder
        
        return StoreOrder.objects.filter(
            store=store,
            customer_phone=customer_phone
        ).select_related(
            'customer'
        ).prefetch_related(
            'items__product'
        ).order_by('-created_at')[:limit]

    @transaction.atomic
    def update_status(
        self,
        order,
        new_status: str,
        notify_customer: bool = True,
        notes: str = None
    ) -> Dict[str, Any]:
        """
        Update order status with validation and optional notification.
        """
        from apps.stores.models import StoreOrder
        
        # Valid status transitions
        valid_transitions = {
            'pending': ['confirmed', 'cancelled'],
            'confirmed': ['preparing', 'cancelled'],
            'preparing': ['ready', 'out_for_delivery', 'cancelled'],
            'ready': ['out_for_delivery', 'delivered', 'picked_up', 'cancelled'],
            'out_for_delivery': ['delivered', 'cancelled'],
            'delivered': [],
            'picked_up': [],
            'cancelled': [],
        }
        
        current_status = order.status
        allowed = valid_transitions.get(current_status, [])
        
        if new_status not in allowed and new_status != current_status:
            return {
                'success': False,
                'error': f'Invalid status transition from {current_status} to {new_status}',
                'allowed_transitions': allowed
            }
        
        old_status = order.status
        order.status = new_status
        
        # Update timestamps
        if new_status == 'confirmed':
            order.confirmed_at = timezone.now()
        elif new_status == 'preparing':
            order.preparing_at = timezone.now()
        elif new_status == 'ready':
            order.ready_at = timezone.now()
        elif new_status == 'out_for_delivery':
            order.out_for_delivery_at = timezone.now()
        elif new_status == 'delivered':
            order.delivered_at = timezone.now()
        elif new_status == 'picked_up':
            order.picked_up_at = timezone.now()
        elif new_status == 'cancelled':
            order.cancelled_at = timezone.now()
        
        if notes:
            order.notes = f"{order.notes}\n\n[{timezone.now().isoformat()}] Status: {new_status} - {notes}".strip()
        
        order.save()
        
        # Trigger webhook
        from .webhook_service import webhook_service
        webhook_service.trigger_webhooks(order.store, 'order.status_changed', {
            'order_id': str(order.id),
            'order_number': order.order_number,
            'old_status': old_status,
            'new_status': new_status,
            'customer_phone': order.customer_phone,
        })
        
        # Send notification if requested
        if notify_customer and order.customer_phone:
            self._send_status_notification(order, old_status, new_status)
        
        logger.info(f"Order {order.order_number} status updated: {old_status} -> {new_status}")
        
        return {
            'success': True,
            'order_id': str(order.id),
            'old_status': old_status,
            'new_status': new_status
        }

    def _send_status_notification(self, order, old_status: str, new_status: str):
        """Send WhatsApp notification about order status change."""
        try:
            from apps.whatsapp.services import MessageService
            from apps.whatsapp.utils import get_default_whatsapp_account
            from apps.core.utils import normalize_phone_number

            # Get WhatsApp account for the store
            account = None
            if order.store:
                account = order.store.get_whatsapp_account()

            # Fallback to default account if no store-linked account
            if not account:
                account = get_default_whatsapp_account(create_if_missing=False)

            if not account:
                logger.warning(f"No WhatsApp account found for order {order.order_number}")
                return

            if not account.phone_number_id:
                logger.warning(f"WhatsApp account {account.id} missing phone_number_id")
                return

            status_messages = {
                'confirmed': f"✅ *Pedido Confirmado!*\n\nOlá {order.customer_name or 'Cliente'}!\n\nSeu pedido #{order.order_number} foi confirmado!",
                'preparing': f"👨‍🍳 *Pedido em Preparo!*\n\nOlá {order.customer_name or 'Cliente'}!\n\nSeu pedido #{order.order_number} está sendo preparado!",
                'ready': f"📦 *Pedido Pronto!*\n\nOlá {order.customer_name or 'Cliente'}!\n\nSeu pedido #{order.order_number} está pronto para retirada!",
                'out_for_delivery': f"🚚 *Pedido em Entrega!*\n\nOlá {order.customer_name or 'Cliente'}!\n\nSeu pedido #{order.order_number} saiu para entrega!",
                'delivered': f"✅ *Pedido Entregue!*\n\nOlá {order.customer_name or 'Cliente'}!\n\nSeu pedido #{order.order_number} foi entregue! Agradecemos a preferência!",
                'cancelled': f"❌ *Pedido Cancelado*\n\nOlá {order.customer_name or 'Cliente'}!\n\nSeu pedido #{order.order_number} foi cancelado.",
            }

            message_text = status_messages.get(new_status)
            if not message_text:
                return

            # Normalize phone number
            phone = normalize_phone_number(order.customer_phone or '')
            if not phone:
                logger.warning(f"Invalid phone number for order {order.order_number}")
                return

            # Send message using MessageService
            message_service = MessageService()
            message_service.send_text_message(
                account_id=str(account.id),
                to=phone,
                text=message_text,
                metadata={
                    'source': 'order_status_notification',
                    'order_id': str(order.id),
                    'order_number': order.order_number,
                    'status': new_status
                }
            )

            logger.info(f"WhatsApp status notification sent for order {order.order_number}: {new_status}")

        except Exception as e:
            logger.error(f"Failed to send status notification for order {order.order_number}: {e}")

    @transaction.atomic
    def cancel_order(
        self,
        order,
        reason: str = None,
        refund: bool = False,
        restore_stock: bool = True
    ) -> Dict[str, Any]:
        """Cancel an order with optional refund and stock restoration."""
        from apps.stores.models import StoreOrder
        
        if order.status == 'cancelled':
            return {
                'success': False,
                'error': 'Order is already cancelled'
            }
        
        if order.status in ['delivered', 'picked_up']:
            return {
                'success': False,
                'error': f'Cannot cancel order with status: {order.status}'
            }
        
        # Update status
        order.status = 'cancelled'
        order.cancelled_at = timezone.now()
        
        if reason:
            order.notes = f"{order.notes}\n\nCancellation reason: {reason}".strip()
        
        order.save()
        
        # Restore stock if requested
        if restore_stock:
            for item in order.items.all():
                if item.product and item.product.track_stock:
                    item.product.stock_quantity += item.quantity
                    item.product.save(update_fields=['stock_quantity'])
            
            for combo_item in order.combo_items.all():
                if combo_item.combo and combo_item.combo.track_stock:
                    combo_item.combo.stock_quantity += combo_item.quantity
                    combo_item.combo.save(update_fields=['stock_quantity'])
        
        # Handle refund if requested
        refund_result = None
        if refund and order.payment_status == 'paid':
            refund_result = self._process_refund(order)
        
        # Trigger webhook
        from .webhook_service import webhook_service
        webhook_service.trigger_webhooks(order.store, 'order.cancelled', {
            'order_id': str(order.id),
            'order_number': order.order_number,
            'reason': reason,
            'refunded': refund_result.get('success') if refund_result else False,
        })
        
        logger.info(f"Order {order.order_number} cancelled. Reason: {reason}")
        
        return {
            'success': True,
            'order_id': str(order.id),
            'order_number': order.order_number,
            'stock_restored': restore_stock,
            'refund': refund_result
        }

    def _process_refund(self, order) -> Dict[str, Any]:
        """Process refund for a cancelled order."""
        try:
            from .payment_service import get_payment_service
            
            payment_service = get_payment_service(order.store)
            if payment_service and order.payment_id:
                result = payment_service.refund_payment(order.payment_id)
                if result.get('success'):
                    order.payment_status = 'refunded'
                    order.refunded_at = timezone.now()
                    order.save(update_fields=['payment_status', 'refunded_at'])
                return result
            return {'success': False, 'error': 'No payment service configured'}
        except Exception as e:
            logger.error(f"Refund error for order {order.order_number}: {e}")
            return {'success': False, 'error': str(e)}

    def get_order_statistics(self, store, period_days: int = 30) -> Dict[str, Any]:
        """Get order statistics for a store."""
        from apps.stores.models import StoreOrder
        from django.db.models.functions import TruncDate
        
        now = timezone.now()
        period_start = now - timedelta(days=period_days)
        
        orders = StoreOrder.objects.filter(
            store=store,
            created_at__gte=period_start
        )
        
        total_orders = orders.count()
        total_revenue = orders.filter(
            payment_status='paid'
        ).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
        
        avg_order_value = orders.filter(
            payment_status='paid'
        ).aggregate(avg=Avg('total'))['avg'] or Decimal('0.00')
        
        # Orders by status
        by_status = orders.values('status').annotate(count=Count('id'))
        
        # Orders by payment status
        by_payment = orders.values('payment_status').annotate(count=Count('id'))
        
        # Daily orders
        daily = orders.annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('id'),
            revenue=Sum('total')
        ).order_by('date')
        
        return {
            'period_days': period_days,
            'total_orders': total_orders,
            'total_revenue': float(total_revenue),
            'average_order_value': float(avg_order_value),
            'by_status': {item['status']: item['count'] for item in by_status},
            'by_payment_status': {item['payment_status']: item['count'] for item in by_payment},
            'daily': [
                {
                    'date': item['date'].isoformat() if item['date'] else None,
                    'count': item['count'],
                    'revenue': float(item['revenue'] or 0)
                }
                for item in daily
            ]
        }

    def search_orders(
        self,
        store,
        query: str,
        limit: int = 20
    ):
        """Search orders by number, customer name, email, or phone."""
        from apps.stores.models import StoreOrder
        
        return StoreOrder.objects.filter(
            store=store
        ).filter(
            Q(order_number__icontains=query) |
            Q(customer_name__icontains=query) |
            Q(customer_email__icontains=query) |
            Q(customer_phone__icontains=query)
        ).select_related(
            'customer'
        ).order_by('-created_at')[:limit]

    def get_pending_orders(self, store, include_preparing: bool = True):
        """Get orders that need attention (pending, confirmed, preparing)."""
        from apps.stores.models import StoreOrder
        
        statuses = ['pending', 'confirmed']
        if include_preparing:
            statuses.append('preparing')
        
        return StoreOrder.objects.filter(
            store=store,
            status__in=statuses
        ).select_related(
            'customer'
        ).prefetch_related(
            'items__product'
        ).order_by('created_at')

    @transaction.atomic
    def bulk_update_status(
        self,
        orders,
        new_status: str,
        notify_customers: bool = False
    ) -> Dict[str, Any]:
        """Update status for multiple orders at once."""
        results = []
        for order in orders:
            result = self.update_status(order, new_status, notify_customers)
            results.append({
                'order_id': str(order.id),
                'order_number': order.order_number,
                **result
            })
        
        success_count = sum(1 for r in results if r.get('success'))
        
        return {
            'total': len(results),
            'success': success_count,
            'failed': len(results) - success_count,
            'results': results
        }

    def generate_order_summary(self, order) -> str:
        """Generate a text summary of an order for notifications."""
        lines = [
            f"📦 Pedido #{order.order_number}",
            f"👤 Cliente: {order.customer_name}",
            f"📱 Telefone: {order.customer_phone}",
            "",
            "📝 Itens:",
        ]
        
        for item in order.items.all():
            lines.append(f"  • {item.quantity}x {item.product_name} - R$ {item.subtotal:.2f}")
        
        for combo_item in order.combo_items.all():
            lines.append(f"  • {combo_item.quantity}x {combo_item.combo.name} - R$ {combo_item.subtotal:.2f}")
        
        lines.extend([
            "",
            f"💰 Subtotal: R$ {order.subtotal:.2f}",
        ])
        
        if order.discount > 0:
            lines.append(f"🏷️ Desconto: -R$ {order.discount:.2f}")
        
        if order.delivery_fee > 0:
            lines.append(f"🚗 Entrega: R$ {order.delivery_fee:.2f}")
        
        lines.append(f"💵 Total: R$ {order.total:.2f}")
        
        if order.delivery_method == 'delivery':
            lines.extend([
                "",
                "📍 Endereço de entrega:",
                f"  {order.delivery_address.get('street', '')}",
                f"  {order.delivery_address.get('neighborhood', '')}",
            ])
        
        return "\n".join(lines)


# Singleton instance
order_service = OrderService()
