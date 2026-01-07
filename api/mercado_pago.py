import mercadopago
import logging
import re
import hashlib
import hmac
from typing import Optional
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class MercadoPagoService:
    """
    Complete Mercado Pago payment integration service.
    Handles preference creation, payment processing, and webhook notifications.
    """

    def __init__(self):
        self.access_token = settings.MERCADO_PAGO_ACCESS_TOKEN
        if not self.access_token:
            logger.warning("MERCADO_PAGO_ACCESS_TOKEN is not configured - payments will fail")
            self.sdk = None
        else:
            self.sdk = mercadopago.SDK(self.access_token)
        
        self.statement_descriptor = getattr(settings, 'MERCADO_PAGO_STATEMENT_DESCRIPTOR', 'PASTITA')

    @staticmethod
    def verify_webhook_signature(request) -> tuple[bool, str]:
        """Verify Mercado Pago webhook signature when secret is configured."""
        secret = getattr(settings, 'MERCADO_PAGO_WEBHOOK_SECRET', '')
        if not secret:
            return False, 'missing_secret'

        signature = request.headers.get('x-signature')
        request_id = request.headers.get('x-request-id')
        if not signature or not request_id:
            return False, 'missing_headers'

        parts = {}
        for chunk in signature.split(','):
            if '=' in chunk:
                key, value = chunk.strip().split('=', 1)
                parts[key] = value

        ts = parts.get('ts')
        v1 = parts.get('v1')
        if not ts or not v1:
            return False, 'invalid_signature'

        payload = request.body.decode('utf-8')
        manifest = f'{ts}.{request_id}.{payload}'
        expected = hmac.new(secret.encode('utf-8'), manifest.encode('utf-8'), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected, v1):
            return False, 'signature_mismatch'

        return True, 'ok'

    def _clean_cpf(self, cpf: str) -> str:
        """Remove formatting from CPF."""
        if not cpf:
            return ''
        return re.sub(r'[^0-9]', '', cpf)

    def _clean_phone(self, phone: str) -> dict:
        """Parse phone number into area code and number."""
        if not phone:
            return {'area_code': '11', 'number': '999999999'}
        
        phone = re.sub(r'[^0-9]', '', phone)
        if len(phone) >= 11:
            return {'area_code': phone[:2], 'number': phone[2:]}
        elif len(phone) >= 9:
            return {'area_code': '11', 'number': phone}
        return {'area_code': '11', 'number': '999999999'}

    def _normalize_checkout_payment_method(self, payment_type_id: str, payment_method_id: str) -> Optional[str]:
        """Map MP payment type to local checkout payment_method."""
        mapping = {
            'credit_card': 'credit_card',
            'debit_card': 'debit_card',
            'pix': 'pix',
            'ticket': 'cash',
            'bank_transfer': 'bank_transfer',
        }
        if payment_type_id in mapping:
            return mapping[payment_type_id]
        if payment_method_id == 'pix':
            return 'pix'
        return None

    def _split_name(self, full_name: str) -> tuple[str, str]:
        """Split a full name into first and last name."""
        if not full_name:
            return 'Cliente', ''
        parts = full_name.strip().split()
        if not parts:
            return 'Cliente', ''
        first_name = parts[0]
        last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''
        return first_name, last_name

    def create_preference_from_order(self, order, buyer_data: dict) -> dict:
        """
        Create Mercado Pago payment preference from order.
        
        Args:
            order: Order model instance with items
            buyer_data: Dict with name, email, cpf, phone
            
        Returns:
            Dict with init_point, sandbox_init_point, id
        """
        if not self.sdk:
            raise ValueError("Mercado Pago is not configured. Set MERCADO_PAGO_ACCESS_TOKEN.")
        
        try:
            # Build items list from order
            items = []
            for item in order.items.select_related('product').all():
                product = item.product
                items.append({
                    "id": str(product.id),
                    "title": product.name[:255],
                    "description": (product.description or '')[:255],
                    "picture_url": product.image.url if product.image else None,
                    "category_id": product.category or "others",
                    "quantity": int(item.quantity),
                    "currency_id": "BRL",
                    "unit_price": float(item.price)
                })

            # Build payer information
            phone = self._clean_phone(buyer_data.get('phone', ''))
            cpf = self._clean_cpf(buyer_data.get('cpf', ''))
            
            payer = {
                "name": buyer_data.get('name', 'Cliente')[:100],
                "surname": "",
                "email": buyer_data.get('email', order.user.email),
                "phone": phone,
            }
            
            # Add identification if CPF provided
            if cpf:
                payer["identification"] = {
                    "type": "CPF",
                    "number": cpf
                }

            # Build preference data
            now = timezone.now()
            preference_data = {
                "items": items,
                "payer": payer,
                "back_urls": {
                    "success": f"{settings.FRONTEND_URL}/sucesso?order={order.order_number}",
                    "failure": f"{settings.FRONTEND_URL}/erro?order={order.order_number}",
                    "pending": f"{settings.FRONTEND_URL}/pendente?order={order.order_number}"
                },
                "auto_return": "approved",
                "notification_url": f"{settings.BACKEND_URL}/api/webhooks/mercado_pago/",
                "external_reference": str(order.id),
                "statement_descriptor": self.statement_descriptor[:22],
                "expires": True,
                "expiration_date_from": now.isoformat(),
                "expiration_date_to": (now + timedelta(hours=24)).isoformat(),
                "payment_methods": {
                    "excluded_payment_types": [],
                    "installments": 12,
                    "default_installments": 1
                },
                "shipments": {
                    "receiver_address": {
                        "zip_code": order.shipping_zip_code,
                        "street_name": order.shipping_address[:100],
                        "city_name": order.shipping_city,
                        "state_name": order.shipping_state
                    }
                }
            }

            logger.info(f"Creating MP preference for order {order.order_number}")
            
            preference_response = self.sdk.preference().create(preference_data)
            
            if preference_response["status"] not in [200, 201]:
                error_msg = preference_response.get('response', {})
                logger.error(f"MP preference creation failed: {error_msg}")
                raise Exception(f"Mercado Pago error: {error_msg}")

            response = preference_response["response"]
            logger.info(f"MP preference created: {response.get('id')} for order {order.order_number}")
            
            return {
                'id': response.get('id'),
                'init_point': response.get('init_point'),
                'sandbox_init_point': response.get('sandbox_init_point'),
                'collector_id': response.get('collector_id'),
                'date_created': response.get('date_created')
            }

        except Exception as e:
            logger.error(f"Error creating MP preference for order {order.id}: {str(e)}")
            raise

    def create_payment_from_order(self, order, buyer_data: dict, payment_data: dict) -> dict:
        """
        Create Mercado Pago payment for Checkout Transparente.

        payment_data expects:
          - method/payment_method: pix | credit_card | debit_card | cash
          - payment_method_id: pix, visa, master, bolbradesco, etc.
          - token (required for card)
          - installments (optional)
          - issuer_id (optional)
        """
        if not self.sdk:
            raise ValueError("Mercado Pago is not configured. Set MERCADO_PAGO_ACCESS_TOKEN.")

        if not payment_data:
            raise ValueError("payment_data is required for transparent checkout")

        method = (payment_data.get('method') or payment_data.get('payment_method') or '').strip().lower()
        payment_method_id = payment_data.get('payment_method_id')
        if not method:
            if payment_method_id == 'pix':
                method = 'pix'
            elif payment_data.get('token'):
                method = 'card'
            elif payment_method_id:
                method = 'cash'
        description = payment_data.get('description') or f"Pedido {order.order_number}"

        first_name, last_name = self._split_name(buyer_data.get('name', 'Cliente'))
        payer = {
            "email": buyer_data.get('email', order.user.email),
            "first_name": first_name[:100],
            "last_name": last_name[:100],
            "phone": self._clean_phone(buyer_data.get('phone', '')),
        }

        cpf = self._clean_cpf(buyer_data.get('cpf', ''))
        if cpf:
            payer["identification"] = {
                "type": "CPF",
                "number": cpf
            }

        payment_request = {
            "transaction_amount": float(order.total_amount),
            "description": description[:255],
            "payer": payer,
            "external_reference": str(order.id),
            "notification_url": f"{settings.BACKEND_URL}/api/webhooks/mercado_pago/",
            "metadata": {
                "order_id": str(order.id),
                "order_number": order.order_number,
            },
        }

        if method in ['pix'] or payment_method_id == 'pix':
            payment_request["payment_method_id"] = "pix"
        elif method in ['credit_card', 'debit_card', 'card']:
            token = payment_data.get('token')
            if not token or not payment_method_id:
                raise ValueError("token and payment_method_id are required for card payments")
            payment_request["statement_descriptor"] = self.statement_descriptor[:22]
            payment_request["token"] = token
            payment_request["payment_method_id"] = payment_method_id
            payment_request["installments"] = int(payment_data.get('installments') or 1)
            issuer_id = payment_data.get('issuer_id')
            if issuer_id:
                payment_request["issuer_id"] = str(issuer_id)
        elif method in ['cash', 'ticket', 'boleto']:
            if not payment_method_id:
                raise ValueError("payment_method_id is required for cash payments")
            payment_request["payment_method_id"] = payment_method_id
        else:
            raise ValueError("Unsupported payment method for transparent checkout")

        logger.info(f"Creating MP payment for order {order.order_number} ({method})")
        payment_response = self.sdk.payment().create(payment_request)

        if payment_response["status"] not in [200, 201]:
            error_msg = payment_response.get('response', {})
            logger.error(f"MP payment creation failed: {error_msg}")
            raise Exception(f"Mercado Pago error: {error_msg}")

        response = payment_response["response"]
        logger.info(f"MP payment created: {response.get('id')} for order {order.order_number}")
        return response

    def get_payment_info(self, payment_id: str) -> dict:
        """Fetch payment details from Mercado Pago."""
        if not self.sdk:
            raise ValueError("Mercado Pago is not configured")
        
        response = self.sdk.payment().get(payment_id)
        
        if response["status"] != 200:
            logger.error(f"Failed to get payment {payment_id}: {response}")
            return None
        
        return response["response"]

    def find_payment_by_external_reference(self, external_reference: str) -> dict:
        """Find most recent payment by external reference (order id)."""
        if not self.sdk:
            raise ValueError("Mercado Pago is not configured")

        response = self.sdk.payment().search({
            "external_reference": str(external_reference),
            "sort": "date_created",
            "criteria": "desc",
            "limit": 1,
        })

        if response.get("status") != 200:
            logger.warning(f"MP payment search failed: {response}")
            return None

        results = response.get("response", {}).get("results", [])
        if not results:
            return None
        return results[0]

    def process_payment_notification(self, mp_payment_id: str, payload: dict) -> bool:
        """
        Process payment webhook notification from Mercado Pago.
        Updates order and checkout status based on payment result.
        """
        from .models import Order, Checkout, PaymentNotification
        from .ws_utils import broadcast_admin_event
        
        try:
            # Fetch current payment status from MP
            payment_data = self.get_payment_info(mp_payment_id)
            
            if not payment_data:
                logger.error(f"Could not fetch payment data for {mp_payment_id}")
                return False
            
            # Extract key information
            order_id = payment_data.get('external_reference')
            mp_status = payment_data.get('status')
            mp_status_detail = payment_data.get('status_detail', '')
            payment_type_id = payment_data.get('payment_type_id', '')
            payment_method_id = payment_data.get('payment_method_id', '')
            
            logger.info(
                f"Processing payment {mp_payment_id}: status={mp_status}, "
                f"order={order_id}, type={payment_type_id}, method={payment_method_id}"
            )
            
            if not order_id:
                logger.error(f"No external_reference in payment {mp_payment_id}")
                return False

            # Find order
            try:
                order = Order.objects.get(id=order_id)
            except Order.DoesNotExist:
                logger.error(f"Order {order_id} not found for payment {mp_payment_id}")
                return False

            # Map MP status to order status
            previous_status = order.status
            
            status_mapping = {
                'approved': 'processing',
                'authorized': 'processing',
                'in_process': 'pending',
                'in_mediation': 'pending',
                'pending': 'pending',
                'rejected': 'cancelled',
                'cancelled': 'cancelled',
                'refunded': 'cancelled',
                'charged_back': 'cancelled'
            }
            
            new_status = status_mapping.get(mp_status, order.status)
            
            if new_status != previous_status:
                order.status = new_status
                order.save()
                logger.info(f"Order {order.order_number} status: {previous_status} -> {new_status}")
                
                # If cancelled, restore stock
                if new_status == 'cancelled' and previous_status != 'cancelled':
                    for item in order.items.all():
                        item.product.stock_quantity += item.quantity
                        item.product.save()
                    logger.info(f"Stock restored for cancelled order {order.order_number}")

            # Update checkout if exists
            try:
                checkout = Checkout.objects.get(order=order)
                checkout.mercado_pago_payment_id = str(mp_payment_id)
                checkout.payment_method = self._normalize_checkout_payment_method(
                    payment_type_id,
                    payment_method_id
                )
                
                checkout_status_mapping = {
                    'approved': 'completed',
                    'authorized': 'processing',
                    'in_process': 'processing',
                    'in_mediation': 'pending',
                    'pending': 'pending',
                    'rejected': 'failed',
                    'cancelled': 'cancelled',
                    'refunded': 'refunded'
                }
                checkout.payment_status = checkout_status_mapping.get(mp_status, checkout.payment_status)
                
                if mp_status == 'approved':
                    checkout.completed_at = timezone.now()
                
                checkout.save()
                logger.info(f"Checkout {checkout.id} updated: status={checkout.payment_status}")
                
            except Checkout.DoesNotExist:
                logger.warning(f"No checkout found for order {order.id}")

            try:
                broadcast_admin_event(
                    "payment",
                    {
                        "order_number": order.order_number,
                        "order_status": order.status,
                        "payment_status": checkout.payment_status if 'checkout' in locals() else mp_status,
                        "payment_id": str(mp_payment_id),
                    },
                )
            except Exception:
                logger.exception("Failed to broadcast payment event")

            # Create notification record
            try:
                PaymentNotification.objects.update_or_create(
                    mercado_pago_id=str(mp_payment_id),
                    defaults={
                        'notification_type': 'payment',
                        'checkout': checkout if 'checkout' in locals() else None,
                        'payload': payment_data,
                        'status': mp_status,
                        'status_detail': mp_status_detail,
                        'processed': True,
                        'processed_at': timezone.now()
                    }
                )
            except Exception as e:
                logger.error(f"Failed to create notification record: {str(e)}")

            return True

        except Exception as e:
            logger.error(f"Error processing payment {mp_payment_id}: {str(e)}", exc_info=True)
            return False

    def process_merchant_order(self, merchant_order_id: str, payload: dict) -> bool:
        """
        Process merchant order notification.
        Merchant orders contain multiple payments and are used for marketplace scenarios.
        """
        logger.info(f"Merchant order notification received: {merchant_order_id}")
        
        if not self.sdk:
            return False
        
        try:
            response = self.sdk.merchant_order().get(merchant_order_id)
            
            if response["status"] != 200:
                logger.error(f"Failed to get merchant order {merchant_order_id}")
                return False
            
            merchant_order = response["response"]
            
            # Process each payment in the merchant order
            for payment in merchant_order.get('payments', []):
                if payment.get('status') == 'approved':
                    self.process_payment_notification(payment['id'], {})
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing merchant order {merchant_order_id}: {str(e)}")
            return False

    def refund_payment(self, payment_id: str, amount: float = None) -> dict:
        """
        Refund a payment (full or partial).
        
        Args:
            payment_id: Mercado Pago payment ID
            amount: Amount to refund (None for full refund)
        """
        if not self.sdk:
            raise ValueError("Mercado Pago is not configured")
        
        try:
            refund_data = {}
            if amount:
                refund_data['amount'] = amount
            
            response = self.sdk.refund().create(payment_id, refund_data)
            
            if response["status"] not in [200, 201]:
                raise Exception(f"Refund failed: {response.get('response')}")
            
            logger.info(f"Refund created for payment {payment_id}: {response['response']}")
            return response["response"]
            
        except Exception as e:
            logger.error(f"Error refunding payment {payment_id}: {str(e)}")
            raise
