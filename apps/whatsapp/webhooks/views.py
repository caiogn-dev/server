"""
WhatsApp Webhook views.
"""
import logging
import json
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from ..services import WebhookService

logger = logging.getLogger(__name__)


def process_event_sync_or_async(event):
    """
    Process webhook event - try async first, fall back to sync.
    
    This ensures events are processed even if Celery is not running.
    """
    try:
        # Try to dispatch to Celery
        from ..tasks import process_webhook_event
        process_webhook_event.delay(str(event.id))
        logger.info(f"Event {event.id} dispatched to Celery")
        return 'async'
    except Exception as e:
        # Celery not available, process synchronously
        logger.warning(f"Celery not available, processing event {event.id} synchronously: {e}")
        try:
            service = WebhookService()
            service.process_event(event)
            logger.info(f"Event {event.id} processed synchronously")
            return 'sync'
        except Exception as sync_error:
            logger.error(f"Error processing event {event.id} synchronously: {sync_error}", exc_info=True)
            return 'error'


class WhatsAppWebhookView(APIView):
    """Webhook endpoint for Meta WhatsApp Business API."""
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Verify webhook subscription",
        description="Endpoint for Meta to verify webhook subscription",
        responses={200: str}
    )
    def get(self, request):
        """Handle webhook verification from Meta."""
        mode = request.query_params.get('hub.mode')
        token = request.query_params.get('hub.verify_token')
        challenge = request.query_params.get('hub.challenge')
        
        logger.info(f"Webhook verification request: mode={mode}")
        
        service = WebhookService()
        
        try:
            result = service.verify_webhook(mode, token, challenge)
            return HttpResponse(result, content_type='text/plain')
        except Exception as e:
            logger.error(f"Webhook verification failed: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_403_FORBIDDEN
            )

    @extend_schema(
        summary="Receive webhook events",
        description="Endpoint for receiving webhook events from Meta",
        responses={200: dict}
    )
    def post(self, request):
        """Handle incoming webhook events from Meta."""
        signature = request.headers.get('X-Hub-Signature-256', '')
        
        service = WebhookService()
        
        # Log raw payload for debugging
        logger.info(f"Webhook POST received - Object: {request.data.get('object')}")
        
        if not service.validate_signature(request.body, signature):
            logger.warning("Invalid webhook signature")
            return Response(
                {'error': 'Invalid signature'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        payload = request.data
        headers = dict(request.headers)
        
        # Log detailed payload info
        entries = payload.get('entry', [])
        for entry in entries:
            changes = entry.get('changes', [])
            for change in changes:
                field = change.get('field')
                value = change.get('value', {})
                
                # Log messages
                messages = value.get('messages', [])
                if messages:
                    logger.info(f"Webhook: Received {len(messages)} message(s)")
                    for msg in messages:
                        logger.info(f"  - Message ID: {msg.get('id')}, Type: {msg.get('type')}, From: {msg.get('from')}")
                
                # Log statuses
                statuses = value.get('statuses', [])
                if statuses:
                    logger.info(f"Webhook: Received {len(statuses)} status update(s)")
                    for st in statuses:
                        logger.info(f"  - Status: {st.get('status')} for message {st.get('id')}")
        
        processed_results = {'async': 0, 'sync': 0, 'error': 0}
        
        try:
            events = service.process_webhook(payload, headers)
            
            logger.info(f"Created {len(events)} webhook events, processing...")
            
            for event in events:
                result = process_event_sync_or_async(event)
                processed_results[result] += 1
                logger.info(f"  - Event {event.id} (type: {event.event_type}) -> {result}")
            
            logger.info(f"Processing complete: {processed_results}")
            
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        
        # Always return 200 to Meta to acknowledge receipt
        return Response({'status': 'ok'})
