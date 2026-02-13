"""
Webhook service for triggering store webhooks.
"""
import logging
import hashlib
import hmac
import json
import requests
from typing import Dict, Any, List
from django.utils import timezone
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for managing and triggering store webhooks."""
    
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.timeout = 30
    
    def trigger_webhooks(self, store, event: str, payload: Dict[str, Any]):
        """
        Trigger all webhooks for a store that are subscribed to the given event.
        Runs asynchronously to not block the main thread.
        """
        from apps.stores.models import StoreWebhook
        
        webhooks = StoreWebhook.objects.filter(
            store=store,
            is_active=True
        )
        
        for webhook in webhooks:
            if event in webhook.events or '*' in webhook.events:
                self.executor.submit(self._send_webhook, webhook, event, payload)
    
    def _send_webhook(self, webhook, event: str, payload: Dict[str, Any]):
        """Send a single webhook request."""
        from apps.stores.models import StoreWebhook
        
        try:
            # Prepare the request body
            body = {
                'event': event,
                'timestamp': timezone.now().isoformat(),
                'store_id': str(webhook.store.id),
                'store_name': webhook.store.name,
                'data': payload
            }
            
            body_json = json.dumps(body, default=str)
            
            # Prepare headers
            headers = {
                'Content-Type': 'application/json',
                'X-Webhook-Event': event,
                'X-Webhook-Timestamp': body['timestamp'],
                **webhook.headers
            }
            
            # Add signature if secret is configured
            if webhook.secret:
                signature = self._generate_signature(body_json, webhook.secret)
                headers['X-Webhook-Signature'] = signature
            
            # Send the request
            response = requests.post(
                webhook.url,
                data=body_json,
                headers=headers,
                timeout=self.timeout
            )
            
            success = 200 <= response.status_code < 300
            error = '' if success else f"HTTP {response.status_code}: {response.text[:500]}"
            
            webhook.record_call(success=success, error=error)
            
            if success:
                logger.info(f"Webhook sent successfully: {webhook.name} -> {event}")
            else:
                logger.warning(f"Webhook failed: {webhook.name} -> {event}: {error}")
                
                # Retry if configured
                if webhook.max_retries > 0:
                    self._schedule_retry(webhook, event, payload, attempt=1)
        
        except requests.Timeout:
            error = f"Timeout after {self.timeout}s"
            webhook.record_call(success=False, error=error)
            logger.error(f"Webhook timeout: {webhook.name} -> {event}")
        
        except requests.RequestException as e:
            error = str(e)
            webhook.record_call(success=False, error=error)
            logger.error(f"Webhook error: {webhook.name} -> {event}: {error}")
        
        except Exception as e:
            logger.exception(f"Unexpected error sending webhook: {webhook.name}")
    
    def _generate_signature(self, body: str, secret: str) -> str:
        """Generate HMAC-SHA256 signature for webhook payload."""
        return hmac.new(
            secret.encode('utf-8'),
            body.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _schedule_retry(self, webhook, event: str, payload: Dict[str, Any], attempt: int):
        """Schedule a retry for a failed webhook."""
        if attempt >= webhook.max_retries:
            logger.warning(f"Webhook max retries reached: {webhook.name}")
            return
        
        # Use Celery for delayed retry if available
        try:
            from apps.stores.tasks import retry_webhook
            retry_webhook.apply_async(
                args=[str(webhook.id), event, payload, attempt + 1],
                countdown=webhook.retry_delay * attempt
            )
        except ImportError:
            logger.warning("Celery not available for webhook retry")
    
    def verify_signature(self, body: str, signature: str, secret: str) -> bool:
        """Verify incoming webhook signature."""
        expected = self._generate_signature(body, secret)
        return hmac.compare_digest(expected, signature)
    
    def test_webhook(self, webhook) -> Dict[str, Any]:
        """Send a test webhook to verify configuration."""
        test_payload = {
            'test': True,
            'message': 'This is a test webhook from your store',
            'timestamp': timezone.now().isoformat()
        }
        
        try:
            body = json.dumps({
                'event': 'test',
                'store_id': str(webhook.store.id),
                'store_name': webhook.store.name,
                'data': test_payload
            }, default=str)
            
            headers = {
                'Content-Type': 'application/json',
                'X-Webhook-Event': 'test',
                **webhook.headers
            }
            
            if webhook.secret:
                headers['X-Webhook-Signature'] = self._generate_signature(body, webhook.secret)
            
            response = requests.post(
                webhook.url,
                data=body,
                headers=headers,
                timeout=10
            )
            
            return {
                'success': 200 <= response.status_code < 300,
                'status_code': response.status_code,
                'response': response.text[:500]
            }
        
        except requests.Timeout:
            return {'success': False, 'error': 'Request timed out'}
        except requests.RequestException as e:
            return {'success': False, 'error': str(e)}


webhook_service = WebhookService()
