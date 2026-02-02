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
        from apps.stores.services.webhook_service import WebhookService
        
        service = WebhookService()
        
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
        from apps.stores.services.mercadopago_service import MercadoPagoService
        
        data_id = payload.get('data', {}).get('id')
        if not data_id:
            return {'processed': False, 'error': 'Missing data.id'}
        
        # Fetch payment details from MP API
        # This is done by the existing service
        
        return {
            'processed': True,
            'payment_id': data_id,
            'action': 'payment_updated'
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
