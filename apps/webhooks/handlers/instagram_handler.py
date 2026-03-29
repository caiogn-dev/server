"""
Instagram webhook handler — registrado no dispatcher central.
"""
import hmac
import logging
from typing import Dict, Any
from django.conf import settings
from django.http import HttpResponse

from .base import BaseHandler
from ..models import WebhookEvent

logger = logging.getLogger(__name__)


class InstagramHandler(BaseHandler):
    """
    Handler para webhooks do Instagram via Meta Graph API.
    Delega o processamento ao InstagramWebhookService.
    """

    def handle(self, event: WebhookEvent, payload: dict, headers: dict) -> Dict[str, Any]:
        from apps.instagram.services.instagram_webhook_service import InstagramWebhookService

        service = InstagramWebhookService()
        result = service.process_webhook(payload)

        logger.info(
            f"Instagram webhook processed: {result.get('processed', 0)} events"
        )
        return result

    def handle_verification(self, request) -> HttpResponse:
        """Responde ao desafio hub.challenge do Meta."""
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        verify_token = getattr(settings, 'INSTAGRAM_WEBHOOK_VERIFY_TOKEN', '')

        if not verify_token:
            logger.warning("INSTAGRAM_WEBHOOK_VERIFY_TOKEN not configured")
            return HttpResponse("Verification token not configured", status=500)

        tokens_match = bool(verify_token) and hmac.compare_digest(
            token.encode() if token else b'',
            verify_token.encode()
        )

        if mode == 'subscribe' and tokens_match:
            logger.info("Instagram webhook verified successfully")
            return HttpResponse(challenge, status=200)

        logger.warning(f"Instagram webhook verification failed: mode={mode}, token_match={tokens_match}")
        return HttpResponse("Verification failed", status=403)
