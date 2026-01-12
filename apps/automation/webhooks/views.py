"""
Webhook views for external site integrations.
These endpoints receive events from e-commerce sites, delivery systems, etc.
"""
import logging
import hmac
import hashlib
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from ..models import CompanyProfile
from ..services import AutomationService
from ..api.serializers import (
    CartEventSerializer,
    PaymentEventSerializer,
    OrderEventSerializer,
)

logger = logging.getLogger(__name__)


class WebhookAuthMixin:
    """Mixin for webhook authentication."""
    
    def get_api_key(self, request):
        """Extract API key from request headers."""
        return request.headers.get('X-API-Key', '')
    
    def get_webhook_signature(self, request):
        """Extract webhook signature from request headers."""
        return request.headers.get('X-Webhook-Signature', '')
    
    def validate_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        """Validate webhook signature."""
        if not signature or not secret:
            return True  # Skip validation if no signature provided
        
        # Remove 'sha256=' prefix if present
        if signature.startswith('sha256='):
            signature = signature[7:]
        
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected, signature)
    
    def authenticate_webhook(self, request):
        """Authenticate webhook request."""
        api_key = self.get_api_key(request)
        
        if not api_key:
            return None, Response(
                {'success': False, 'error': 'API key required', 'code': 'MISSING_API_KEY'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        try:
            profile = CompanyProfile.objects.get(
                external_api_key=api_key,
                is_active=True
            )
        except CompanyProfile.DoesNotExist:
            return None, Response(
                {'success': False, 'error': 'Invalid API key', 'code': 'INVALID_API_KEY'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Validate signature if webhook secret is set
        if profile.webhook_secret:
            signature = self.get_webhook_signature(request)
            if not self.validate_signature(request.body, signature, profile.webhook_secret):
                return None, Response(
                    {'success': False, 'error': 'Invalid signature', 'code': 'INVALID_SIGNATURE'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
        
        return profile, None


class CartWebhookView(WebhookAuthMixin, APIView):
    """
    Webhook endpoint for cart events from external sites.
    
    POST /webhooks/automation/cart/
    
    Headers:
        X-API-Key: {api_key}
        X-Webhook-Signature: sha256={signature} (optional)
    
    Events:
        - cart_created: When a cart is created
        - cart_updated: When cart items change
        - cart_abandoned: When cart is abandoned (optional, system can detect)
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        # Authenticate
        profile, error_response = self.authenticate_webhook(request)
        if error_response:
            return error_response
        
        # Validate payload
        serializer = CartEventSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'error': 'Invalid payload', 'details': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        data = serializer.validated_data
        
        # Process event
        service = AutomationService()
        success = service.handle_cart_event(
            api_key=profile.external_api_key,
            session_id=data['session_id'],
            event_type=data['event_type'],
            cart_data={
                'phone_number': data.get('phone_number', ''),
                'customer_name': data.get('customer_name', ''),
                'customer_email': data.get('customer_email', ''),
                'customer_id': data.get('customer_id', ''),
                'items': data.get('items', []),
                'items_count': data.get('items_count', 0),
                'total': float(data.get('total', 0)),
            }
        )
        
        if success:
            return Response({
                'success': True,
                'message': 'Cart event processed',
                'event_type': data['event_type'],
                'session_id': data['session_id'],
            })
        else:
            return Response(
                {'success': False, 'error': 'Failed to process cart event'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PaymentWebhookView(WebhookAuthMixin, APIView):
    """
    Webhook endpoint for payment events from external sites.
    
    POST /webhooks/automation/payment/
    
    Headers:
        X-API-Key: {api_key}
        X-Webhook-Signature: sha256={signature} (optional)
    
    Events:
        - pix_generated: When a PIX payment is generated
        - payment_confirmed: When payment is confirmed
        - payment_failed: When payment fails
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        # Authenticate
        profile, error_response = self.authenticate_webhook(request)
        if error_response:
            return error_response
        
        # Validate payload
        serializer = PaymentEventSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'error': 'Invalid payload', 'details': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        data = serializer.validated_data
        
        # Process event
        service = AutomationService()
        success = service.handle_payment_event(
            api_key=profile.external_api_key,
            session_id=data['session_id'],
            event_type=data['event_type'],
            payment_data={
                'payment_id': data.get('payment_id', ''),
                'order_number': data.get('order_number', ''),
                'amount': float(data.get('amount', 0)),
                'pix_code': data.get('pix_code', ''),
                'qr_code': data.get('qr_code', ''),
                'expires_at': data.get('expires_at'),
            }
        )
        
        if success:
            return Response({
                'success': True,
                'message': 'Payment event processed',
                'event_type': data['event_type'],
                'session_id': data['session_id'],
                'notification_sent': True,
            })
        else:
            return Response(
                {'success': False, 'error': 'Failed to process payment event'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class OrderWebhookView(WebhookAuthMixin, APIView):
    """
    Webhook endpoint for order events from external sites.
    
    POST /webhooks/automation/order/
    
    Headers:
        X-API-Key: {api_key}
        X-Webhook-Signature: sha256={signature} (optional)
    
    Events:
        - order_placed: When order is placed
        - order_confirmed: When order is confirmed
        - order_preparing: When order is being prepared
        - order_ready: When order is ready
        - order_shipped: When order is shipped
        - order_out_for_delivery: When order is out for delivery
        - order_delivered: When order is delivered
        - order_cancelled: When order is cancelled
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        # Authenticate
        profile, error_response = self.authenticate_webhook(request)
        if error_response:
            return error_response
        
        # Validate payload
        serializer = OrderEventSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'error': 'Invalid payload', 'details': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        data = serializer.validated_data
        
        # Process event
        service = AutomationService()
        success = service.handle_order_event(
            api_key=profile.external_api_key,
            session_id=data['session_id'],
            event_type=data['event_type'],
            order_data={
                'order_id': data.get('order_id', ''),
                'order_number': data.get('order_number', ''),
                'tracking_code': data.get('tracking_code', ''),
                'carrier': data.get('carrier', ''),
                'delivery_estimate': data.get('delivery_estimate', ''),
            }
        )
        
        if success:
            return Response({
                'success': True,
                'message': 'Order event processed',
                'event_type': data['event_type'],
                'session_id': data['session_id'],
                'notification_sent': True,
            })
        else:
            return Response(
                {'success': False, 'error': 'Failed to process order event'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class WebhookStatusView(WebhookAuthMixin, APIView):
    """
    Check webhook status and configuration.
    
    GET /webhooks/automation/status/
    
    Headers:
        X-API-Key: {api_key}
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        # Authenticate
        profile, error_response = self.authenticate_webhook(request)
        if error_response:
            return error_response
        
        return Response({
            'success': True,
            'company': profile.company_name,
            'account_phone': profile.account.phone_number,
            'settings': {
                'auto_reply_enabled': profile.auto_reply_enabled,
                'abandoned_cart_notification': profile.abandoned_cart_notification,
                'abandoned_cart_delay_minutes': profile.abandoned_cart_delay_minutes,
                'pix_notification_enabled': profile.pix_notification_enabled,
                'payment_confirmation_enabled': profile.payment_confirmation_enabled,
                'order_status_notification_enabled': profile.order_status_notification_enabled,
                'delivery_notification_enabled': profile.delivery_notification_enabled,
            },
            'webhook_secret_configured': bool(profile.webhook_secret),
        })
