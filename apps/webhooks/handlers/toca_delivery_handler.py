"""
Toca Delivery webhook handler.

Receives status update callbacks when Toca Delivery fires the empresa.webhook_url.
Expected payload (POST JSON):
    {
        "corrida_id": "<uuid>",
        "codigo": "TCA-XXXX",
        "status": "em_rota",           # CorridaStatus value
        "evento": "status_change",
        "timestamp": "2026-04-18T10:00:00Z"
    }

Security: HMAC-SHA256 signature in X-Toca-Signature header (hex digest of body).
"""
import hashlib
import hmac
import logging
from typing import Any, Dict, Optional

from django.conf import settings
from django.utils import timezone

from apps.webhooks.handlers.base import BaseHandler
from apps.webhooks.models import WebhookEvent

logger = logging.getLogger(__name__)


class TocaDeliveryHandler(BaseHandler):
    PROVIDER = 'toca-delivery'

    def handle(self, event: WebhookEvent, payload: dict, headers: dict) -> Dict[str, Any]:
        corrida_id = payload.get('corrida_id') or payload.get('id', '')
        new_status = payload.get('status', '')

        if not corrida_id or not new_status:
            logger.warning('TocaDeliveryHandler: missing corrida_id or status in payload')
            return {'ok': False, 'reason': 'missing_fields'}

        from apps.stores.models import StoreOrder
        from apps.stores.services.delivery_provider.toca_delivery import TocaDeliveryProvider

        provider = TocaDeliveryProvider()
        order_status = provider.map_status_to_order(new_status)

        update_fields: dict = {
            'external_delivery_status': new_status,
        }

        if order_status:
            update_fields['status'] = order_status
            if order_status == 'out_for_delivery':
                update_fields['out_for_delivery_at'] = timezone.now()
            elif order_status == 'delivered':
                update_fields['delivered_at'] = timezone.now()

        updated = StoreOrder.objects.filter(external_delivery_id=corrida_id).update(**update_fields)

        if updated == 0:
            logger.warning('TocaDeliveryHandler: no order found for corrida_id=%s', corrida_id)
            return {'ok': False, 'reason': 'order_not_found'}

        logger.info(
            'TocaDeliveryHandler: corrida=%s status=%s → order_status=%s (%d updated)',
            corrida_id, new_status, order_status, updated,
        )
        return {'ok': True, 'updated': updated, 'new_status': new_status}

    def validate_signature(self, body: bytes, signature_header: str) -> bool:
        """Validate HMAC-SHA256 signature from X-Toca-Signature header."""
        secret = getattr(settings, 'TOCA_DELIVERY_WEBHOOK_SECRET', '')
        if not secret:
            return True  # Not configured — skip validation

        expected = hmac.new(  # noqa: S324
            secret.encode(), body, hashlib.sha256
        ).hexdigest()
        # hmac.new → hmac.HMAC constructor; Python 3.x uses hmac.new as an alias
        return hmac.compare_digest(expected, signature_header or '')


