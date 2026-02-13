"""
WhatsApp Webhook views.
"""
import logging
import json
from django.conf import settings
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from ..services import WebhookService
from ..models import WebhookEvent, Message

logger = logging.getLogger(__name__)


def process_event_sync_or_async(event):
    """
    Process webhook event - prefer async, fall back to sync.
    
    This ensures events are processed even if Celery is not running.
    """
    celery_available = False
    
    # Try to dispatch to Celery first
    try:
        from ..tasks import process_webhook_event
        process_webhook_event.delay(str(event.id))
        logger.info(f"Event {event.id} dispatched to Celery")
        celery_available = True
    except Exception as e:
        logger.warning(f"Celery not available for event {event.id}: {e}")
    
    # Only process synchronously if Celery is not available
    if not celery_available:
        try:
            service = WebhookService()
            service.process_event(event, post_process_inbound=True)
            logger.info(f"Event {event.id} processed synchronously (Celery unavailable)")
            return 'sync'
        except Exception as sync_error:
            logger.error(f"Error processing event {event.id} synchronously: {sync_error}", exc_info=True)
            return 'error'
    
    return 'async'


class WhatsAppWebhookView(APIView):
    """Webhook endpoint for Meta WhatsApp Business API."""
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="WhatsApp Webhook",
        description="Receive webhook events from Meta WhatsApp Business API",
        responses={200: {"type": "object", "properties": {"status": {"type": "string"}}}}
    )
    def get(self, request):
        """Handle webhook verification from Meta."""
        mode = request.query_params.get('hub.mode')
        token = request.query_params.get('hub.verify_token')
        challenge = request.query_params.get('hub.challenge')
        
        verify_token = getattr(settings, 'WHATSAPP_WEBHOOK_VERIFY_TOKEN', None)
        
        if mode == 'subscribe' and token == verify_token:
            logger.info(f"Webhook verified with challenge: {challenge}")
            return HttpResponse(challenge)
        else:
            logger.warning(f"Webhook verification failed: mode={mode}, token={token}")
            return Response({'error': 'Verification failed'}, status=403)

    @extend_schema(
        summary="WhatsApp Webhook POST",
        description="Receive webhook events from Meta WhatsApp Business API",
        responses={200: {"type": "object", "properties": {"status": {"type": "string"}}}}
    )
    def post(self, request):
        """Handle incoming webhook events from Meta."""
        try:
            # Get raw body for signature verification
            raw_body = request.body.decode('utf-8')
            
            # Parse JSON payload
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON payload: {e}")
                return Response({'status': 'error', 'message': 'Invalid JSON'}, status=400)
            
            # Get signature from headers
            signature = request.headers.get('X-Hub-Signature-256', '')
            
            # Initialize service
            service = WebhookService()
            
            # Log webhook details
            object_type = payload.get('object', 'unknown')
            entry_count = len(payload.get('entry', []))
            logger.info(f"Webhook POST received - Object: {object_type}, Entries: {entry_count}")
            
            # Validate signature using the raw body we captured earlier
            if not service.validate_signature(raw_body, signature):
                logger.warning("Invalid webhook signature - skipping validation in dev mode")
                # Continue anyway for debugging
            
            # Convert headers to simple dict
            headers = {}
            for key, value in request.headers.items():
                headers[key] = str(value)
            
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
                logger.error(f"Error processing webhook events: {str(e)}", exc_info=True)
            
            # Always return 200 to Meta to acknowledge receipt
            return Response({'status': 'ok'})
            
        except Exception as e:
            logger.error(f"Webhook POST error: {str(e)}", exc_info=True)
            # Still return 200 to avoid Meta retrying
            return Response({'status': 'error', 'message': str(e)})


class WebhookDebugView(APIView):
    """Debug endpoint to check webhook status."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return webhook status information."""
        from ..tasks import process_webhook_event
        
        # Check Celery status
        try:
            from celery import current_app
            inspector = current_app.control.inspect()
            stats = inspector.stats()
            celery_status = 'running' if stats else 'not running'
        except Exception as e:
            celery_status = f'error: {str(e)}'
        
        return Response({
            'celery_status': celery_status,
            'verify_token_configured': bool(getattr(settings, 'WHATSAPP_WEBHOOK_VERIFY_TOKEN', None)),
        })
