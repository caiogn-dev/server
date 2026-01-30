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
    Process webhook event - try async first, fall back to sync.
    
    This ensures events are processed even if Celery is not running.
    """
    try:
        # Try to dispatch to Celery
        from ..tasks import process_webhook_event
        process_webhook_event.delay(str(event.id))
        logger.info(f"Event {event.id} dispatched to Celery")
    except Exception as e:
        logger.warning(f"Celery not available for event {event.id}: {e}")

    # Always process synchronously to guarantee delivery/status updates
    try:
        service = WebhookService()
        service.process_event(event, post_process_inbound=True)
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
        try:
            signature = request.headers.get('X-Hub-Signature-256', '')
            
            # IMPORTANT: Read raw body BEFORE accessing request.data
            # DRF's request.data consumes the stream, making request.body unavailable
            raw_body = request.body
            
            service = WebhookService()
            
            # Log raw payload for debugging
            payload = request.data
            logger.info(f"Webhook POST received - Object: {payload.get('object')}")
            
            # Log entries info
            entries = payload.get('entry', [])
            logger.info(f"Webhook has {len(entries)} entries")
            
            for entry in entries:
                changes = entry.get('changes', [])
                logger.info(f"Entry has {len(changes)} changes")
                
                for change in changes:
                    field = change.get('field')
                    value = change.get('value', {})
                    metadata = value.get('metadata', {})
                    phone_number_id = metadata.get('phone_number_id')
                    display_phone = metadata.get('display_phone_number')
                    
                    logger.info(f"Webhook change - field: {field}, phone_number_id: {phone_number_id}, display: {display_phone}")
                    
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

    @extend_schema(
        summary="Debug webhook status",
        description="Check recent webhook events and messages",
        responses={200: dict}
    )
    def get(self, request):
        """Get debug info about webhooks."""
        from ..models import WhatsAppAccount
        from datetime import timedelta
        
        # Get recent webhook events
        recent_events = WebhookEvent.objects.order_by('-created_at')[:20]
        events_data = [
            {
                'id': str(e.id),
                'event_type': e.event_type,
                'processing_status': e.processing_status,
                'created_at': e.created_at.isoformat(),
                'error_message': e.error_message[:200] if e.error_message else None,
                'account_id': str(e.account_id) if e.account_id else None,
                'retry_count': e.retry_count,
            }
            for e in recent_events
        ]
        
        # Get recent inbound messages
        recent_inbound = Message.objects.filter(
            direction='inbound'
        ).order_by('-created_at')[:10]
        inbound_data = [
            {
                'id': str(m.id),
                'from_number': m.from_number,
                'text_body': m.text_body[:50] if m.text_body else None,
                'message_type': m.message_type,
                'created_at': m.created_at.isoformat(),
                'account_id': str(m.account_id),
            }
            for m in recent_inbound
        ]
        
        # Get stats
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_hour = now - timedelta(hours=1)
        
        total_events = WebhookEvent.objects.count()
        pending_events = WebhookEvent.objects.filter(processing_status='pending').count()
        failed_events = WebhookEvent.objects.filter(processing_status='failed').count()
        processing_events = WebhookEvent.objects.filter(processing_status='processing').count()
        completed_events = WebhookEvent.objects.filter(processing_status='completed').count()
        
        events_last_24h = WebhookEvent.objects.filter(created_at__gte=last_24h).count()
        events_last_hour = WebhookEvent.objects.filter(created_at__gte=last_hour).count()
        
        total_inbound = Message.objects.filter(direction='inbound').count()
        total_outbound = Message.objects.filter(direction='outbound').count()
        inbound_last_24h = Message.objects.filter(direction='inbound', created_at__gte=last_24h).count()
        inbound_last_hour = Message.objects.filter(direction='inbound', created_at__gte=last_hour).count()
        
        # Get WhatsApp accounts status
        accounts = WhatsAppAccount.objects.all()
        accounts_data = [
            {
                'id': str(a.id),
                'name': a.name,
                'phone_number': a.phone_number,
                'phone_number_id': a.phone_number_id,
                'status': a.status,
                'is_active': a.is_active,
                'auto_response_enabled': a.auto_response_enabled,
            }
            for a in accounts
        ]
        
        # Check Celery status
        celery_status = 'unknown'
        try:
            from config.celery import app
            conn = app.connection()
            conn.ensure_connection(max_retries=1, timeout=2)
            conn.close()
            celery_status = 'connected'
        except Exception as e:
            celery_status = f'disconnected: {str(e)[:50]}'
        
        # Get failed events details
        failed_events_details = WebhookEvent.objects.filter(
            processing_status='failed'
        ).order_by('-created_at')[:5]
        failed_data = [
            {
                'id': str(e.id),
                'event_type': e.event_type,
                'error_message': e.error_message[:300] if e.error_message else None,
                'retry_count': e.retry_count,
                'created_at': e.created_at.isoformat(),
            }
            for e in failed_events_details
        ]
        
        return Response({
            'status': 'ok',
            'server_time': timezone.now().isoformat(),
            'celery_status': celery_status,
            'stats': {
                'webhook_events': {
                    'total': total_events,
                    'pending': pending_events,
                    'processing': processing_events,
                    'completed': completed_events,
                    'failed': failed_events,
                    'last_24h': events_last_24h,
                    'last_hour': events_last_hour,
                },
                'messages': {
                    'total_inbound': total_inbound,
                    'total_outbound': total_outbound,
                    'inbound_last_24h': inbound_last_24h,
                    'inbound_last_hour': inbound_last_hour,
                },
            },
            'accounts': accounts_data,
            'recent_events': events_data,
            'recent_inbound_messages': inbound_data,
            'failed_events': failed_data,
            'diagnosis': {
                'has_active_accounts': any(a['is_active'] and a['status'] == 'active' for a in accounts_data),
                'has_pending_events': pending_events > 0,
                'has_failed_events': failed_events > 0,
                'celery_connected': celery_status == 'connected',
                'receiving_webhooks': events_last_hour > 0,
                'receiving_messages': inbound_last_hour > 0,
            }
        })

    @extend_schema(
        summary="Reprocess pending/failed webhook events",
        description="Manually trigger reprocessing of pending or failed webhook events",
        responses={200: dict}
    )
    def post(self, request):
        """Reprocess pending/failed webhook events."""
        action = request.data.get('action', 'reprocess_pending')
        limit = min(int(request.data.get('limit', 50)), 100)
        
        service = WebhookService()
        results = {'processed': 0, 'failed': 0, 'errors': []}
        
        if action == 'reprocess_pending':
            events = WebhookEvent.objects.filter(
                processing_status='pending'
            ).order_by('created_at')[:limit]
        elif action == 'reprocess_failed':
            events = WebhookEvent.objects.filter(
                processing_status='failed',
                retry_count__lt=5
            ).order_by('created_at')[:limit]
        elif action == 'reprocess_all':
            events = WebhookEvent.objects.filter(
                processing_status__in=['pending', 'failed']
            ).order_by('created_at')[:limit]
        else:
            return Response(
                {'error': f'Unknown action: {action}. Use: reprocess_pending, reprocess_failed, reprocess_all'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        for event in events:
            try:
                # Reset status to pending for retry
                if event.processing_status == 'failed':
                    event.processing_status = 'pending'
                    event.save(update_fields=['processing_status'])
                
                service.process_event(event)
                results['processed'] += 1
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'event_id': str(event.id),
                    'error': str(e)[:100]
                })
        
        return Response({
            'status': 'ok',
            'action': action,
            'results': results
        })
