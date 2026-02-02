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
        
        service = WebhookService()
        
        # Process the webhook
        result = service.process_webhook(payload)
        
        return {
            'processed': True,
            'messages_processed': len(result.get('messages', [])),
            'statuses_processed': len(result.get('statuses', [])),
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
