"""
Messenger webhook handler — registrado no dispatcher central.
"""
import hmac
import logging
from typing import Dict, Any
from django.conf import settings
from django.http import HttpResponse

from .base import BaseHandler
from ..models import WebhookEvent

logger = logging.getLogger(__name__)


class MessengerHandler(BaseHandler):
    """
    Handler para webhooks do Facebook Messenger via Meta Graph API.
    Delega o processamento ao MessengerWebhookService.
    """

    def handle(self, event: WebhookEvent, payload: dict, headers: dict) -> Dict[str, Any]:
        from apps.messaging.services.messenger_webhook_service import MessengerWebhookService

        service = MessengerWebhookService()
        result = service.process_webhook(payload)

        logger.info(
            f"Messenger webhook processed: {result.get('processed', 0)} events"
        )
        return result

    def handle_verification(self, request) -> HttpResponse:
        """Responde ao desafio hub.challenge do Meta."""
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        verify_token = getattr(settings, 'MESSENGER_WEBHOOK_VERIFY_TOKEN',
                               getattr(settings, 'WHATSAPP_WEBHOOK_VERIFY_TOKEN', ''))

        if not verify_token:
            logger.warning("MESSENGER_WEBHOOK_VERIFY_TOKEN not configured")
            return HttpResponse("Verification token not configured", status=500)

        tokens_match = bool(verify_token) and hmac.compare_digest(
            token.encode() if token else b'',
            verify_token.encode()
        )

        if mode == 'subscribe' and tokens_match:
            logger.info("Messenger webhook verified successfully")
            return HttpResponse(challenge, status=200)

        logger.warning(f"Messenger webhook verification failed: mode={mode}, token_match={tokens_match}")
        return HttpResponse("Verification failed", status=403)
