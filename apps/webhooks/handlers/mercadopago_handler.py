"""
Mercado Pago webhook handler.
"""
import logging
from typing import Dict, Any
from django.http import HttpResponse

from .base import BaseHandler
from ..models import WebhookEvent

logger = logging.getLogger(__name__)


class MercadoPagoHandler(BaseHandler):
    """
    Handler for Mercado Pago payment webhooks.
    """
    
    def handle(self, event: WebhookEvent, payload: dict, headers: dict) -> Dict[str, Any]:
        """
        Process Mercado Pago webhook.
        Delegates to the existing store webhook service.
        """
        # Extract data from payload
        event_type = payload.get('type', '')
        data_id = payload.get('data', {}).get('id')
        
        logger.info(f"Processing Mercado Pago webhook: {event_type}, data_id={data_id}")
        
        # Process based on event type
        if event_type.startswith('payment'):
            result = self._handle_payment_webhook(payload)
        elif event_type.startswith('merchant_order'):
            result = self._handle_order_webhook(payload)
        else:
            result = {'processed': False, 'reason': 'unknown_event_type'}
        
        return result
    
    def _handle_payment_webhook(self, payload: dict) -> Dict[str, Any]:
        """Handle payment-related webhooks."""
        from django.db import DatabaseError
        from apps.stores.models import StoreOrder
        from apps.stores.services.checkout_service import CheckoutService, checkout_service
        
        data_id = payload.get('data', {}).get('id')
        if not data_id:
            return {'processed': False, 'error': 'Missing data.id'}

        payment_id = str(data_id)
        payment_status = (
            payload.get('status')
            or payload.get('data', {}).get('status')
            or payload.get('action')
        )

        if payment_status in {'payment.created', 'payment.updated'}:
            payment_status = None

        if not payment_status:
            try:
                order = StoreOrder.objects.filter(payment_id=payment_id).select_related('store').first()
            except DatabaseError as exc:
                logger.error("Mercado Pago webhook order lookup failed: %s", exc)
                return {
                    'processed': False,
                    'payment_id': payment_id,
                    'reason': 'order_lookup_failed',
                }
            if not order:
                return {
                    'processed': False,
                    'payment_id': payment_id,
                    'reason': 'order_not_found',
                }

            try:
                import mercadopago
            except ImportError:
                return {
                    'processed': False,
                    'payment_id': payment_id,
                    'reason': 'mercadopago_sdk_unavailable',
                }

            credentials = checkout_service.get_payment_credentials(order.store)
            if not credentials:
                return {
                    'processed': False,
                    'payment_id': payment_id,
                    'order_id': str(order.id),
                    'reason': 'payment_credentials_not_found',
                }

            sdk = mercadopago.SDK(credentials['access_token'])
            response = sdk.payment().get(payment_id)
            if response.get('status') != 200:
                return {
                    'processed': False,
                    'payment_id': payment_id,
                    'order_id': str(order.id),
                    'reason': 'payment_fetch_failed',
                    'status_code': response.get('status'),
                }
            payment_status = response.get('response', {}).get('status')

        order = CheckoutService.process_payment_webhook(payment_id, payment_status)

        return {
            'processed': bool(order),
            'payment_id': payment_id,
            'order_id': str(order.id) if order else None,
            'order_number': order.order_number if order else '',
            'payment_status': payment_status,
            'action': 'payment_updated',
        }
    
    def _handle_order_webhook(self, payload: dict) -> Dict[str, Any]:
        """Handle order-related webhooks."""
        data_id = payload.get('data', {}).get('id')
        
        return {
            'processed': True,
            'order_id': data_id,
            'action': 'merchant_order_updated'
        }
    
    def handle_verification(self, request) -> HttpResponse:
        """Mercado Pago doesn't use challenge-response."""
        return HttpResponse("OK", status=200)
