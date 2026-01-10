# -*- coding: utf-8 -*-
"""
Mercado Pago integration service for e-commerce.
"""
import logging
import uuid
import hmac
import hashlib
from decimal import Decimal
from typing import Optional, Dict, Any
from django.conf import settings
from django.utils import timezone as dj_timezone
from datetime import datetime, timedelta

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
        self.webhook_secret = getattr(settings, 'MERCADO_PAGO_WEBHOOK_SECRET', '')
        
        if HAS_MERCADOPAGO and self.access_token:
            self.sdk = mercadopago.SDK(self.access_token)
        else:
            self.sdk = None

    def is_configured(self) -> bool:
        """Check if Mercado Pago is properly configured"""
        return bool(self.sdk and self.access_token)

    def _format_expiration(self, delta: timedelta) -> str:
        """Return Mercado Pago date_of_expiration in ISO 8601 format with milliseconds."""
        expiration = dj_timezone.localtime(dj_timezone.now() + delta)
        # O Mercado Pago exige exatamente 3 dígitos de milissegundos (.000)
        # e o timezone com dois pontos (-03:00).
        return expiration.isoformat(timespec='milliseconds')

    def _apply_coupon_discount(
        self,
        payment_data: Dict[str, Any],
        discount_amount: float,
        coupon_code: Optional[str],
    ) -> None:
        """Attach coupon discount fields to a Mercado Pago payment payload."""
        if not discount_amount or discount_amount <= 0:
            return

        transaction_amount = payment_data.get('transaction_amount')
        if transaction_amount is not None:
            coupon_value = min(float(discount_amount), float(transaction_amount))
        else:
            coupon_value = float(discount_amount)

        payment_data['coupon_amount'] = coupon_value
        metadata = payment_data.get('metadata') or {}
        metadata['discount_amount'] = coupon_value
        if coupon_code:
            metadata['coupon_code'] = coupon_code
        payment_data['metadata'] = metadata
    
    def verify_webhook_signature(
        self,
        x_signature: str,
        x_request_id: str,
        data_id: str,
    ) -> bool:
        """
        Verify Mercado Pago webhook signature.
        
        The signature is calculated using HMAC-SHA256 with the webhook secret.
        The template is: id:[data.id];request-id:[x-request-id];ts:[ts];
        
        Args:
            x_signature: The x-signature header from the webhook request
            x_request_id: The x-request-id header from the webhook request
            data_id: The data.id from the webhook payload
            
        Returns:
            True if signature is valid, False otherwise
        """
        if not self.webhook_secret:
            # In production, fail closed - reject webhooks without secret configured
            is_production = not getattr(settings, 'DEBUG', True)
            if is_production:
                logger.error(
                    "SECURITY: Webhook secret not configured in production! "
                    "Set MERCADO_PAGO_WEBHOOK_SECRET environment variable."
                )
                return False
            else:
                logger.warning(
                    "Webhook secret not configured, skipping signature validation. "
                    "This is only acceptable in development mode."
                )
                return True
        
        if not x_signature:
            logger.warning("No x-signature header provided")
            return False
        
        try:
            # Parse the x-signature header
            # Format: ts=timestamp,v1=signature
            parts = {}
            for part in x_signature.split(','):
                if '=' in part:
                    key, value = part.split('=', 1)
                    parts[key.strip()] = value.strip()
            
            ts = parts.get('ts')
            v1 = parts.get('v1')
            
            if not ts or not v1:
                logger.warning(f"Invalid x-signature format: {x_signature}")
                return False
            
            # Build the manifest string
            # Template: id:[data.id];request-id:[x-request-id];ts:[ts];
            manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
            
            # Calculate HMAC-SHA256
            expected_signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                manifest.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures
            is_valid = hmac.compare_digest(expected_signature, v1)
            
            if not is_valid:
                logger.warning(f"Webhook signature mismatch. Expected: {expected_signature}, Got: {v1}")
            else:
                logger.debug(f"Webhook signature verified successfully for data_id: {data_id}")
            
            return is_valid
            
        except Exception as e:
            logger.exception(f"Error verifying webhook signature: {e}")
            return False

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

    def create_pix_payment(
        self,
        checkout_id: str,
        amount: float,
        customer_email: str,
        customer_name: str,
        customer_cpf: str,
        description: str = 'Pedido Pastita',
        external_reference: Optional[str] = None,
        discount_amount: float = 0.0,
        coupon_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a PIX payment directly (not a preference).
        This generates the QR code immediately.
        
        Args:
            checkout_id: Internal checkout ID
            amount: Amount to charge
            customer_email: Customer email
            customer_name: Customer full name
            customer_cpf: Customer CPF (required for PIX)
            description: Payment description
            external_reference: External reference for tracking
            discount_amount: Discount amount applied to the order
            coupon_code: Coupon code applied to the order
            
        Returns:
            Dict with payment_id, qr_code, qr_code_base64, status, etc.
        """
        if not self.is_configured():
            logger.error("Mercado Pago not configured")
            return {'success': False, 'error': 'Payment service not configured'}

        # Clean CPF (remove formatting)
        clean_cpf = ''.join(filter(str.isdigit, str(customer_cpf or '')))
        
        # Split name into first and last
        name_parts = customer_name.split() if customer_name else ['Cliente']
        first_name = name_parts[0] if name_parts else 'Cliente'
        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

        # PIX expiration (4 hours from now)
        expiration = self._format_expiration(timedelta(hours=4))
        logger.info("PIX expiration formatted: %s", expiration)

        payment_data = {
            'transaction_amount': float(amount),
            'description': description,
            'payment_method_id': 'pix',
            'payer': {
                'email': customer_email,
                'first_name': first_name,
                'last_name': last_name,
                'identification': {
                    'type': 'CPF',
                    'number': clean_cpf,
                } if clean_cpf else None,
            },
            'external_reference': external_reference or str(checkout_id),
            'notification_url': f'{self.backend_url}/api/v1/ecommerce/webhooks/mercado_pago/',
            'date_of_expiration': expiration,
        }

        # Remove None identification if CPF not provided
        if not clean_cpf:
            del payment_data['payer']['identification']

        self._apply_coupon_discount(payment_data, discount_amount, coupon_code)

        try:
            response = self.sdk.payment().create(payment_data)
            result = response.get('response', {})
            
            if response.get('status') in [200, 201]:
                # Extract PIX data from point_of_interaction
                poi = result.get('point_of_interaction', {})
                transaction_data = poi.get('transaction_data', {})
                
                logger.info(f"Created PIX payment {result.get('id')} for checkout {checkout_id}")
                return {
                    'success': True,
                    'payment_id': result.get('id'),
                    'status': result.get('status'),
                    'status_detail': result.get('status_detail'),
                    'qr_code': transaction_data.get('qr_code'),
                    'qr_code_base64': transaction_data.get('qr_code_base64'),
                    'ticket_url': transaction_data.get('ticket_url'),
                    'transaction_amount': result.get('transaction_amount'),
                    'date_of_expiration': result.get('date_of_expiration'),
                    'external_reference': result.get('external_reference'),
                }
            else:
                error_msg = result.get('message', 'Unknown error')
                cause = result.get('cause', [])
                if cause:
                    error_details = [c.get('description', '') for c in cause if c.get('description')]
                    if error_details:
                        error_msg = '; '.join(error_details)
                logger.error(f"Failed to create PIX payment: {response}")
                return {
                    'success': False,
                    'error': error_msg,
                    'status_code': response.get('status'),
                }
        except Exception as e:
            logger.exception(f"Error creating PIX payment: {e}")
            return {'success': False, 'error': str(e)}

    def create_boleto_payment(
        self,
        checkout_id: str,
        amount: float,
        customer_email: str,
        customer_name: str,
        customer_cpf: str,
        description: str = 'Pedido Pastita',
        external_reference: Optional[str] = None,
        discount_amount: float = 0.0,
        coupon_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a Boleto payment directly.
        
        Args:
            checkout_id: Internal checkout ID
            amount: Amount to charge
            customer_email: Customer email
            customer_name: Customer full name
            customer_cpf: Customer CPF (required for Boleto)
            description: Payment description
            external_reference: External reference for tracking
            discount_amount: Discount amount applied to the order
            coupon_code: Coupon code applied to the order
            
        Returns:
            Dict with payment_id, ticket_url, barcode, status, etc.
        """
        if not self.is_configured():
            logger.error("Mercado Pago not configured")
            return {'success': False, 'error': 'Payment service not configured'}

        # Clean CPF
        clean_cpf = ''.join(filter(str.isdigit, str(customer_cpf or '')))
        
        # Split name
        name_parts = customer_name.split() if customer_name else ['Cliente']
        first_name = name_parts[0] if name_parts else 'Cliente'
        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

        # Boleto expiration (3 days from now)
        expiration = self._format_expiration(timedelta(days=3))

        payment_data = {
            'transaction_amount': float(amount),
            'description': description,
            'payment_method_id': 'bolbradesco',
            'payer': {
                'email': customer_email,
                'first_name': first_name,
                'last_name': last_name,
                'identification': {
                    'type': 'CPF',
                    'number': clean_cpf,
                } if clean_cpf else None,
            },
            'external_reference': external_reference or str(checkout_id),
            'notification_url': f'{self.backend_url}/api/v1/ecommerce/webhooks/mercado_pago/',
            'date_of_expiration': expiration,
        }

        if not clean_cpf:
            del payment_data['payer']['identification']

        self._apply_coupon_discount(payment_data, discount_amount, coupon_code)

        try:
            response = self.sdk.payment().create(payment_data)
            result = response.get('response', {})
            
            if response.get('status') in [200, 201]:
                transaction_details = result.get('transaction_details', {})
                
                logger.info(f"Created Boleto payment {result.get('id')} for checkout {checkout_id}")
                return {
                    'success': True,
                    'payment_id': result.get('id'),
                    'status': result.get('status'),
                    'status_detail': result.get('status_detail'),
                    'ticket_url': transaction_details.get('external_resource_url'),
                    'barcode': result.get('barcode', {}).get('content'),
                    'transaction_amount': result.get('transaction_amount'),
                    'date_of_expiration': result.get('date_of_expiration'),
                    'external_reference': result.get('external_reference'),
                }
            else:
                error_msg = result.get('message', 'Unknown error')
                logger.error(f"Failed to create Boleto payment: {response}")
                return {
                    'success': False,
                    'error': error_msg,
                    'status_code': response.get('status'),
                }
        except Exception as e:
            logger.exception(f"Error creating Boleto payment: {e}")
            return {'success': False, 'error': str(e)}

    def create_card_payment(
        self,
        checkout_id: str,
        amount: float,
        token: str,
        payment_method_id: str,
        installments: int,
        customer_email: str,
        customer_name: str,
        customer_cpf: str,
        issuer_id: Optional[str] = None,
        description: str = 'Pedido Pastita',
        external_reference: Optional[str] = None,
        discount_amount: float = 0.0,
        coupon_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a card payment using a token from the frontend.
        
        Args:
            checkout_id: Internal checkout ID
            amount: Amount to charge
            token: Card token from Mercado Pago SDK
            payment_method_id: Payment method (visa, master, etc.)
            installments: Number of installments
            customer_email: Customer email
            customer_name: Customer full name
            customer_cpf: Customer CPF
            issuer_id: Card issuer ID
            description: Payment description
            external_reference: External reference for tracking
            discount_amount: Discount amount applied to the order
            coupon_code: Coupon code applied to the order
            
        Returns:
            Dict with payment_id, status, etc.
        """
        if not self.is_configured():
            logger.error("Mercado Pago not configured")
            return {'success': False, 'error': 'Payment service not configured'}

        # Clean CPF
        clean_cpf = ''.join(filter(str.isdigit, str(customer_cpf or '')))
        
        # Split name
        name_parts = customer_name.split() if customer_name else ['Cliente']
        first_name = name_parts[0] if name_parts else 'Cliente'
        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''

        payment_data = {
            'transaction_amount': float(amount),
            'token': token,
            'description': description,
            'installments': int(installments),
            'payment_method_id': payment_method_id,
            'payer': {
                'email': customer_email,
                'first_name': first_name,
                'last_name': last_name,
                'identification': {
                    'type': 'CPF',
                    'number': clean_cpf,
                } if clean_cpf else None,
            },
            'external_reference': external_reference or str(checkout_id),
            'notification_url': f'{self.backend_url}/api/v1/ecommerce/webhooks/mercado_pago/',
            'statement_descriptor': self.statement_descriptor,
        }

        if issuer_id:
            payment_data['issuer_id'] = issuer_id

        if not clean_cpf:
            del payment_data['payer']['identification']

        self._apply_coupon_discount(payment_data, discount_amount, coupon_code)

        try:
            response = self.sdk.payment().create(payment_data)
            result = response.get('response', {})
            
            if response.get('status') in [200, 201]:
                logger.info(f"Created card payment {result.get('id')} for checkout {checkout_id}")
                return {
                    'success': True,
                    'payment_id': result.get('id'),
                    'status': result.get('status'),
                    'status_detail': result.get('status_detail'),
                    'transaction_amount': result.get('transaction_amount'),
                    'installments': result.get('installments'),
                    'external_reference': result.get('external_reference'),
                }
            else:
                error_msg = result.get('message', 'Unknown error')
                cause = result.get('cause', [])
                if cause:
                    error_details = [c.get('description', '') for c in cause if c.get('description')]
                    if error_details:
                        error_msg = '; '.join(error_details)
                logger.error(f"Failed to create card payment: {response}")
                return {
                    'success': False,
                    'error': error_msg,
                    'status_code': response.get('status'),
                    'status_detail': result.get('status_detail'),
                }
        except Exception as e:
            logger.exception(f"Error creating card payment: {e}")
            return {'success': False, 'error': str(e)}
