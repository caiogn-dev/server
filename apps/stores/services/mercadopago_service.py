"""
Mercado Pago Service - Processamento de pagamentos e webhooks.
"""
import logging
from typing import Dict, Any, Optional
import mercadopago

from django.conf import settings
from apps.stores.models import StorePayment, StoreOrder

logger = logging.getLogger(__name__)


class MercadoPagoService:
    """
    Serviço para integração com Mercado Pago.
    """
    
    def __init__(self):
        self.sdk = mercadopago.SDK(settings.MERCADO_PAGO_ACCESS_TOKEN)
    
    def process_payment_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa webhook de pagamento do Mercado Pago.
        """
        data_id = payload.get('data', {}).get('id')
        if not data_id:
            logger.error("Webhook sem data.id")
            return {'processed': False, 'error': 'Missing data.id'}
        
        try:
            # Buscar detalhes do pagamento na API do MP
            payment_info = self.sdk.payment().get(data_id)
            
            if payment_info['status'] != 200:
                logger.error(f"Erro ao buscar pagamento {data_id}: {payment_info}")
                return {'processed': False, 'error': 'API error'}
            
            payment_data = payment_info['response']
            external_ref = payment_data.get('external_reference')
            
            if not external_ref:
                logger.warning(f"Pagamento {data_id} sem external_reference")
                return {'processed': False, 'error': 'No external_reference'}
            
            # Buscar pagamento no nosso sistema
            try:
                payment = StorePayment.objects.get(
                    transaction_id=external_ref
                )
                
                # Atualizar status
                mp_status = payment_data.get('status')
                status_map = {
                    'approved': StorePayment.PaymentStatus.CONFIRMED,
                    'pending': StorePayment.PaymentStatus.PENDING,
                    'in_process': StorePayment.PaymentStatus.PENDING,
                    'rejected': StorePayment.PaymentStatus.FAILED,
                    'cancelled': StorePayment.PaymentStatus.CANCELLED,
                    'refunded': StorePayment.PaymentStatus.REFUNDED,
                }
                
                new_status = status_map.get(mp_status, StorePayment.PaymentStatus.PENDING)
                
                if payment.status != new_status:
                    payment.status = new_status
                    
                    if new_status == StorePayment.PaymentStatus.CONFIRMED:
                        payment.paid_at = payment_data.get('date_approved')
                        payment.receipt_url = payment_data.get('transaction_details', {}).get('external_resource_url')
                    
                    payment.save(update_fields=['status', 'paid_at', 'receipt_url', 'updated_at'])
                    
                    logger.info(f"Pagamento {payment.id} atualizado para {new_status}")
                
                return {
                    'processed': True,
                    'payment_id': payment.id,
                    'status': new_status
                }
                
            except StorePayment.DoesNotExist:
                logger.warning(f"Pagamento com external_reference {external_ref} não encontrado")
                return {'processed': False, 'error': 'Payment not found'}
                
        except Exception as e:
            logger.exception(f"Erro ao processar webhook de pagamento: {e}")
            return {'processed': False, 'error': str(e)}
    
    def get_payment_status(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca status de um pagamento no Mercado Pago.
        """
        try:
            result = self.sdk.payment().get(payment_id)
            if result['status'] == 200:
                return result['response']
            return None
        except Exception as e:
            logger.exception(f"Erro ao buscar pagamento {payment_id}: {e}")
            return None
    
    def generate_pix(self, order: StoreOrder, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gera um pagamento PIX para um pedido.
        """
        try:
            preference_data = {
                "items": [
                    {
                        "title": f"Pedido {order.order_number}",
                        "quantity": 1,
                        "unit_price": float(order.total),
                    }
                ],
                "external_reference": str(order.id),
                "payer": {
                    "email": customer_data.get('email', 'cliente@exemplo.com'),
                    "first_name": customer_data.get('name', 'Cliente'),
                },
                "payment_methods": {
                    "excluded_payment_types": [
                        {"id": "credit_card"},
                        {"id": "debit_card"},
                        {"id": "ticket"},
                    ],
                    "installments": 1,
                },
            }
            
            result = self.sdk.preference().create(preference_data)
            
            if result['status'] == 201:
                return {
                    'success': True,
                    'preference_id': result['response']['id'],
                    'init_point': result['response']['init_point'],
                }
            else:
                logger.error(f"Erro ao criar preferência: {result}")
                return {'success': False, 'error': 'API error'}
                
        except Exception as e:
            logger.exception(f"Erro ao gerar PIX: {e}")
            return {'success': False, 'error': str(e)}
