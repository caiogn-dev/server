"""
Payment Webhook views.
"""
import logging
import hmac
import hashlib
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from drf_spectacular.utils import extend_schema
from ..models import PaymentGateway
from ..services import PaymentService
from ..tasks import process_payment_webhook

logger = logging.getLogger(__name__)


class PaymentWebhookView(APIView):
    """Webhook endpoint for payment gateways."""
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Receive payment webhook",
        description="Endpoint for receiving webhook events from payment gateways",
        responses={200: dict}
    )
    def post(self, request, gateway_id=None):
        """Handle incoming payment webhook."""
        if not gateway_id:
            return Response(
                {'error': 'Gateway ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = PaymentService()
        
        try:
            gateway = service.get_gateway(gateway_id)
        except PaymentGateway.DoesNotExist:
            logger.warning(f"Gateway not found: {gateway_id}")
            return Response(
                {'error': 'Gateway not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if not self._validate_signature(request, gateway):
            logger.warning(f"Invalid webhook signature for gateway: {gateway_id}")
            return Response(
                {'error': 'Invalid signature'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        payload = request.data
        headers = dict(request.headers)
        
        event_type = self._extract_event_type(gateway, payload, headers)
        event_id = self._extract_event_id(gateway, payload, headers)
        
        logger.info(f"Payment webhook received: {gateway.name} - {event_type}")
        
        try:
            event = service.process_webhook(
                gateway_id=str(gateway.id),
                event_type=event_type,
                event_id=event_id,
                payload=payload,
                headers=headers
            )
            
            process_payment_webhook.delay(str(event.id))
            
        except Exception as e:
            logger.error(f"Error processing payment webhook: {str(e)}")
        
        return Response({'status': 'ok'})

    def _validate_signature(self, request, gateway: PaymentGateway) -> bool:
        """Validate webhook signature."""
        from apps.core.utils import token_encryption
        
        if not gateway.webhook_secret_encrypted:
            return True
        
        try:
            webhook_secret = token_encryption.decrypt(gateway.webhook_secret_encrypted)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to decrypt webhook secret for gateway {gateway.id}: {e}")
            return True
        
        if gateway.gateway_type == PaymentGateway.GatewayType.STRIPE:
            signature = request.headers.get('Stripe-Signature', '')
            return self._validate_stripe_signature(request.body, signature, webhook_secret)
        elif gateway.gateway_type == PaymentGateway.GatewayType.MERCADOPAGO:
            signature = request.headers.get('X-Signature', '')
            return self._validate_mercadopago_signature(request.body, signature, webhook_secret)
        
        return True

    def _validate_stripe_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str
    ) -> bool:
        """Validate Stripe webhook signature."""
        try:
            parts = dict(item.split('=') for item in signature.split(','))
            timestamp = parts.get('t', '')
            v1_signature = parts.get('v1', '')
            
            signed_payload = f"{timestamp}.{payload.decode()}"
            expected_signature = hmac.new(
                secret.encode(),
                signed_payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(expected_signature, v1_signature)
        except (ValueError, KeyError, UnicodeDecodeError) as e:
            logger.warning(f"Stripe signature validation failed: {e}")
            return False

    def _validate_mercadopago_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str
    ) -> bool:
        """Validate Mercado Pago webhook signature."""
        try:
            expected_signature = hmac.new(
                secret.encode(),
                payload,
                hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(expected_signature, signature)
        except (ValueError, TypeError) as e:
            logger.warning(f"Mercado Pago signature validation failed: {e}")
            return False

    def _extract_event_type(
        self,
        gateway: PaymentGateway,
        payload: dict,
        headers: dict
    ) -> str:
        """Extract event type from webhook payload."""
        if gateway.gateway_type == PaymentGateway.GatewayType.STRIPE:
            return payload.get('type', 'unknown')
        elif gateway.gateway_type == PaymentGateway.GatewayType.MERCADOPAGO:
            return payload.get('action', payload.get('type', 'unknown'))
        elif gateway.gateway_type == PaymentGateway.GatewayType.PIX:
            return payload.get('tipo', 'pix.received')
        
        return payload.get('event_type', payload.get('type', 'unknown'))

    def _extract_event_id(
        self,
        gateway: PaymentGateway,
        payload: dict,
        headers: dict
    ) -> str:
        """Extract event ID from webhook payload."""
        if gateway.gateway_type == PaymentGateway.GatewayType.STRIPE:
            return payload.get('id', '')
        elif gateway.gateway_type == PaymentGateway.GatewayType.MERCADOPAGO:
            return str(payload.get('id', payload.get('data', {}).get('id', '')))
        elif gateway.gateway_type == PaymentGateway.GatewayType.PIX:
            return payload.get('txid', payload.get('e2eid', ''))
        
        return payload.get('event_id', payload.get('id', ''))
