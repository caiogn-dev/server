"""
Webhook Dispatcher - Routes incoming webhooks to appropriate handlers.
"""
import logging
import hmac
import hashlib
from typing import Dict, Any, Optional, Type
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from .models import WebhookEvent, WebhookEndpoint
from .handlers.base import BaseHandler

logger = logging.getLogger(__name__)


class WebhookDispatcherView(View):
    """
    Central webhook receiver view.
    Routes webhooks from various providers to their handlers.
    """
    
    # Registry of handlers by provider
    _handlers: Dict[str, Type[BaseHandler]] = {}
    
    @classmethod
    def register_handler(cls, provider: str, handler_class: Type[BaseHandler]):
        """Register a handler for a provider."""
        cls._handlers[provider] = handler_class
        logger.info(f"Registered webhook handler for {provider}: {handler_class.__name__}")
    
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request, provider: str, **kwargs):
        """Handle POST requests."""
        return self._handle_webhook(request, provider, **kwargs)
    
    def get(self, request, provider: str, **kwargs):
        """Handle GET requests (for verification challenges)."""
        return self._handle_verification(request, provider, **kwargs)
    
    def _handle_webhook(self, request, provider: str, **kwargs) -> HttpResponse:
        """Process incoming webhook."""
        # Get handler
        handler_class = self._handlers.get(provider)
        if not handler_class:
            logger.warning(f"No handler registered for provider: {provider}")
            return HttpResponse("Provider not found", status=404)
        
        # Parse payload
        try:
            if request.content_type == 'application/json':
                payload = request.json()
            else:
                payload = dict(request.POST)
        except Exception as e:
            logger.warning(f"Failed to parse webhook payload: {e}")
            payload = {'raw_body': request.body.decode('utf-8', errors='replace')}
        
        # Get headers
        headers = dict(request.headers)
        
        # Extract event type
        event_type = self._extract_event_type(provider, payload, headers)
        event_id = self._extract_event_id(provider, payload, headers)
        
        # Check for duplicates
        if event_id:
            existing = WebhookEvent.objects.filter(
                provider=provider,
                event_id=event_id,
                status__in=[WebhookEvent.Status.COMPLETED, WebhookEvent.Status.DUPLICATE]
            ).first()
            
            if existing:
                logger.info(f"Duplicate webhook event: {event_id}")
                return HttpResponse("OK", status=200)
        
        # Create event log
        event = WebhookEvent.objects.create(
            provider=provider,
            event_type=event_type,
            event_id=event_id or '',
            payload=payload,
            headers=headers,
            query_params=dict(request.GET),
            status=WebhookEvent.Status.PENDING
        )
        
        # Verify signature
        signature_valid = self._verify_signature(request, provider, payload)
        event.signature_valid = signature_valid
        event.save(update_fields=['signature_valid'])
        
        # Process with handler
        try:
            handler = handler_class()
            result = handler.handle(event, payload, headers)
            
            # Update event status
            event.status = WebhookEvent.Status.COMPLETED
            event.processed_at = timezone.now()
            event.handler_result = result or {}
            event.save(update_fields=['status', 'processed_at', 'handler_result'])
            
            return HttpResponse("OK", status=200)
            
        except Exception as e:
            logger.exception(f"Error handling webhook: {e}")
            
            event.status = WebhookEvent.Status.FAILED
            event.error_message = str(e)
            event.save(update_fields=['status', 'error_message'])
            
            # Still return 200 to prevent retries from provider
            return HttpResponse("OK", status=200)
    
    def _handle_verification(self, request, provider: str, **kwargs) -> HttpResponse:
        """Handle verification challenge."""
        handler_class = self._handlers.get(provider)
        if not handler_class:
            return HttpResponse("Provider not found", status=404)
        
        try:
            handler = handler_class()
            response = handler.handle_verification(request)
            return response
        except Exception as e:
            logger.exception(f"Error handling verification: {e}")
            return HttpResponse("Verification failed", status=403)
    
    def _extract_event_type(self, provider: str, payload: dict, headers: dict) -> str:
        """Extract event type from payload or headers."""
        # Provider-specific extraction
        if provider == 'whatsapp':
            # WhatsApp sends in payload.entry[].changes[].value.messages[]
            try:
                entry = payload.get('entry', [{}])[0]
                changes = entry.get('changes', [{}])[0]
                value = changes.get('value', {})
                
                if value.get('messages'):
                    return 'message'
                elif value.get('statuses'):
                    return 'status_update'
            except (KeyError, IndexError):
                pass
        
        elif provider == 'mercadopago':
            # Mercado Pago sends type in query params or payload
            return payload.get('type', 'unknown')
        
        return 'unknown'
    
    def _extract_event_id(self, provider: str, payload: dict, headers: dict) -> Optional[str]:
        """Extract unique event ID for deduplication."""
        if provider == 'whatsapp':
            # WhatsApp message ID
            try:
                entry = payload.get('entry', [{}])[0]
                changes = entry.get('changes', [{}])[0]
                value = changes.get('value', {})
                messages = value.get('messages', [])
                if messages:
                    return messages[0].get('id')
            except (KeyError, IndexError):
                pass
        
        return None
    
    def _verify_signature(self, request, provider: str, payload: dict) -> Optional[bool]:
        """Verify webhook signature."""
        try:
            endpoint = WebhookEndpoint.objects.get(provider=provider, is_active=True)
            
            if not endpoint.secret:
                return None  # No verification configured
            
            signature_header = request.headers.get(endpoint.signature_header)
            if not signature_header:
                return False
            
            # Calculate expected signature
            if provider == 'whatsapp' or provider == 'instagram':
                # Meta signature format: sha256=<hmac>
                expected = hmac.new(
                    endpoint.secret.encode(),
                    request.body,
                    hashlib.sha256
                ).hexdigest()
                
                if signature_header.startswith('sha256='):
                    return hmac.compare_digest(signature_header[7:], expected)
            
            elif provider == 'mercadopago':
                # Mercado Pago signature format
                expected = hmac.new(
                    endpoint.secret.encode(),
                    request.body,
                    hashlib.sha256
                ).hexdigest()
                return hmac.compare_digest(signature_header, expected)
            
            return None
            
        except WebhookEndpoint.DoesNotExist:
            return None
        except Exception as e:
            logger.warning(f"Signature verification error: {e}")
            return False


# Import handlers to register them
def register_default_handlers():
    """Register default handlers."""
    from .handlers.whatsapp_handler import WhatsAppHandler
    from .handlers.mercadopago_handler import MercadoPagoHandler
    
    WebhookDispatcherView.register_handler('whatsapp', WhatsAppHandler)
    WebhookDispatcherView.register_handler('mercadopago', MercadoPagoHandler)
    # Add more handlers as needed


# Auto-register on module load
from django.utils import timezone
register_default_handlers()
