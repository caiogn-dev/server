"""
WhatsApp webhook handler.
"""
import logging
from typing import Dict, Any, Optional
from django.http import HttpResponse

from .base import BaseHandler
from ..models import WebhookEvent

logger = logging.getLogger(__name__)


class WhatsAppHandler(BaseHandler):
    """
    Handler for WhatsApp webhooks from Meta.
    """
    
    def handle(self, event: WebhookEvent, payload: dict, headers: dict) -> Dict[str, Any]:
        """
        Process WhatsApp webhook.
        Delegates to the existing WhatsApp webhook service.
        """
        from apps.whatsapp.services import WebhookService
        from apps.whatsapp.models import WebhookEvent as WhatsAppWebhookEvent
        
        service = WebhookService()
        
        # Process the webhook (creates WebhookEvent records)
        whatsapp_events = service.process_webhook(payload, headers)
        
        # Dispatch each event to Celery for processing
        processed_count = 0
        for whatsapp_event in whatsapp_events:
            try:
                from apps.whatsapp.tasks import process_webhook_event
                process_webhook_event.delay(str(whatsapp_event.id))
                processed_count += 1
                logger.info(f"Dispatched WhatsApp event {whatsapp_event.id} to Celery")
            except Exception as e:
                # If Celery fails, process synchronously
                logger.warning(f"Celery dispatch failed for event {whatsapp_event.id}: {e}")
                try:
                    service.process_event(whatsapp_event, post_process_inbound=True)
                    processed_count += 1
                    logger.info(f"Processed event {whatsapp_event.id} synchronously")
                except Exception as sync_error:
                    logger.error(f"Sync processing failed for event {whatsapp_event.id}: {sync_error}")
        
        return {
            'processed': True,
            'events_created': len(whatsapp_events),
            'events_dispatched': processed_count,
        }
    
    def handle_verification(self, request) -> HttpResponse:
        """
        Handle WhatsApp verification challenge.
        """
        from django.conf import settings
        
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        
        verify_token = getattr(settings, 'WHATSAPP_WEBHOOK_VERIFY_TOKEN', '')
        
        if mode == 'subscribe' and token == verify_token:
            logger.info("WhatsApp webhook verified successfully")
            return HttpResponse(challenge, status=200)
        
        logger.warning(f"WhatsApp webhook verification failed: mode={mode}, token_match={token == verify_token}")
        return HttpResponse("Verification failed", status=403)
