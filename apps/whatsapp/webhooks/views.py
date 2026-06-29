"""\nWhatsApp Webhook views.\n"""
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
                if settings.DEBUG:
                    logger.warning("Invalid webhook signature — continuing in DEBUG mode only")
                else:
                    logger.error("Invalid webhook signature — rejecting request")
                    return Response({'status': 'error', 'message': 'Invalid signature'}, status=403)
            
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
            # Return 200 to avoid Meta retrying indefinitely — details logged above
            return Response({'status': 'error'})


class WebhookDebugView(APIView):
    """Diagnóstico de webhooks WhatsApp consumido pela WebhookDiagnosticsPage.

    Antes retornava só celery_status/verify_token e 404 fora de DEBUG — a página,
    que espera contas, eventos recentes/falhos, mensagens inbound e contadores,
    nunca funcionava. Aqui montamos o payload completo (escopado às contas do
    usuário p/ não vazar dados de outros tenants) + ações de reprocesso.
    """
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _celery_status():
        try:
            from celery import current_app
            stats = current_app.control.inspect().stats()
            return 'running' if stats else 'not running'
        except Exception as e:
            return f'error: {str(e)}'

    def get(self, request):
        from datetime import timedelta
        from django.db.models import Count, Q
        from apps.core.dashboard_views import _accessible_accounts

        accounts_qs = _accessible_accounts(request.user)
        account_ids = list(accounts_qs.values_list('id', flat=True))
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_hour = now - timedelta(hours=1)

        events = WebhookEvent.objects.filter(account_id__in=account_ids)
        ev = events.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(processing_status='pending')),
            processing=Count('id', filter=Q(processing_status='processing')),
            completed=Count('id', filter=Q(processing_status='completed')),
            failed=Count('id', filter=Q(processing_status='failed')),
            last_24h=Count('id', filter=Q(created_at__gte=last_24h)),
            last_hour=Count('id', filter=Q(created_at__gte=last_hour)),
        )
        msgs = Message.objects.filter(account_id__in=account_ids)
        mg = msgs.aggregate(
            total_inbound=Count('id', filter=Q(direction='inbound')),
            total_outbound=Count('id', filter=Q(direction='outbound')),
            inbound_last_24h=Count('id', filter=Q(direction='inbound', created_at__gte=last_24h)),
            inbound_last_hour=Count('id', filter=Q(direction='inbound', created_at__gte=last_hour)),
        )
        celery_status = self._celery_status()

        accounts = [{
            'id': str(a.id), 'name': a.name, 'phone_number': a.phone_number,
            'phone_number_id': a.phone_number_id, 'status': a.status,
            'is_active': a.is_active, 'auto_response_enabled': a.auto_response_enabled,
        } for a in accounts_qs]
        recent_events = [{
            'id': str(e.id), 'event_type': e.event_type, 'processing_status': e.processing_status,
            'created_at': e.created_at.isoformat(), 'error_message': e.error_message or None,
            'account_id': str(e.account_id) if e.account_id else None, 'retry_count': e.retry_count,
        } for e in events.order_by('-created_at')[:20]]
        recent_inbound = [{
            'id': str(m.id), 'from_number': m.from_number, 'text_body': m.text_body or None,
            'message_type': m.message_type, 'created_at': m.created_at.isoformat(),
            'account_id': str(m.account_id),
        } for m in msgs.filter(direction='inbound').order_by('-created_at')[:20]]
        failed_events = [{
            'id': str(e.id), 'event_type': e.event_type, 'error_message': e.error_message or None,
            'retry_count': e.retry_count, 'created_at': e.created_at.isoformat(),
        } for e in events.filter(processing_status='failed').order_by('-created_at')[:20]]

        diagnosis = {
            'has_active_accounts': accounts_qs.filter(is_active=True).exists(),
            'has_pending_events': ev['pending'] > 0,
            'has_failed_events': ev['failed'] > 0,
            'celery_connected': celery_status == 'running',
            'receiving_webhooks': ev['last_24h'] > 0,
            'receiving_messages': mg['inbound_last_24h'] > 0,
        }

        return Response({
            'status': 'ok',
            'server_time': now.isoformat(),
            'celery_status': celery_status,
            'stats': {'webhook_events': ev, 'messages': mg},
            'accounts': accounts,
            'recent_events': recent_events,
            'recent_inbound_messages': recent_inbound,
            'failed_events': failed_events,
            'diagnosis': diagnosis,
        })

    def post(self, request):
        from apps.core.dashboard_views import _accessible_accounts

        action = request.data.get('action')
        try:
            limit = max(1, min(int(request.data.get('limit', 50)), 200))
        except (TypeError, ValueError):
            limit = 50

        account_ids = list(_accessible_accounts(request.user).values_list('id', flat=True))
        status_map = {'reprocess_pending': 'pending', 'reprocess_failed': 'failed'}
        target_status = status_map.get(action)
        if not target_status:
            return Response(
                {'detail': 'Ação inválida. Use reprocess_pending ou reprocess_failed.'},
                status=400,
            )

        target = WebhookEvent.objects.filter(
            account_id__in=account_ids, processing_status=target_status,
        ).order_by('-created_at')[:limit]
        results = {'async': 0, 'sync': 0, 'error': 0}
        for event in target:
            r = process_event_sync_or_async(event)
            results[r] = results.get(r, 0) + 1
        return Response({'action': action, 'processed': sum(results.values()), 'results': results})
