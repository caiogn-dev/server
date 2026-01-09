"""
Mercado Pago integration service for e-commerce.
"""
import logging
import uuid
from decimal import Decimal
from typing import Optional, Dict, Any
from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import mercadopago
    HAS_MERCADOPAGO = True
except ImportError:
    HAS_MERCADOPAGO = False
    logger.warning("mercadopago package not installed. Payment features will be limited.")


class MercadoPagoService:
    """Service for Mercado Pago payment integration"""

    def __init__(self):
        self.access_token = getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', '')
        self.backend_url = getattr(settings, 'BACKEND_URL', 'http://localhost:8000')
        self.frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        self.statement_descriptor = getattr(settings, 'MERCADO_PAGO_STATEMENT_DESCRIPTOR', 'PASTITA')
        
        if HAS_MERCADOPAGO and self.access_token:
            self.sdk = mercadopago.SDK(self.access_token)
        else:
            self.sdk = None

    def is_configured(self) -> bool:
        """Check if Mercado Pago is properly configured"""
        return bool(self.sdk and self.access_token)

    def create_preference(
        self,
        checkout_id: str,
        items: list,
        total_amount: Decimal,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        external_reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a Mercado Pago payment preference.
        
        Args:
            checkout_id: Internal checkout ID
            items: List of items with name, quantity, unit_price
            total_amount: Total amount to charge
            customer_name: Customer full name
            customer_email: Customer email
            customer_phone: Customer phone
            external_reference: External reference for tracking
            
        Returns:
            Dict with preference_id, init_point (payment URL), etc.
        """
        if not self.is_configured():
            logger.error("Mercado Pago not configured")
            return {'error': 'Payment service not configured'}

        # Build items for preference
        preference_items = []
        for item in items:
            preference_items.append({
                'title': item.get('name', 'Product'),
                'quantity': int(item.get('quantity', 1)),
                'unit_price': float(item.get('unit_price', item.get('price', 0))),
                'currency_id': 'BRL',
            })

        # Build preference data
        preference_data = {
            'items': preference_items,
            'payer': {
                'name': customer_name.split()[0] if customer_name else 'Cliente',
                'surname': ' '.join(customer_name.split()[1:]) if len(customer_name.split()) > 1 else '',
                'email': customer_email,
                'phone': {
                    'area_code': customer_phone[:2] if len(customer_phone) > 2 else '',
                    'number': customer_phone[2:] if len(customer_phone) > 2 else customer_phone,
                }
            },
            'back_urls': {
                'success': f'{self.frontend_url}/sucesso',
                'failure': f'{self.frontend_url}/erro',
                'pending': f'{self.frontend_url}/pendente',
            },
            'auto_return': 'approved',
            'notification_url': f'{self.backend_url}/api/v1/ecommerce/webhooks/mercado_pago/',
            'external_reference': external_reference or str(checkout_id),
            'statement_descriptor': self.statement_descriptor,
            'payment_methods': {
                'excluded_payment_types': [],
                'installments': 12,
            },
        }

        try:
            response = self.sdk.preference().create(preference_data)
            result = response.get('response', {})
            
            if response.get('status') == 201:
                logger.info(f"Created preference {result.get('id')} for checkout {checkout_id}")
                return {
                    'success': True,
                    'preference_id': result.get('id'),
                    'init_point': result.get('init_point'),
                    'sandbox_init_point': result.get('sandbox_init_point'),
                }
            else:
                logger.error(f"Failed to create preference: {response}")
                return {
                    'success': False,
                    'error': result.get('message', 'Unknown error'),
                }
        except Exception as e:
            logger.exception(f"Error creating preference: {e}")
            return {'success': False, 'error': str(e)}

    def get_payment(self, payment_id: str) -> Dict[str, Any]:
        """Get payment details from Mercado Pago"""
        if not self.is_configured():
            return {'error': 'Payment service not configured'}

        try:
            response = self.sdk.payment().get(payment_id)
            if response.get('status') == 200:
                return {
                    'success': True,
                    'payment': response.get('response', {}),
                }
            return {
                'success': False,
                'error': response.get('response', {}).get('message', 'Unknown error'),
            }
        except Exception as e:
            logger.exception(f"Error getting payment {payment_id}: {e}")
            return {'success': False, 'error': str(e)}

    def process_webhook(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process Mercado Pago webhook notification.
        
        Args:
            data: Webhook payload from Mercado Pago
            
        Returns:
            Dict with payment status and details
        """
        notification_type = data.get('type') or data.get('topic')
        resource_id = data.get('data', {}).get('id') or data.get('id')

        if notification_type == 'payment':
            return self._process_payment_notification(resource_id)
        elif notification_type == 'merchant_order':
            return self._process_merchant_order(resource_id)
        
        logger.info(f"Unhandled notification type: {notification_type}")
        return {'success': True, 'message': 'Notification received'}

    def _process_payment_notification(self, payment_id: str) -> Dict[str, Any]:
        """Process payment notification"""
        result = self.get_payment(payment_id)
        if not result.get('success'):
            return result

        payment = result.get('payment', {})
        status = payment.get('status')
        external_reference = payment.get('external_reference')

        return {
            'success': True,
            'payment_id': payment_id,
            'status': status,
            'status_detail': payment.get('status_detail'),
            'external_reference': external_reference,
            'payment_method': payment.get('payment_method_id'),
            'payment_type': payment.get('payment_type_id'),
            'amount': payment.get('transaction_amount'),
            'payer_email': payment.get('payer', {}).get('email'),
        }

    def _process_merchant_order(self, order_id: str) -> Dict[str, Any]:
        """Process merchant order notification"""
        if not self.is_configured():
            return {'error': 'Payment service not configured'}

        try:
            response = self.sdk.merchant_order().get(order_id)
            if response.get('status') == 200:
                order = response.get('response', {})
                return {
                    'success': True,
                    'order_id': order_id,
                    'status': order.get('status'),
                    'external_reference': order.get('external_reference'),
                    'payments': order.get('payments', []),
                }
            return {'success': False, 'error': 'Failed to get merchant order'}
        except Exception as e:
            logger.exception(f"Error processing merchant order {order_id}: {e}")
            return {'success': False, 'error': str(e)}
