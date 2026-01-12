"""
Payment Service - Business logic for payment management.
"""
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from apps.core.exceptions import NotFoundError, ValidationError, PaymentGatewayError
from apps.core.utils import generate_idempotency_key
from apps.orders.models import Order
from apps.orders.services import OrderService
from ..models import Payment, PaymentGateway, PaymentWebhookEvent
from ..repositories import PaymentRepository

logger = logging.getLogger(__name__)


class PaymentService:
    """Service for payment operations."""

    def __init__(self):
        self.repo = PaymentRepository()

    def _send_payment_notification(
        self,
        payment: Payment,
        status: str,
        error_code: str = None,
        error_message: str = None
    ) -> None:
        """Send WebSocket notification for payment status change."""
        try:
            channel_layer = get_channel_layer()
            if not channel_layer or not payment.order:
                return
            
            message = {
                'type': 'payment_status',
                'order_id': str(payment.order.id),
                'payment_id': str(payment.id),
                'status': status,
                'payment_method': payment.payment_method,
                'amount': float(payment.amount),
                'error_code': error_code,
                'error_message': error_message,
                'timestamp': timezone.now().isoformat(),
            }
            
            # Send to order-specific group
            async_to_sync(channel_layer.group_send)(
                f"payment_order_{payment.order.id}",
                message
            )
            
            logger.debug(f"Payment notification sent for order {payment.order.id}")
        except Exception as e:
            logger.warning(f"Failed to send payment notification: {str(e)}")

    def create_payment(
        self,
        order_id: str,
        amount: float,
        gateway_id: Optional[str] = None,
        payment_method: str = '',
        payer_email: str = '',
        payer_name: str = '',
        payer_document: str = '',
        metadata: Dict = None
    ) -> Payment:
        """Create a new payment."""
        try:
            order = Order.objects.get(id=order_id, is_active=True)
        except Order.DoesNotExist:
            raise NotFoundError(message="Order not found")
        
        gateway = None
        if gateway_id:
            gateway = self.repo.get_gateway_by_id(gateway_id)
            if not gateway:
                raise NotFoundError(message="Payment gateway not found")
        
        payment = self.repo.create(
            order=order,
            gateway=gateway,
            amount=amount,
            net_amount=amount,
            payment_method=payment_method,
            payer_email=payer_email,
            payer_name=payer_name,
            payer_document=payer_document,
            metadata=metadata or {}
        )
        
        logger.info(f"Payment created: {payment.payment_id}")
        return payment

    def get_payment(self, payment_id: str) -> Payment:
        """Get payment by ID."""
        payment = self.repo.get_by_id(payment_id)
        if not payment:
            payment = self.repo.get_by_payment_id(payment_id)
        if not payment:
            raise NotFoundError(message="Payment not found")
        return payment

    def get_payment_by_external_id(self, external_id: str) -> Optional[Payment]:
        """Get payment by external ID."""
        return self.repo.get_by_external_id(external_id)

    def list_order_payments(self, order_id: str) -> List[Payment]:
        """List payments for an order."""
        return list(self.repo.get_by_order(order_id))

    def process_payment(
        self,
        payment_id: str,
        gateway_type: str = None
    ) -> Payment:
        """Process a payment through gateway."""
        payment = self.get_payment(payment_id)
        
        if payment.status != Payment.PaymentStatus.PENDING:
            raise ValidationError(
                message=f"Cannot process payment with status: {payment.status}"
            )
        
        gateway = payment.gateway
        if not gateway and gateway_type:
            gateway = self.repo.get_gateway_by_type(gateway_type)
            if gateway:
                payment.gateway = gateway
                payment.save(update_fields=['gateway'])
        
        if not gateway:
            raise ValidationError(message="No payment gateway configured")
        
        payment = self.repo.update_status(
            payment,
            Payment.PaymentStatus.PROCESSING
        )
        
        logger.info(f"Payment processing: {payment.payment_id}")
        return payment

    def confirm_payment(
        self,
        payment_id: str,
        external_id: str = '',
        gateway_response: Dict = None
    ) -> Payment:
        """Confirm a payment as completed."""
        payment = self.get_payment(payment_id)
        
        if payment.status == Payment.PaymentStatus.COMPLETED:
            logger.info(f"Payment already completed: {payment.payment_id}")
            return payment
        
        if external_id:
            payment.external_id = external_id
        
        payment = self.repo.update_status(
            payment,
            Payment.PaymentStatus.COMPLETED,
            gateway_response
        )
        
        order_service = OrderService()
        try:
            order_service.mark_paid(
                str(payment.order.id),
                payment_reference=payment.payment_id
            )
        except Exception as e:
            logger.error(f"Failed to update order status: {str(e)}")
        
        # Send WebSocket notification
        self._send_payment_notification(payment, 'completed')
        
        logger.info(f"Payment confirmed: {payment.payment_id}")
        return payment

    def fail_payment(
        self,
        payment_id: str,
        error_code: str,
        error_message: str,
        gateway_response: Dict = None
    ) -> Payment:
        """Mark a payment as failed."""
        payment = self.get_payment(payment_id)
        
        if gateway_response:
            payment.gateway_response = gateway_response
            payment.save(update_fields=['gateway_response'])
        
        payment = self.repo.mark_failed(payment, error_code, error_message)
        
        # Send WebSocket notification
        self._send_payment_notification(payment, 'failed', error_code, error_message)
        
        logger.warning(f"Payment failed: {payment.payment_id} - {error_code}")
        return payment

    def cancel_payment(self, payment_id: str) -> Payment:
        """Cancel a payment."""
        payment = self.get_payment(payment_id)
        
        if payment.status not in [
            Payment.PaymentStatus.PENDING,
            Payment.PaymentStatus.PROCESSING
        ]:
            raise ValidationError(
                message=f"Cannot cancel payment with status: {payment.status}"
            )
        
        payment = self.repo.update_status(
            payment,
            Payment.PaymentStatus.CANCELLED
        )
        
        # Send WebSocket notification
        self._send_payment_notification(payment, 'cancelled')
        
        logger.info(f"Payment cancelled: {payment.payment_id}")
        return payment

    def refund_payment(
        self,
        payment_id: str,
        amount: Optional[float] = None,
        reason: str = ''
    ) -> Payment:
        """Refund a payment."""
        payment = self.get_payment(payment_id)
        
        if payment.status != Payment.PaymentStatus.COMPLETED:
            raise ValidationError(
                message=f"Cannot refund payment with status: {payment.status}"
            )
        
        refund_amount = amount or float(payment.amount)
        
        if refund_amount > float(payment.amount - payment.refunded_amount):
            raise ValidationError(message="Refund amount exceeds available amount")
        
        payment.refunded_amount += refund_amount
        
        if payment.refunded_amount >= payment.amount:
            payment.status = Payment.PaymentStatus.REFUNDED
        else:
            payment.status = Payment.PaymentStatus.PARTIALLY_REFUNDED
        
        payment.save()
        
        logger.info(f"Payment refunded: {payment.payment_id} - Amount: {refund_amount}")
        return payment

    def process_webhook(
        self,
        gateway_id: str,
        event_type: str,
        event_id: str,
        payload: Dict,
        headers: Dict
    ) -> PaymentWebhookEvent:
        """Process a payment webhook."""
        gateway = self.repo.get_gateway_by_id(gateway_id)
        if not gateway:
            raise NotFoundError(message="Payment gateway not found")
        
        idempotency_key = generate_idempotency_key(gateway_id, event_id)
        
        if self.repo.webhook_event_exists(idempotency_key):
            logger.info(f"Duplicate webhook event: {idempotency_key}")
            existing = self.repo.get_webhook_event_by_id(idempotency_key)
            return existing
        
        event = self.repo.create_webhook_event(
            gateway=gateway,
            event_id=idempotency_key,
            event_type=event_type,
            payload=payload,
            headers=headers
        )
        
        logger.info(f"Payment webhook event created: {event.id}")
        return event

    def handle_webhook_event(self, event_id: str) -> PaymentWebhookEvent:
        """Handle a payment webhook event."""
        event = self.repo.get_webhook_event_by_id(event_id)
        if not event:
            raise NotFoundError(message="Webhook event not found")
        
        if event.processing_status == PaymentWebhookEvent.ProcessingStatus.COMPLETED:
            return event
        
        self.repo.update_webhook_event_status(
            event,
            PaymentWebhookEvent.ProcessingStatus.PROCESSING
        )
        
        try:
            self._process_gateway_event(event)
            
            self.repo.update_webhook_event_status(
                event,
                PaymentWebhookEvent.ProcessingStatus.COMPLETED
            )
            
        except Exception as e:
            logger.error(f"Error processing webhook event: {str(e)}")
            event.retry_count += 1
            self.repo.update_webhook_event_status(
                event,
                PaymentWebhookEvent.ProcessingStatus.FAILED,
                str(e)
            )
            raise
        
        return event

    def _process_gateway_event(self, event: PaymentWebhookEvent) -> None:
        """Process gateway-specific webhook event."""
        gateway = event.gateway
        payload = event.payload
        event_type = event.event_type
        
        external_id = self._extract_external_id(gateway.gateway_type, payload)
        
        if not external_id:
            logger.warning(f"Could not extract external ID from webhook: {event.id}")
            return
        
        payment = self.get_payment_by_external_id(external_id)
        
        if not payment:
            logger.warning(f"Payment not found for external ID: {external_id}")
            return
        
        event.payment = payment
        event.save(update_fields=['payment'])
        
        status = self._extract_status(gateway.gateway_type, event_type, payload)
        
        if status == 'completed':
            self.confirm_payment(
                str(payment.id),
                external_id=external_id,
                gateway_response=payload
            )
        elif status == 'failed':
            error_code = payload.get('error_code', 'unknown')
            error_message = payload.get('error_message', 'Payment failed')
            self.fail_payment(
                str(payment.id),
                error_code,
                error_message,
                payload
            )
        elif status == 'cancelled':
            self.cancel_payment(str(payment.id))

    def _extract_external_id(self, gateway_type: str, payload: Dict) -> Optional[str]:
        """Extract external ID from webhook payload."""
        if gateway_type == PaymentGateway.GatewayType.STRIPE:
            return payload.get('data', {}).get('object', {}).get('id')
        elif gateway_type == PaymentGateway.GatewayType.MERCADOPAGO:
            return str(payload.get('data', {}).get('id', ''))
        elif gateway_type == PaymentGateway.GatewayType.PIX:
            return payload.get('txid') or payload.get('e2eid')
        else:
            return payload.get('id') or payload.get('payment_id') or payload.get('external_id')

    def _extract_status(
        self,
        gateway_type: str,
        event_type: str,
        payload: Dict
    ) -> str:
        """Extract payment status from webhook payload."""
        if gateway_type == PaymentGateway.GatewayType.STRIPE:
            if event_type == 'payment_intent.succeeded':
                return 'completed'
            elif event_type == 'payment_intent.payment_failed':
                return 'failed'
            elif event_type == 'payment_intent.canceled':
                return 'cancelled'
        elif gateway_type == PaymentGateway.GatewayType.MERCADOPAGO:
            status = payload.get('data', {}).get('status', '')
            if status == 'approved':
                return 'completed'
            elif status in ['rejected', 'cancelled']:
                return 'failed'
        elif gateway_type == PaymentGateway.GatewayType.PIX:
            status = payload.get('status', '')
            if status == 'CONCLUIDA':
                return 'completed'
            elif status in ['REMOVIDA_PELO_USUARIO_RECEBEDOR', 'REMOVIDA_PELO_PSP']:
                return 'cancelled'
        
        return payload.get('status', 'unknown')

    def get_gateway(self, gateway_id: str) -> PaymentGateway:
        """Get payment gateway."""
        gateway = self.repo.get_gateway_by_id(gateway_id)
        if not gateway:
            raise NotFoundError(message="Payment gateway not found")
        return gateway

    def list_gateways(self, account_id: Optional[str] = None) -> List[PaymentGateway]:
        """List payment gateways."""
        queryset = PaymentGateway.objects.filter(is_enabled=True, is_active=True)
        
        if account_id:
            queryset = queryset.filter(accounts__id=account_id)
        
        return list(queryset)
