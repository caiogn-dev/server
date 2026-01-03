import mercadopago
import logging
from decimal import Decimal
from django.utils import timezone
from django.conf import settings
from decouple import config

from .models import Checkout, PaymentNotification, Order

logger = logging.getLogger(__name__)


class MercadoPagoService:
    """Service for Mercado Pago payment integration"""

    def __init__(self):
        """Initialize Mercado Pago SDK with API credentials"""
        self.access_token = config('MERCADO_PAGO_ACCESS_TOKEN', default=None)
        if not self.access_token:
            raise ValueError("MERCADO_PAGO_ACCESS_TOKEN is not configured")
        
        self.sdk = mercadopago.SDK(self.access_token)

    def create_preference(self, checkout):
        """
        Create a payment preference in Mercado Pago
        
        Args:
            checkout: Checkout instance
            
        Returns:
            str: Preference ID or None if failed
        """
        try:
            items = []
            for order_item in checkout.order.items.all():
                items.append({
                    "title": order_item.product.name,
                    "description": order_item.product.description[:100],
                    "picture_url": self._get_product_image_url(order_item.product),
                    "quantity": order_item.quantity,
                    "unit_price": float(order_item.price),
                    "id": str(order_item.product.id)
                })

            preference_data = {
                "items": items,
                "payer": {
                    "name": checkout.customer_name.split()[0] if checkout.customer_name else "Customer",
                    "email": checkout.customer_email,
                    "phone": {
                        "area_code": "55",  # Brazil country code
                        "number": checkout.customer_phone.replace("+55", "").replace(" ", "")
                    },
                    "address": {
                        "street_name": checkout.billing_address.split(',')[0] if checkout.billing_address else "",
                        "street_number": "",
                        "zip_code": checkout.billing_zip_code
                    }
                },
                "back_urls": {
                    "success": f"{settings.FRONTEND_URL}/payment/success?token={checkout.session_token}",
                    "failure": f"{settings.FRONTEND_URL}/payment/failure?token={checkout.session_token}",
                    "pending": f"{settings.FRONTEND_URL}/payment/pending?token={checkout.session_token}"
                },
                "notification_url": f"{settings.BACKEND_URL}/api/webhooks/mercado-pago/",
                "statement_descriptor": "PASTITA.COM.BR",
                "external_reference": str(checkout.id),
                "expires": True,
                "expiration_date_from": timezone.now().isoformat(),
                "expiration_date_to": timezone.now().replace(day=timezone.now().day + 30).isoformat(),
            }

            result = self.sdk.preference().create(preference_data)
            
            if result["status"] == 201:
                preference_id = result["response"]["id"]
                logger.info(f"Mercado Pago preference created: {preference_id} for checkout {checkout.id}")
                return preference_id
            else:
                logger.error(f"Failed to create Mercado Pago preference: {result}")
                return None

        except Exception as e:
            logger.error(f"Error creating Mercado Pago preference: {str(e)}")
            return None

    def get_payment_link(self, preference_id):
        """
        Get payment link for a preference
        
        Args:
            preference_id: Mercado Pago preference ID
            
        Returns:
            str: Payment URL
        """
        return f"https://www.mercadopago.com.br/checkout/v1/redirect?pref_id={preference_id}"

    def get_payment_details(self, payment_id):
        """
        Get payment details from Mercado Pago
        
        Args:
            payment_id: Mercado Pago payment ID
            
        Returns:
            dict: Payment data or None if failed
        """
        try:
            result = self.sdk.payment().get(payment_id)
            
            if result["status"] == 200:
                return result["response"]
            else:
                logger.warning(f"Failed to get payment details: {result}")
                return None

        except Exception as e:
            logger.error(f"Error getting payment details: {str(e)}")
            return None

    def process_payment_notification(self, payment_id, payload):
        """
        Process payment notification from Mercado Pago
        
        Args:
            payment_id: Payment ID from webhook
            payload: Webhook payload
            
        Returns:
            bool: True if processed successfully
        """
        try:
            # Avoid duplicate processing
            if PaymentNotification.objects.filter(
                mercado_pago_id=payment_id
            ).exists():
                logger.info(f"Payment notification {payment_id} already processed")
                return True

            # Get payment details
            payment_data = self.get_payment_details(payment_id)
            if not payment_data:
                logger.error(f"Could not fetch payment details for {payment_id}")
                return False

            external_reference = payment_data.get('external_reference')
            status = payment_data.get('status')
            status_detail = payment_data.get('status_detail')

            # Find checkout by external reference (checkout ID)
            try:
                checkout = Checkout.objects.get(id=external_reference)
            except Checkout.DoesNotExist:
                logger.error(f"Checkout not found for reference {external_reference}")
                return False

            # Create notification record
            notification = PaymentNotification.objects.create(
                notification_type='payment',
                mercado_pago_id=payment_id,
                checkout=checkout,
                payload=payment_data,
                status=status,
                status_detail=status_detail,
                processed=False
            )

            # Update checkout based on payment status
            if status == 'approved':
                checkout.payment_status = 'completed'
                checkout.mercado_pago_payment_id = payment_id
                checkout.completed_at = timezone.now()
                checkout.save()

                # Update order status
                checkout.order.status = 'processing'
                checkout.order.save()

                logger.info(f"Payment {payment_id} approved for checkout {checkout.id}")

            elif status == 'pending':
                checkout.payment_status = 'processing'
                checkout.mercado_pago_payment_id = payment_id
                checkout.save()
                logger.info(f"Payment {payment_id} pending for checkout {checkout.id}")

            elif status == 'rejected' or status == 'cancelled':
                checkout.payment_status = 'failed'
                checkout.mercado_pago_payment_id = payment_id
                checkout.save()

                # Reset order status
                checkout.order.status = 'cancelled'
                checkout.order.save()

                logger.warning(f"Payment {payment_id} rejected for checkout {checkout.id}")

            elif status == 'refunded':
                checkout.payment_status = 'refunded'
                checkout.mercado_pago_payment_id = payment_id
                checkout.save()
                logger.info(f"Payment {payment_id} refunded for checkout {checkout.id}")

            notification.processed = True
            notification.processed_at = timezone.now()
            notification.save()

            return True

        except Exception as e:
            logger.error(f"Error processing payment notification: {str(e)}")
            return False

    def process_merchant_order(self, merchant_order_id, payload):
        """
        Process merchant order notification from Mercado Pago
        
        Args:
            merchant_order_id: Merchant order ID from webhook
            payload: Webhook payload
            
        Returns:
            bool: True if processed successfully
        """
        try:
            # This is typically handled through payment notifications
            logger.info(f"Merchant order notification received: {merchant_order_id}")
            
            notification = PaymentNotification.objects.create(
                notification_type='merchant_order',
                mercado_pago_id=merchant_order_id,
                payload=payload,
                status='received',
                processed=True,
                processed_at=timezone.now()
            )
            
            return True

        except Exception as e:
            logger.error(f"Error processing merchant order notification: {str(e)}")
            return False

    def refund_payment(self, payment_id, amount=None):
        """
        Refund a payment in Mercado Pago
        
        Args:
            payment_id: Mercado Pago payment ID
            amount: Optional refund amount (if not specified, refunds full amount)
            
        Returns:
            bool: True if refund successful
        """
        try:
            refund_data = {}
            if amount:
                refund_data['amount'] = float(amount)

            result = self.sdk.refund().create(payment_id, refund_data)

            if result["status"] == 201 or result["status"] == 200:
                logger.info(f"Refund successful for payment {payment_id}")
                return True
            else:
                logger.error(f"Refund failed: {result}")
                return False

        except Exception as e:
            logger.error(f"Error refunding payment: {str(e)}")
            return False

    def cancel_payment(self, payment_id):
        """
        Cancel a payment in Mercado Pago
        
        Args:
            payment_id: Mercado Pago payment ID
            
        Returns:
            bool: True if cancellation successful
        """
        try:
            # Note: Only pending payments can be cancelled
            cancel_data = {"status": "cancelled"}
            
            result = self.sdk.payment().update(payment_id, cancel_data)

            if result["status"] == 200:
                logger.info(f"Payment {payment_id} cancelled successfully")
                return True
            else:
                logger.error(f"Payment cancellation failed: {result}")
                return False

        except Exception as e:
            logger.error(f"Error cancelling payment: {str(e)}")
            return False

    def _get_product_image_url(self, product):
        """
        Get full URL for product image
        
        Args:
            product: Product instance
            
        Returns:
            str: Full image URL
        """
        if product.image:
            return f"{settings.BACKEND_URL}{product.image.url}"
        return f"{settings.BACKEND_URL}/static/placeholder.png"
