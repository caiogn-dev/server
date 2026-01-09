"""
Payment Repository.
"""
import uuid
from typing import Optional, List
from uuid import UUID
from django.db.models import QuerySet
from django.utils import timezone
from ..models import Payment, PaymentGateway, PaymentWebhookEvent


class PaymentRepository:
    """Repository for Payment operations."""

    def get_by_id(self, payment_id: UUID) -> Optional[Payment]:
        """Get payment by ID."""
        try:
            return Payment.objects.select_related('order', 'gateway').get(
                id=payment_id,
                is_active=True
            )
        except Payment.DoesNotExist:
            return None

    def get_by_payment_id(self, payment_id: str) -> Optional[Payment]:
        """Get payment by payment ID."""
        try:
            return Payment.objects.select_related('order', 'gateway').get(
                payment_id=payment_id,
                is_active=True
            )
        except Payment.DoesNotExist:
            return None

    def get_by_external_id(self, external_id: str) -> Optional[Payment]:
        """Get payment by external ID."""
        try:
            return Payment.objects.select_related('order', 'gateway').get(
                external_id=external_id,
                is_active=True
            )
        except Payment.DoesNotExist:
            return None

    def get_by_order(self, order_id: UUID) -> QuerySet[Payment]:
        """Get payments by order."""
        return Payment.objects.filter(
            order_id=order_id,
            is_active=True
        ).select_related('gateway')

    def create(self, **kwargs) -> Payment:
        """Create a new payment."""
        if 'payment_id' not in kwargs:
            kwargs['payment_id'] = self._generate_payment_id()
        
        return Payment.objects.create(**kwargs)

    def update(self, payment: Payment, **kwargs) -> Payment:
        """Update a payment."""
        for key, value in kwargs.items():
            setattr(payment, key, value)
        payment.save()
        return payment

    def update_status(
        self,
        payment: Payment,
        new_status: str,
        gateway_response: dict = None
    ) -> Payment:
        """Update payment status."""
        payment.status = new_status
        
        if gateway_response:
            payment.gateway_response = gateway_response
        
        if new_status == Payment.PaymentStatus.COMPLETED:
            payment.paid_at = timezone.now()
        
        payment.save()
        return payment

    def mark_failed(
        self,
        payment: Payment,
        error_code: str,
        error_message: str
    ) -> Payment:
        """Mark payment as failed."""
        payment.status = Payment.PaymentStatus.FAILED
        payment.error_code = error_code
        payment.error_message = error_message
        payment.save()
        return payment

    def get_gateway_by_id(self, gateway_id: UUID) -> Optional[PaymentGateway]:
        """Get gateway by ID."""
        try:
            return PaymentGateway.objects.get(id=gateway_id, is_active=True)
        except PaymentGateway.DoesNotExist:
            return None

    def get_gateway_by_type(
        self,
        gateway_type: str,
        account_id: Optional[UUID] = None
    ) -> Optional[PaymentGateway]:
        """Get gateway by type."""
        queryset = PaymentGateway.objects.filter(
            gateway_type=gateway_type,
            is_enabled=True,
            is_active=True
        )
        
        if account_id:
            queryset = queryset.filter(accounts__id=account_id)
        
        return queryset.first()

    def create_webhook_event(self, **kwargs) -> PaymentWebhookEvent:
        """Create a webhook event."""
        return PaymentWebhookEvent.objects.create(**kwargs)

    def get_webhook_event_by_id(self, event_id: str) -> Optional[PaymentWebhookEvent]:
        """Get webhook event by event ID."""
        try:
            return PaymentWebhookEvent.objects.get(event_id=event_id)
        except PaymentWebhookEvent.DoesNotExist:
            return None

    def webhook_event_exists(self, event_id: str) -> bool:
        """Check if webhook event exists."""
        return PaymentWebhookEvent.objects.filter(event_id=event_id).exists()

    def update_webhook_event_status(
        self,
        event: PaymentWebhookEvent,
        status: str,
        error_message: str = ''
    ) -> PaymentWebhookEvent:
        """Update webhook event status."""
        event.processing_status = status
        event.error_message = error_message
        
        if status == PaymentWebhookEvent.ProcessingStatus.COMPLETED:
            event.processed_at = timezone.now()
        
        event.save()
        return event

    def _generate_payment_id(self) -> str:
        """Generate unique payment ID."""
        prefix = timezone.now().strftime('%Y%m%d')
        suffix = uuid.uuid4().hex[:8].upper()
        return f"PAY-{prefix}-{suffix}"
