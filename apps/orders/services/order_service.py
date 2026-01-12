# -*- coding: utf-8 -*-
"""
Order Service - Business logic for order management.
"""
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from apps.core.exceptions import NotFoundError, ValidationError
from apps.whatsapp.services import MessageService
from apps.whatsapp.repositories import WhatsAppAccountRepository
from apps.notifications.services import email_service
from ..models import Order, OrderItem, OrderEvent
from ..repositories import OrderRepository

logger = logging.getLogger(__name__)


class OrderService:
    """Service for order operations."""

    def __init__(self):
        self.repo = OrderRepository()
        self.account_repo = WhatsAppAccountRepository()

    def _send_order_notification(
        self,
        order: Order,
        status: str,
        previous_status: str = None,
        tracking_code: str = None,
        carrier: str = None
    ) -> None:
        """Send WebSocket notification for order status change."""
        try:
            channel_layer = get_channel_layer()
            if not channel_layer:
                return
            
            message = {
                'type': 'order_status',
                'order_id': str(order.id),
                'order_number': order.order_number,
                'status': status,
                'previous_status': previous_status,
                'tracking_code': tracking_code,
                'carrier': carrier,
                'timestamp': timezone.now().isoformat(),
            }
            
            # Send to order-specific group
            async_to_sync(channel_layer.group_send)(
                f"order_{order.id}",
                message
            )
            
            logger.debug(f"Order notification sent for order {order.order_number}")
        except Exception as e:
            logger.warning(f"Failed to send order notification: {str(e)}")

    def create_order(
        self,
        account_id: str,
        customer_phone: str,
        items: List[Dict[str, Any]],
        customer_name: str = '',
        customer_email: str = '',
        shipping_address: Dict = None,
        billing_address: Dict = None,
        notes: str = '',
        metadata: Dict = None,
        conversation_id: str = None
    ) -> Order:
        """Create a new order."""
        account = self.account_repo.get_by_id(account_id)
        if not account:
            raise NotFoundError(message="WhatsApp account not found")
        
        if not items:
            raise ValidationError(message="Order must have at least one item")
        
        order_items = []
        subtotal = 0
        
        for item in items:
            quantity = item.get('quantity', 1)
            unit_price = item.get('unit_price', 0)
            total_price = quantity * unit_price
            subtotal += total_price
            
            order_items.append({
                'product_id': item.get('product_id', ''),
                'product_name': item.get('product_name', 'Unknown Product'),
                'product_sku': item.get('product_sku', ''),
                'quantity': quantity,
                'unit_price': unit_price,
                'total_price': total_price,
                'notes': item.get('notes', ''),
                'metadata': item.get('metadata', {}),
            })
        
        order = self.repo.create(
            account=account,
            conversation_id=conversation_id,
            customer_phone=customer_phone,
            customer_name=customer_name,
            customer_email=customer_email,
            subtotal=subtotal,
            total=subtotal,
            shipping_address=shipping_address or {},
            billing_address=billing_address or {},
            notes=notes,
            metadata=metadata or {},
            items=order_items
        )
        
        logger.info(f"Order created: {order.order_number}")
        return order

    def get_order(self, order_id: str) -> Order:
        """Get order by ID."""
        order = self.repo.get_by_id(order_id)
        if not order:
            raise NotFoundError(message="Order not found")
        return order

    def get_order_by_number(self, order_number: str) -> Order:
        """Get order by order number."""
        order = self.repo.get_by_order_number(order_number)
        if not order:
            raise NotFoundError(message="Order not found")
        return order

    def list_orders(
        self,
        account_id: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Order]:
        """List orders for an account."""
        return list(self.repo.get_by_account(
            account_id=account_id,
            status=status,
            limit=limit
        ))

    def list_customer_orders(
        self,
        customer_phone: str,
        account_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Order]:
        """List orders for a customer."""
        return list(self.repo.get_by_customer_phone(
            customer_phone=customer_phone,
            account_id=account_id,
            limit=limit
        ))

    def confirm_order(self, order_id: str, actor=None) -> Order:
        """Confirm an order."""
        order = self.get_order(order_id)
        previous_status = order.status
        
        if order.status != Order.OrderStatus.PENDING:
            raise ValidationError(
                message=f"Cannot confirm order with status: {order.status}"
            )
        
        order = self.repo.update_status(
            order=order,
            new_status=Order.OrderStatus.CONFIRMED,
            actor=actor,
            description="Order confirmed"
        )
        
        self._notify_customer_order_confirmed(order)
        self._send_order_notification(order, 'confirmed', previous_status)
        
        logger.info(f"Order confirmed: {order.order_number}")
        return order

    def mark_awaiting_payment(self, order_id: str, actor=None) -> Order:
        """Mark order as awaiting payment."""
        order = self.get_order(order_id)
        previous_status = order.status
        
        if order.status not in [Order.OrderStatus.PENDING, Order.OrderStatus.CONFIRMED]:
            raise ValidationError(
                message=f"Cannot mark order as awaiting payment with status: {order.status}"
            )
        
        order = self.repo.update_status(
            order=order,
            new_status=Order.OrderStatus.AWAITING_PAYMENT,
            actor=actor,
            description="Order awaiting payment"
        )
        
        self._notify_customer_payment_pending(order)
        self._send_order_notification(order, 'awaiting_payment', previous_status)
        
        logger.info(f"Order awaiting payment: {order.order_number}")
        return order

    def mark_paid(
        self,
        order_id: str,
        payment_reference: str = '',
        actor=None
    ) -> Order:
        """Mark order as paid."""
        order = self.get_order(order_id)
        previous_status = order.status
        
        if order.status not in [
            Order.OrderStatus.PENDING,
            Order.OrderStatus.CONFIRMED,
            Order.OrderStatus.AWAITING_PAYMENT
        ]:
            raise ValidationError(
                message=f"Cannot mark order as paid with status: {order.status}"
            )
        
        metadata = order.metadata
        if payment_reference:
            metadata['payment_reference'] = payment_reference
        
        order = self.repo.update(order, metadata=metadata)
        order = self.repo.update_status(
            order=order,
            new_status=Order.OrderStatus.PAID,
            actor=actor,
            description=f"Payment received. Reference: {payment_reference}" if payment_reference else "Payment received"
        )
        
        self._notify_customer_payment_confirmed(order)
        self._send_order_notification(order, 'paid', previous_status)
        
        logger.info(f"Order paid: {order.order_number}")
        return order

    def mark_shipped(
        self,
        order_id: str,
        tracking_code: str = '',
        carrier: str = '',
        actor=None
    ) -> Order:
        """Mark order as shipped."""
        order = self.get_order(order_id)
        previous_status = order.status
        
        if order.status != Order.OrderStatus.PAID:
            raise ValidationError(
                message=f"Cannot ship order with status: {order.status}"
            )
        
        metadata = order.metadata
        if tracking_code:
            metadata['tracking_code'] = tracking_code
        if carrier:
            metadata['carrier'] = carrier
        
        order = self.repo.update(order, metadata=metadata)
        order = self.repo.update_status(
            order=order,
            new_status=Order.OrderStatus.SHIPPED,
            actor=actor,
            description=f"Order shipped. Tracking: {tracking_code}" if tracking_code else "Order shipped"
        )
        
        self._notify_customer_order_shipped(order, tracking_code, carrier)
        self._send_order_notification(order, 'shipped', previous_status, tracking_code, carrier)
        
        logger.info(f"Order shipped: {order.order_number}")
        return order

    def mark_delivered(self, order_id: str, actor=None) -> Order:
        """Mark order as delivered."""
        order = self.get_order(order_id)
        previous_status = order.status
        
        if order.status != Order.OrderStatus.SHIPPED:
            raise ValidationError(
                message=f"Cannot mark order as delivered with status: {order.status}"
            )
        
        order = self.repo.update_status(
            order=order,
            new_status=Order.OrderStatus.DELIVERED,
            actor=actor,
            description="Order delivered"
        )
        
        self._notify_customer_order_delivered(order)
        self._send_order_notification(order, 'delivered', previous_status)
        
        logger.info(f"Order delivered: {order.order_number}")
        return order

    def cancel_order(
        self,
        order_id: str,
        reason: str = '',
        actor=None
    ) -> Order:
        """Cancel an order."""
        order = self.get_order(order_id)
        previous_status = order.status
        
        if order.status in [
            Order.OrderStatus.SHIPPED,
            Order.OrderStatus.DELIVERED,
            Order.OrderStatus.CANCELLED
        ]:
            raise ValidationError(
                message=f"Cannot cancel order with status: {order.status}"
            )
        
        order = self.repo.cancel(order, reason, actor)
        
        self._notify_customer_order_cancelled(order, reason)
        self._send_order_notification(order, 'cancelled', previous_status)
        
        logger.info(f"Order cancelled: {order.order_number}")
        return order

    def add_item(
        self,
        order_id: str,
        product_name: str,
        quantity: int,
        unit_price: float,
        product_id: str = '',
        product_sku: str = '',
        notes: str = '',
        metadata: Dict = None
    ) -> OrderItem:
        """Add item to order."""
        order = self.get_order(order_id)
        
        if order.status not in [Order.OrderStatus.PENDING, Order.OrderStatus.CONFIRMED]:
            raise ValidationError(
                message=f"Cannot add items to order with status: {order.status}"
            )
        
        item = self.repo.add_item(
            order=order,
            product_id=product_id,
            product_name=product_name,
            product_sku=product_sku,
            quantity=quantity,
            unit_price=unit_price,
            total_price=quantity * unit_price,
            notes=notes,
            metadata=metadata or {}
        )
        
        logger.info(f"Item added to order: {order.order_number}")
        return item

    def remove_item(self, order_id: str, item_id: str) -> None:
        """Remove item from order."""
        order = self.get_order(order_id)
        
        if order.status not in [Order.OrderStatus.PENDING, Order.OrderStatus.CONFIRMED]:
            raise ValidationError(
                message=f"Cannot remove items from order with status: {order.status}"
            )
        
        try:
            item = OrderItem.objects.get(id=item_id, order=order)
        except OrderItem.DoesNotExist:
            raise NotFoundError(message="Order item not found")
        
        self.repo.remove_item(item)
        logger.info(f"Item removed from order: {order.order_number}")

    def update_shipping(
        self,
        order_id: str,
        shipping_address: Dict,
        shipping_cost: float = None
    ) -> Order:
        """Update shipping information."""
        order = self.get_order(order_id)
        
        if order.status not in [Order.OrderStatus.PENDING, Order.OrderStatus.CONFIRMED]:
            raise ValidationError(
                message=f"Cannot update shipping for order with status: {order.status}"
            )
        
        update_data = {'shipping_address': shipping_address}
        if shipping_cost is not None:
            update_data['shipping_cost'] = shipping_cost
        
        order = self.repo.update(order, **update_data)
        order.calculate_total()
        order.save()
        
        logger.info(f"Shipping updated for order: {order.order_number}")
        return order

    def add_note(
        self,
        order_id: str,
        note: str,
        is_internal: bool = False,
        actor=None
    ) -> Order:
        """Add note to order."""
        order = self.get_order(order_id)
        return self.repo.add_note(order, note, is_internal, actor)

    def get_order_events(self, order_id: str) -> List[OrderEvent]:
        """Get order events."""
        order = self.get_order(order_id)
        return list(self.repo.get_events(order))

    def get_order_stats(
        self,
        account_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get order statistics."""
        return self.repo.get_order_stats(account_id, start_date, end_date)

    def _is_whatsapp_enabled(self, order: Order) -> bool:
        """Check if WhatsApp notifications are enabled for this order's account."""
        if not order.account:
            return False
        if order.account.status != 'active':
            return False
        metadata = order.account.metadata or {}
        if metadata.get('whatsapp_disabled'):
            return False
        if not order.account.access_token:
            return False
        return True

    def _notify_customer_order_confirmed(self, order: Order) -> None:
        """Notify customer that order is confirmed."""
        # Send WhatsApp notification (if enabled)
        if self._is_whatsapp_enabled(order):
            try:
                message_service = MessageService()
                message_service.send_text_message(
                    account_id=str(order.account.id),
                    to=order.customer_phone,
                    text=f"✅ Seu pedido #{order.order_number} foi confirmado!\n\n"
                         f"Total: R$ {order.total:.2f}\n\n"
                         f"Aguardamos o pagamento para dar continuidade.",
                    metadata={'order_id': str(order.id), 'notification_type': 'order_confirmed'}
                )
            except Exception as e:
                logger.error(f"Failed to notify customer via WhatsApp: {str(e)}")
        
        # Send email notification
        if order.customer_email:
            try:
                email_service.send_order_confirmation(order, order.customer_email)
            except Exception as e:
                logger.error(f"Failed to send order confirmation email: {str(e)}")

    def _notify_customer_payment_pending(self, order: Order) -> None:
        """Notify customer about pending payment."""
        if not self._is_whatsapp_enabled(order):
            return
        try:
            message_service = MessageService()
            message_service.send_text_message(
                account_id=str(order.account.id),
                to=order.customer_phone,
                text=f"💳 Pedido #{order.order_number}\n\n"
                     f"Aguardando pagamento no valor de R$ {order.total:.2f}\n\n"
                     f"Após a confirmação do pagamento, seu pedido será processado.",
                metadata={'order_id': str(order.id), 'notification_type': 'payment_pending'}
            )
        except Exception as e:
            logger.error(f"Failed to notify customer: {str(e)}")

    def _notify_customer_payment_confirmed(self, order: Order) -> None:
        """Notify customer that payment is confirmed."""
        # Send WhatsApp notification (if enabled)
        if self._is_whatsapp_enabled(order):
            try:
                message_service = MessageService()
                message_service.send_text_message(
                    account_id=str(order.account.id),
                    to=order.customer_phone,
                    text=f"✅ Pagamento confirmado!\n\n"
                         f"Pedido #{order.order_number}\n"
                         f"Valor: R$ {order.total:.2f}\n\n"
                         f"Seu pedido está sendo preparado para envio.",
                    metadata={'order_id': str(order.id), 'notification_type': 'payment_confirmed'}
                )
            except Exception as e:
                logger.error(f"Failed to notify customer via WhatsApp: {str(e)}")
        
        # Send email notification
        if order.customer_email:
            try:
                email_service.send_payment_confirmed(order, order.customer_email)
            except Exception as e:
                logger.error(f"Failed to send payment confirmation email: {str(e)}")

    def _notify_customer_order_shipped(
        self,
        order: Order,
        tracking_code: str,
        carrier: str
    ) -> None:
        """Notify customer that order is shipped."""
        # Send WhatsApp notification (if enabled)
        if self._is_whatsapp_enabled(order):
            try:
                message_service = MessageService()
                tracking_info = ""
                if tracking_code:
                    tracking_info = f"\n\n📦 Código de rastreio: {tracking_code}"
                if carrier:
                    tracking_info += f"\nTransportadora: {carrier}"
                
                message_service.send_text_message(
                    account_id=str(order.account.id),
                    to=order.customer_phone,
                    text=f"🚚 Seu pedido foi enviado!\n\n"
                         f"Pedido #{order.order_number}{tracking_info}",
                    metadata={'order_id': str(order.id), 'notification_type': 'order_shipped'}
                )
            except Exception as e:
                logger.error(f"Failed to notify customer via WhatsApp: {str(e)}")
        
        # Send email notification
        if order.customer_email:
            try:
                email_service.send_order_shipped(order, order.customer_email, tracking_code)
            except Exception as e:
                logger.error(f"Failed to send order shipped email: {str(e)}")

    def _notify_customer_order_delivered(self, order: Order) -> None:
        """Notify customer that order is delivered."""
        # Send WhatsApp notification (if enabled)
        if self._is_whatsapp_enabled(order):
            try:
                message_service = MessageService()
                message_service.send_text_message(
                    account_id=str(order.account.id),
                    to=order.customer_phone,
                    text=f"📬 Pedido entregue!\n\n"
                         f"Pedido #{order.order_number} foi entregue com sucesso.\n\n"
                         f"Obrigado pela preferência! 🙏",
                    metadata={'order_id': str(order.id), 'notification_type': 'order_delivered'}
                )
            except Exception as e:
                logger.error(f"Failed to notify customer via WhatsApp: {str(e)}")
        
        # Send email notification
        if order.customer_email:
            try:
                email_service.send_order_delivered(order, order.customer_email)
            except Exception as e:
                logger.error(f"Failed to send order delivered email: {str(e)}")

    def _notify_customer_order_cancelled(self, order: Order, reason: str) -> None:
        """Notify customer that order is cancelled."""
        if not self._is_whatsapp_enabled(order):
            return
        try:
            message_service = MessageService()
            reason_text = f"\n\nMotivo: {reason}" if reason else ""
            
            message_service.send_text_message(
                account_id=str(order.account.id),
                to=order.customer_phone,
                text=f"❌ Pedido cancelado\n\n"
                     f"Pedido #{order.order_number} foi cancelado.{reason_text}\n\n"
                     f"Se tiver dúvidas, entre em contato conosco.",
                metadata={'order_id': str(order.id), 'notification_type': 'order_cancelled'}
            )
        except Exception as e:
            logger.error(f"Failed to notify customer: {str(e)}")
