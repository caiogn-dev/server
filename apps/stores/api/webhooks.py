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
from rest_framework.permissions import IsAuthenticated

from apps.stores.models import Store, StoreOrder, StoreIntegration
from apps.stores.services import checkout_service
from apps.stores.services.realtime_service import broadcast_order_event

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class MercadoPagoWebhookView(APIView):
    """
    Unified Mercado Pago webhook handler.
    Routes payment notifications to the correct store.
    Validates webhook signature for security.
    """
    
    authentication_classes = []
    permission_classes = []
    
    def post(self, request, store_slug=None):
        """Handle Mercado Pago webhook notification."""
        try:
            # Log incoming webhook
            logger.info(f"MP Webhook received for store: {store_slug}")
            logger.debug(f"Webhook data: {request.data}")
            logger.debug(f"Webhook headers: {dict(request.headers)}")
            
            # Validate webhook signature if secret is configured
            sig_result = self._validate_signature(request, store_slug)
            if sig_result is False:
                # Secret IS configured but signature didn't match — reject
                logger.warning("Webhook signature validation failed for store: %s", store_slug)
                return Response({'status': 'invalid_signature'}, status=status.HTTP_401_UNAUTHORIZED)
            
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
    
    def _validate_signature(self, request, store_slug):
        """
        Validate Mercado Pago webhook signature.

        Returns:
            True  — no secret configured (validation skipped, allow)
            True  — secret configured and signature matches
            False — secret configured but signature is missing or wrong
        """
        import hmac as hmac_mod
        import hashlib

        if not store_slug:
            return True

        try:
            integration = StoreIntegration.objects.filter(
                store__slug=store_slug,
                integration_type=StoreIntegration.IntegrationType.MERCADOPAGO,
                status=StoreIntegration.IntegrationStatus.ACTIVE,
            ).only('webhook_secret').first()
        except Exception as e:
            logger.error("Error fetching MP integration for signature check: %s", e)
            return True  # DB error — can't validate; allow and log

        if not integration or not integration.webhook_secret:
            # No secret configured — skip validation (True = allow)
            return True

        # Secret IS configured — enforce validation
        # Mercado Pago sends signature in query string: ?signature=<hex>
        provided_sig = (
            request.query_params.get('signature')
            or request.headers.get('X-Signature')
            or request.headers.get('X-Hub-Signature')
            or ''
        )
        if not provided_sig:
            logger.warning("MP webhook missing signature for store %s", store_slug)
            return False

        # Strip algorithm prefix if present (e.g. "sha256=abc...")
        if '=' in provided_sig and not provided_sig.startswith('0') and len(provided_sig) < 20:
            provided_sig = provided_sig.split('=', 1)[-1]

        try:
            body = request.body.decode('utf-8')
            expected = hmac_mod.new(
                integration.webhook_secret.encode('utf-8'),
                body.encode('utf-8'),
                hashlib.sha256,
            ).hexdigest()
            if hmac_mod.compare_digest(provided_sig, expected):
                return True
            logger.warning("MP webhook signature mismatch for store %s", store_slug)
            return False
        except Exception as e:
            logger.error("MP webhook signature computation error: %s", e)
            return False  # Fail closed when secret is configured
    
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
            
            # Send WhatsApp notification if payment is approved
            if payment_status == 'approved':
                self._send_payment_confirmation_whatsapp(order)
        
        return Response({'status': 'processed'}, status=status.HTTP_200_OK)
    
    def _handle_merchant_order(self, request, store_slug):
        """Handle merchant order notification."""
        # Merchant orders are typically used for marketplace scenarios
        # For now, we just acknowledge them
        logger.info(f"Merchant order webhook received for {store_slug}")
        return Response({'status': 'acknowledged'}, status=status.HTTP_200_OK)
    
    def _notify_order_update(self, order):
        """Send WebSocket notification for order update."""
        broadcast_order_event(order)
    
    def _send_payment_confirmation_whatsapp(self, order):
        """
        Send WhatsApp payment confirmation message.
        Uses template message if available, otherwise sends text.
        """
        try:
            # Check if customer has phone number
            if not order.customer_phone:
                logger.info(f"No phone number for order {order.order_number}, skipping WhatsApp")
                return
            
            # Get WhatsApp integration for the store
            from apps.stores.models import StoreIntegration
            integration = StoreIntegration.objects.filter(
                store=order.store,
                integration_type=StoreIntegration.IntegrationType.WHATSAPP,
                status=StoreIntegration.IntegrationStatus.ACTIVE
            ).first()
            
            if not integration:
                logger.info(f"No WhatsApp integration for store {order.store.slug}")
                return
            
            # Import message service
            from apps.whatsapp.services import MessageService
            service = MessageService()
            
            # Clean phone number
            phone = ''.join(filter(str.isdigit, order.customer_phone))
            if not phone.startswith('55'):
                phone = '55' + phone
            
            # Build message
            items_text = []
            for item in order.items.all():
                items_text.append(f"• {item.quantity}x {item.product_name}")
            
            message = f"""✅ *Pagamento Confirmado!*

🛒 Pedido: #{order.order_number}

{chr(10).join(items_text)}

💰 Total: R$ {float(order.total):.2f}
📦 Entrega: {order.get_delivery_method_display()}

Obrigado pela preferência! 🎉"""
            
            # Send message
            service.send_text_message(
                account_id=str(integration.external_id) if integration.external_id else str(integration.id),
                to=phone,
                text=message
            )
            
            logger.info(f"WhatsApp confirmation sent for order {order.order_number}")
            
        except Exception as e:
            logger.error(f"Failed to send WhatsApp confirmation: {e}", exc_info=True)
            # Don't raise - webhook should not fail if message fails


@method_decorator(csrf_exempt, name='dispatch')
class PaymentStatusView(APIView):
    """
    SECURE payment status endpoint.
    Requires access_token for public access.
    
    Usage:
    - GET /orders/{order_number}/payment-status/?token={access_token}
    - GET /orders/by-token/{access_token}/
    
    The access_token is a secure random string generated when the order is created.
    This prevents unauthorized access to order details.
    """
    
    authentication_classes = []
    permission_classes = []
    
    def get(self, request, order_id):
        """Get payment status for an order (requires token)."""
        try:
            # Get token from query params
            token = request.query_params.get('token', '')
            
            # Try to find order
            order = None
            
            # Try by UUID first
            try:
                from uuid import UUID
                UUID(str(order_id))
                order = StoreOrder.objects.select_related('store').prefetch_related('items').get(id=order_id)
            except (ValueError, StoreOrder.DoesNotExist):
                # Try by order_number
                try:
                    order = StoreOrder.objects.select_related('store').prefetch_related('items').get(order_number=str(order_id))
                except StoreOrder.DoesNotExist:
                    pass
            
            if not order:
                return Response(
                    {'error': 'Pedido não encontrado'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # SECURITY: Validate access token
            # Allow access if:
            # 1. Valid token provided
            # 2. User is authenticated and owns the order
            # 3. Request is from authenticated admin/staff
            user = request.user
            is_authenticated_owner = user.is_authenticated and (
                order.customer == user or 
                user.is_staff or 
                user.is_superuser
            )
            
            has_valid_token = token and order.access_token and token == order.access_token
            
            if not has_valid_token and not is_authenticated_owner:
                logger.warning(f"Unauthorized access attempt to order {order.order_number}")
                return Response(
                    {'error': 'Token de acesso inválido ou expirado'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Build items list
            items = []
            for item in order.items.all():
                items.append({
                    'id': str(item.id),
                    'product_name': item.product_name,
                    'variant_name': item.variant_name,
                    'quantity': item.quantity,
                    'unit_price': float(item.unit_price),
                    'subtotal': float(item.subtotal),
                })
            
            # Build response with all payment info
            response_data = {
                'order_id': str(order.id),
                'order_number': order.order_number,
                'status': order.status,
                'payment_status': order.payment_status,
                'payment_method': order.payment_method,
                'payment_id': order.payment_id,
                'subtotal': float(order.subtotal),
                'delivery_fee': float(order.delivery_fee),
                'discount': float(order.discount),
                'tax': float(order.tax) if order.tax else 0,
                'total': float(order.total),
                'total_amount': float(order.total),
                'delivery_method': order.delivery_method,
                'delivery_address': order.delivery_address,
                'items': items,
                'created_at': order.created_at.isoformat(),
                'paid_at': order.paid_at.isoformat() if order.paid_at else None,
            }
            
            # Include PIX data if available
            if order.payment_method == 'pix':
                response_data['pix_code'] = order.pix_code or ''
                response_data['pix_qr_code'] = order.pix_qr_code or ''
                response_data['payment'] = {
                    'payment_method_id': 'pix',
                    'payment_type_id': 'bank_transfer',
                    'status': order.payment_status,
                    'transaction_amount': float(order.total),
                    'qr_code': order.pix_code or '',
                    'qr_code_base64': order.pix_qr_code or '',
                }
            
            return Response(response_data)
        
        except Exception as e:
            logger.error(f"Error in PaymentStatusView: {e}", exc_info=True)
            return Response(
                {'error': 'Erro ao buscar pedido'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class OrderByTokenView(APIView):
    """
    Get order details by access token.
    This is the SECURE way to access order details publicly.
    
    Usage: GET /orders/by-token/{access_token}/
    """
    
    authentication_classes = []
    permission_classes = []
    
    def get(self, request, access_token):
        """Get order by access token."""
        try:
            order = StoreOrder.objects.select_related('store').prefetch_related('items').get(
                access_token=access_token
            )
            
            # Build items list
            items = []
            for item in order.items.all():
                items.append({
                    'id': str(item.id),
                    'product_name': item.product_name,
                    'variant_name': item.variant_name,
                    'quantity': item.quantity,
                    'unit_price': float(item.unit_price),
                    'subtotal': float(item.subtotal),
                })
            
            # Build response
            response_data = {
                'order_id': str(order.id),
                'order_number': order.order_number,
                'store': {
                    'name': order.store.name,
                    'slug': order.store.slug,
                    'phone': order.store.phone,
                    'whatsapp_number': order.store.whatsapp_number,
                },
                'status': order.status,
                'payment_status': order.payment_status,
                'payment_method': order.payment_method,
                'subtotal': float(order.subtotal),
                'delivery_fee': float(order.delivery_fee),
                'discount': float(order.discount),
                'tax': float(order.tax) if order.tax else 0,
                'total': float(order.total),
                'delivery_method': order.delivery_method,
                'items': items,
                'created_at': order.created_at.isoformat(),
                'paid_at': order.paid_at.isoformat() if order.paid_at else None,
            }
            
            # Include PIX data if available
            if order.payment_method == 'pix':
                response_data['pix_code'] = order.pix_code or ''
                response_data['pix_qr_code'] = order.pix_qr_code or ''
            
            return Response(response_data)
        
        except StoreOrder.DoesNotExist:
            return Response(
                {'error': 'Token inválido ou pedido não encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )


class CustomerOrdersView(APIView):
    """
    Get orders for authenticated customer.
    Used by frontend to show order history.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get orders for the authenticated user."""
        user = request.user
        
        if not user.is_authenticated:
            return Response(
                {'error': 'Autenticação necessária', 'results': []},
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
        
        from django.db.models import Count
        orders = (
            orders
            .annotate(items_count=Count('items'))
            .order_by('-created_at')[:50]
        )

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
                'items_count': order.items_count,
                'created_at': order.created_at.isoformat(),
            })
        
        return Response({'results': results})


class CustomerOrderDetailView(APIView):
    """
    Get single order details for customer.
    Access requires one of:
    - Authenticated user who owns the order, or is staff/superuser
    - Valid ?token=<access_token> query param (customer self-service post-checkout)
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request, order_id):
        """Get order details."""
        try:
            order = StoreOrder.objects.select_related('store').prefetch_related('items').get(id=order_id)

            token = request.query_params.get('token', '')
            user = request.user
            is_owner = (
                user.is_authenticated
                and (order.customer_id == user.id or user.is_staff or user.is_superuser)
            )
            has_valid_token = bool(token and order.access_token and token == order.access_token)

            if not is_owner and not has_valid_token:
                return Response(
                    {'error': 'Acesso negado. Token inválido ou autenticação necessária.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
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


class OrderReceiptView(APIView):
    """
    Generate and return a PDF receipt for an order.

    Access control (any of):
    - Authenticated store owner / staff
    - Valid ?token=<access_token> query param (for customer self-service)

    GET /api/v1/stores/orders/<uuid>/receipt/
    GET /api/v1/stores/orders/<uuid>/receipt/?token=<access_token>
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request, order_id):
        token = request.query_params.get("token")

        try:
            order = (
                StoreOrder.objects
                .select_related("store")
                .prefetch_related("items__product", "combo_items")
                .get(id=order_id)
            )
        except StoreOrder.DoesNotExist:
            return Response({"error": "Pedido não encontrado"}, status=status.HTTP_404_NOT_FOUND)

        # Authorization: token OR authenticated owner/staff
        user = request.user if request.user and request.user.is_authenticated else None
        if token:
            if order.access_token != token:
                return Response({"error": "Token inválido"}, status=status.HTTP_403_FORBIDDEN)
        elif user:
            store = order.store
            is_owner = getattr(store, "owner_id", None) == user.id
            is_staff = user.is_staff or user.is_superuser
            is_store_staff = store.staff.filter(id=user.id).exists() if not is_staff else False
            if not (is_owner or is_staff or is_store_staff):
                return Response({"error": "Sem permissão"}, status=status.HTTP_403_FORBIDDEN)
        else:
            return Response(
                {"error": "Autenticação necessária ou token de pedido obrigatório"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            from apps.stores.services.receipt_service import generate_order_receipt_pdf
            pdf_bytes = generate_order_receipt_pdf(order)
        except ImportError:
            return Response(
                {"error": "reportlab não instalado — execute pip install reportlab"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.exception("Failed to generate receipt for order %s: %s", order_id, exc)
            return Response({"error": "Erro ao gerar PDF"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        filename = f"recibo-{order.order_number}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response
