"""
Payment Service - Business logic for payment processing.

Integrates with payment gateways (Mercado Pago, etc.) and manages
payment lifecycle while syncing with StoreOrder.
"""
import logging
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any, List
from django.utils import timezone
from django.db import transaction

from apps.stores.models import (
    StoreOrder,
    StorePayment,
    StorePaymentGateway,
    StorePaymentWebhookEvent,
)

logger = logging.getLogger(__name__)


class PaymentService:
    """Service for managing payments."""

    def __init__(self):
        self.logger = logger

    def create_payment(
        self,
        order_id: str,
        gateway_id: Optional[str] = None,
        amount: Optional[Decimal] = None,
        payment_method: str = '',
        payer_email: str = '',
        payer_name: str = '',
        payer_document: str = '',
        metadata: Optional[Dict] = None,
    ) -> StorePayment:
        """Create a new payment for an order."""
        from apps.stores.models import StoreOrder

        order = StoreOrder.objects.get(id=order_id)
        
        # Use order total if amount not provided
        if amount is None:
            amount = order.total

        # Get default gateway if not specified
        gateway = None
        if gateway_id:
            gateway = StorePaymentGateway.objects.filter(id=gateway_id).first()
        else:
            gateway = StorePaymentGateway.objects.filter(
                store=order.store,
                is_enabled=True,
                is_default=True
            ).first()

        payment = StorePayment.objects.create(
            order=order,
            gateway=gateway,
            amount=amount,
            payment_method=payment_method,
            payer_email=payer_email or order.customer_email,
            payer_name=payer_name or order.customer_name,
            payer_document=payer_document,
            metadata=metadata or {},
            external_reference=order.order_number,
        )

        self.logger.info(f"Created payment {payment.payment_id} for order {order.order_number}")
        return payment

    def process_payment(
        self,
        payment_id: str,
        gateway_type: Optional[str] = None,
    ) -> StorePayment:
        """Process a payment through the gateway."""
        payment = StorePayment.objects.select_related('order', 'gateway').get(id=payment_id)

        if not payment.can_process():
            raise ValueError(f"Payment cannot be processed. Current status: {payment.status}")

        if not payment.gateway:
            raise ValueError("No gateway configured for this payment")

        payment.status = StorePayment.PaymentStatus.PROCESSING
        payment.save()

        # Process based on gateway type
        if payment.gateway.gateway_type == StorePaymentGateway.GatewayType.MERCADOPAGO:
            return self._process_mercadopago(payment)
        elif payment.gateway.gateway_type == StorePaymentGateway.GatewayType.PIX:
            return self._process_pix(payment)
        else:
            # For other gateways, just mark as processing
            # The actual processing would be handled by the gateway's SDK
            self.logger.info(f"Payment {payment.payment_id} marked as processing for gateway {payment.gateway.gateway_type}")
            return payment

    def _process_mercadopago(self, payment: StorePayment) -> StorePayment:
        """Process payment through Mercado Pago."""
        try:
            import mercadopago
            
            credentials = payment.gateway.get_mercadopago_credentials()
            if not credentials or not credentials.get('access_token'):
                raise ValueError("Mercado Pago credentials not configured")

            sdk = mercadopago.SDK(credentials['access_token'])

            # Create preference
            preference_data = {
                "items": [
                    {
                        "title": f"Order {payment.order.order_number}",
                        "quantity": 1,
                        "unit_price": float(payment.amount),
                        "currency_id": payment.currency,
                    }
                ],
                "payer": {
                    "email": payment.payer_email,
                    "name": payment.payer_name,
                },
                "external_reference": payment.payment_id,
                "notification_url": payment.gateway.webhook_url or "",
                "back_urls": {
                    "success": f"{payment.order.store.url}/payment/success",
                    "failure": f"{payment.order.store.url}/payment/failure",
                    "pending": f"{payment.order.store.url}/payment/pending",
                },
                "auto_return": "approved",
            }

            preference_response = sdk.preference().create(preference_data)
            
            if preference_response["status"] == 201:
                preference = preference_response["response"]
                payment.payment_url = preference.get("init_point")
                payment.gateway_response = preference
                payment.save()
                
                self.logger.info(f"Mercado Pago preference created for payment {payment.payment_id}")
            else:
                raise Exception(f"Failed to create preference: {preference_response}")

            return payment

        except Exception as e:
            self.logger.error(f"Error processing Mercado Pago payment: {e}")
            payment.status = StorePayment.PaymentStatus.FAILED
            payment.error_code = "mp_error"
            payment.error_message = str(e)
            payment.save()
            raise

    def _process_pix(self, payment: StorePayment) -> StorePayment:
        """Process PIX payment."""
        # PIX processing would be implemented here
        # For now, just mark as processing
        payment.payment_method = StorePayment.PaymentMethod.PIX
        payment.save()
        return payment

    def confirm_payment(
        self,
        payment_id: str,
        external_id: str = '',
        gateway_response: Optional[Dict] = None,
    ) -> StorePayment:
        """Confirm a payment as completed."""
        payment = StorePayment.objects.select_related('order').get(id=payment_id)

        if not payment.can_confirm():
            raise ValueError(f"Payment cannot be confirmed. Current status: {payment.status}")

        payment.status = StorePayment.PaymentStatus.COMPLETED
        payment.external_id = external_id or payment.external_id
        payment.paid_at = timezone.now()
        
        if gateway_response:
            payment.gateway_response.update(gateway_response)
        
        payment.save()

        self.logger.info(f"Payment {payment.payment_id} confirmed")
        return payment

    def fail_payment(
        self,
        payment_id: str,
        error_code: str,
        error_message: str,
        gateway_response: Optional[Dict] = None,
    ) -> StorePayment:
        """Mark a payment as failed."""
        payment = StorePayment.objects.get(id=payment_id)

        payment.status = StorePayment.PaymentStatus.FAILED
        payment.error_code = error_code
        payment.error_message = error_message
        
        if gateway_response:
            payment.gateway_response.update(gateway_response)
        
        payment.save()

        self.logger.warning(f"Payment {payment.payment_id} failed: {error_code} - {error_message}")
        return payment

    def cancel_payment(self, payment_id: str) -> StorePayment:
        """Cancel a payment."""
        payment = StorePayment.objects.get(id=payment_id)

        if not payment.can_cancel():
            raise ValueError(f"Payment cannot be cancelled. Current status: {payment.status}")

        payment.status = StorePayment.PaymentStatus.CANCELLED
        payment.save()

        self.logger.info(f"Payment {payment.payment_id} cancelled")
        return payment

    def refund_payment(
        self,
        payment_id: str,
        amount: Optional[Decimal] = None,
        reason: str = '',
    ) -> StorePayment:
        """Refund a payment (partial or full)."""
        payment = StorePayment.objects.select_related('order', 'gateway').get(id=payment_id)

        if not payment.can_refund():
            raise ValueError(f"Payment cannot be refunded. Status: {payment.status}, Refunded: {payment.refunded_amount}")

        refund_amount = amount or payment.get_refundable_amount()
        
        if refund_amount > payment.get_refundable_amount():
            raise ValueError(f"Refund amount {refund_amount} exceeds refundable amount {payment.get_refundable_amount()}")

        # Process refund through gateway if needed
        if payment.gateway and payment.gateway.gateway_type == StorePaymentGateway.GatewayType.MERCADOPAGO:
            self._refund_mercadopago(payment, refund_amount)

        payment.refunded_amount += refund_amount
        
        if payment.refunded_amount >= payment.amount:
            payment.status = StorePayment.PaymentStatus.REFUNDED
        else:
            payment.status = StorePayment.PaymentStatus.PARTIALLY_REFUNDED
        
        payment.refunded_at = timezone.now()
        payment.metadata['refund_reason'] = reason
        payment.save()

        self.logger.info(f"Payment {payment.payment_id} refunded: {refund_amount}")
        return payment

    def _refund_mercadopago(self, payment: StorePayment, amount: Decimal) -> None:
        """Process refund through Mercado Pago."""
        try:
            import mercadopago
            
            credentials = payment.gateway.get_mercadopago_credentials()
            if not credentials:
                raise ValueError("Mercado Pago credentials not configured")

            sdk = mercadopago.SDK(credentials['access_token'])

            refund_data = {
                "amount": float(amount),
            }

            refund_response = sdk.refund().create(payment.external_id, refund_data)
            
            if refund_response["status"] not in [200, 201]:
                raise Exception(f"Refund failed: {refund_response}")

        except Exception as e:
            self.logger.error(f"Error processing Mercado Pago refund: {e}")
            raise

    def list_order_payments(self, order_id: str) -> List[StorePayment]:
        """Get all payments for an order."""
        return StorePayment.objects.filter(order_id=order_id).order_by('-created_at')

    def get_payment_by_external_id(self, external_id: str) -> Optional[StorePayment]:
        """Get payment by external ID (from gateway)."""
        return StorePayment.objects.filter(external_id=external_id).first()

    def handle_webhook(
        self,
        gateway: StorePaymentGateway,
        event_type: str,
        event_id: str,
        payload: Dict,
        headers: Dict,
    ) -> StorePaymentWebhookEvent:
        """Handle incoming webhook from payment gateway."""
        # Check for duplicate
        existing = StorePaymentWebhookEvent.objects.filter(
            gateway=gateway,
            event_id=event_id
        ).first()
        
        if existing:
            existing.mark_duplicate()
            return existing

        # Create webhook event
        event = StorePaymentWebhookEvent.objects.create(
            gateway=gateway,
            event_type=event_type,
            event_id=event_id,
            payload=payload,
            headers=headers,
        )

        try:
            # Process based on gateway type
            if gateway.gateway_type == StorePaymentGateway.GatewayType.MERCADOPAGO:
                self._process_mercadopago_webhook(event)
            else:
                event.processing_status = StorePaymentWebhookEvent.ProcessingStatus.IGNORED
                event.save()

        except Exception as e:
            event.mark_failed(str(e))
            raise

        return event

    def _process_mercadopago_webhook(self, event: StorePaymentWebhookEvent) -> None:
        """Process Mercado Pago webhook."""
        import mercadopago
        
        payload = event.payload
        topic = payload.get('type') or payload.get('topic')
        
        if topic == 'payment':
            payment_id = payload.get('data', {}).get('id')
            
            if not payment_id:
                event.mark_failed("No payment ID in webhook")
                return

            # Fetch payment details from MP
            credentials = event.gateway.get_mercadopago_credentials()
            sdk = mercadopago.SDK(credentials['access_token'])
            payment_response = sdk.payment().get(payment_id)
            
            if payment_response['status'] != 200:
                event.mark_failed(f"Failed to fetch payment: {payment_response}")
                return

            mp_payment = payment_response['response']
            external_ref = mp_payment.get('external_reference')
            
            # Find our payment
            payment = self.get_payment_by_external_id(str(payment_id))
            
            if not payment and external_ref:
                payment = StorePayment.objects.filter(payment_id=external_ref).first()
            
            if payment:
                event.payment = payment
                event.order = payment.order
                event.save()

                # Update payment status
                status = mp_payment.get('status')
                
                if status == 'approved':
                    self.confirm_payment(
                        str(payment.id),
                        external_id=str(payment_id),
                        gateway_response=mp_payment,
                    )
                elif status in ['rejected', 'cancelled']:
                    self.fail_payment(
                        str(payment.id),
                        error_code=mp_payment.get('status_detail', 'unknown'),
                        error_message=f"Payment {status}",
                        gateway_response=mp_payment,
                    )

                event.mark_processed()
            else:
                event.processing_status = StorePaymentWebhookEvent.ProcessingStatus.IGNORED
                event.save()

        elif topic == 'merchant_order':
            # Handle merchant order updates
            event.processing_status = StorePaymentWebhookEvent.ProcessingStatus.IGNORED
            event.save()
        else:
            event.processing_status = StorePaymentWebhookEvent.ProcessingStatus.IGNORED
            event.save()


def get_payment_service() -> PaymentService:
    """Get payment service instance."""
    return PaymentService()
