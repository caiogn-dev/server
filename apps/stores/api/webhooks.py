"""
Unified Payment Webhooks for all stores.
Handles Mercado Pago webhooks and routes to correct store.
"""
import logging
import json
from decimal import Decimal
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.stores.models import Store, StoreOrder, StoreIntegration
from apps.stores.services import checkout_service

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class MercadoPagoWebhookView(APIView):
    """
    Unified Mercado Pago webhook handler.
    Routes payment notifications to the correct store.
    """
    
    authentication_classes = []
    permission_classes = []
    
    def post(self, request, store_slug=None):
        """Handle Mercado Pago webhook notification."""
        try:
            # Log incoming webhook
            logger.info(f"MP Webhook received for store: {store_slug}")
            logger.debug(f"Webhook data: {request.data}")
            
            # Get notification type
            topic = request.data.get('type') or request.query_params.get('topic')
            
            if topic == 'payment':
                return self._handle_payment(request, store_slug)
            elif topic == 'merchant_order':
                return self._handle_merchant_order(request, store_slug)
            else:
                logger.info(f"Ignoring webhook topic: {topic}")
                return Response({'status': 'ignored'}, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Webhook error: {e}", exc_info=True)
            # Always return 200 to prevent retries
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_200_OK)
    
    def _handle_payment(self, request, store_slug):
        """Handle payment notification."""
        import mercadopago
        
        # Get payment ID
        payment_id = request.data.get('data', {}).get('id')
        if not payment_id:
            payment_id = request.query_params.get('data.id')
        
        if not payment_id:
            logger.warning("No payment ID in webhook")
            return Response({'status': 'no_payment_id'}, status=status.HTTP_200_OK)
        
        # Find order by payment_id
        order = StoreOrder.objects.filter(payment_id=str(payment_id)).first()
        
        if not order:
            # Try to find by external_reference (order ID)
            external_ref = request.data.get('data', {}).get('external_reference')
            if external_ref:
                order = StoreOrder.objects.filter(id=external_ref).first()
        
        if not order:
            logger.warning(f"Order not found for payment {payment_id}")
            return Response({'status': 'order_not_found'}, status=status.HTTP_200_OK)
        
        # Get store credentials
        credentials = checkout_service.get_payment_credentials(order.store)
        if not credentials:
            logger.error(f"No payment credentials for store {order.store.slug}")
            return Response({'status': 'no_credentials'}, status=status.HTTP_200_OK)
        
        # Fetch payment details from Mercado Pago
        sdk = mercadopago.SDK(credentials['access_token'])
        payment_response = sdk.payment().get(payment_id)
        
        if payment_response['status'] != 200:
            logger.error(f"Failed to fetch payment {payment_id}: {payment_response}")
            return Response({'status': 'fetch_failed'}, status=status.HTTP_200_OK)
        
        payment = payment_response['response']
        payment_status = payment.get('status')
        
        # Process payment status
        order = checkout_service.process_payment_webhook(str(payment_id), payment_status)
        
        if order:
            logger.info(f"Order {order.order_number} updated to status: {order.status}")
            
            # Send real-time notification via WebSocket
            self._notify_order_update(order)
        
        return Response({'status': 'processed'}, status=status.HTTP_200_OK)
    
    def _handle_merchant_order(self, request, store_slug):
        """Handle merchant order notification."""
        # Merchant orders are typically used for marketplace scenarios
        # For now, we just acknowledge them
        logger.info(f"Merchant order webhook received for {store_slug}")
        return Response({'status': 'acknowledged'}, status=status.HTTP_200_OK)
    
    def _notify_order_update(self, order):
        """Send WebSocket notification for order update."""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"store_{order.store.slug}_orders",
                    {
                        'type': 'order_update',
                        'order_id': str(order.id),
                        'order_number': order.order_number,
                        'status': order.status,
                        'payment_status': order.payment_status,
                        'updated_at': order.updated_at.isoformat(),
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to send WebSocket notification: {e}")


@method_decorator(csrf_exempt, name='dispatch')
class PaymentStatusView(APIView):
    """
    Check payment status for an order.
    Used by frontend to poll payment status.
    Accepts either order UUID or order_number.
    """
    
    authentication_classes = []
    permission_classes = []
    
    def get(self, request, order_id):
        """Get payment status for an order."""
        try:
            # Try to find by UUID first
            try:
                from uuid import UUID
                UUID(str(order_id))
                order = StoreOrder.objects.get(id=order_id)
            except (ValueError, StoreOrder.DoesNotExist):
                # Try by order_number
                order = StoreOrder.objects.get(order_number=str(order_id))
            
            return Response({
                'order_id': str(order.id),
                'order_number': order.order_number,
                'status': order.status,
                'payment_status': order.payment_status,
                'payment_id': order.payment_id,
                'total': float(order.total),
                'paid_at': order.paid_at.isoformat() if order.paid_at else None,
            })
        
        except StoreOrder.DoesNotExist:
            return Response(
                {'error': 'Pedido não encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )


class CustomerOrdersView(APIView):
    """
    Get orders for authenticated customer.
    Used by frontend to show order history.
    """
    
    def get(self, request):
        """Get orders for the authenticated user."""
        user = request.user
        
        if not user.is_authenticated:
            return Response(
                {'error': 'Autenticação necessária'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Get store filter
        store_slug = request.query_params.get('store')
        
        # Get orders where customer email or phone matches user
        orders = StoreOrder.objects.filter(
            customer=user
        ).select_related('store').prefetch_related('items')
        
        if store_slug:
            orders = orders.filter(store__slug=store_slug)
        
        orders = orders.order_by('-created_at')[:50]
        
        results = []
        for order in orders:
            results.append({
                'id': str(order.id),
                'order_number': order.order_number,
                'store_name': order.store.name,
                'store_slug': order.store.slug,
                'status': order.status,
                'payment_status': order.payment_status,
                'total': float(order.total),
                'delivery_method': order.delivery_method,
                'items_count': order.items.count(),
                'created_at': order.created_at.isoformat(),
            })
        
        return Response({'results': results})


class CustomerOrderDetailView(APIView):
    """
    Get single order details for customer.
    """
    
    authentication_classes = []
    permission_classes = []
    
    def get(self, request, order_id):
        """Get order details."""
        try:
            order = StoreOrder.objects.select_related('store').prefetch_related('items').get(id=order_id)
            
            items = []
            for item in order.items.all():
                items.append({
                    'id': str(item.id),
                    'product_name': item.product_name,
                    'variant_name': item.variant_name,
                    'quantity': item.quantity,
                    'unit_price': float(item.unit_price),
                    'subtotal': float(item.subtotal),
                    'notes': item.notes,
                })
            
            return Response({
                'id': str(order.id),
                'order_number': order.order_number,
                'store': {
                    'name': order.store.name,
                    'slug': order.store.slug,
                    'phone': order.store.phone,
                    'whatsapp_number': order.store.whatsapp_number,
                },
                'customer_name': order.customer_name,
                'customer_email': order.customer_email,
                'customer_phone': order.customer_phone,
                'status': order.status,
                'payment_status': order.payment_status,
                'payment_method': order.payment_method,
                'subtotal': float(order.subtotal),
                'discount': float(order.discount),
                'delivery_fee': float(order.delivery_fee),
                'total': float(order.total),
                'delivery_method': order.delivery_method,
                'delivery_address': order.delivery_address,
                'delivery_notes': order.delivery_notes,
                'customer_notes': order.customer_notes,
                'tracking_code': order.tracking_code,
                'tracking_url': order.tracking_url,
                'items': items,
                'created_at': order.created_at.isoformat(),
                'updated_at': order.updated_at.isoformat(),
                'paid_at': order.paid_at.isoformat() if order.paid_at else None,
                'shipped_at': order.shipped_at.isoformat() if order.shipped_at else None,
                'delivered_at': order.delivered_at.isoformat() if order.delivered_at else None,
            })
        
        except StoreOrder.DoesNotExist:
            return Response(
                {'error': 'Pedido não encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )


class OrderWhatsAppView(APIView):
    """
    Generate WhatsApp confirmation link for an order.
    """
    
    authentication_classes = []
    permission_classes = []
    
    def get(self, request, order_id):
        """Get WhatsApp link for order confirmation."""
        try:
            order = StoreOrder.objects.select_related('store').get(id=order_id)
            
            # Get store WhatsApp number
            whatsapp_number = order.store.whatsapp_number or order.store.phone
            if not whatsapp_number:
                return Response(
                    {'error': 'Loja não possui WhatsApp configurado'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Clean phone number
            clean_number = ''.join(filter(str.isdigit, whatsapp_number))
            if not clean_number.startswith('55'):
                clean_number = '55' + clean_number
            
            # Build message
            items_text = []
            for item in order.items.all():
                items_text.append(f"• {item.quantity}x {item.product_name}")
            
            message = f"""🛒 *Pedido #{order.order_number}*

{chr(10).join(items_text)}

💰 *Total:* R$ {order.total:.2f}
📦 *Entrega:* {order.get_delivery_method_display()}

Olá! Gostaria de confirmar meu pedido."""
            
            # URL encode message
            from urllib.parse import quote
            encoded_message = quote(message)
            
            whatsapp_url = f"https://wa.me/{clean_number}?text={encoded_message}"
            
            return Response({
                'whatsapp_url': whatsapp_url,
                'phone_number': clean_number,
                'message': message,
            })
        
        except StoreOrder.DoesNotExist:
            return Response(
                {'error': 'Pedido não encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )
