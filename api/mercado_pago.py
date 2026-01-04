import mercadopago
import logging
from django.conf import settings
from django.utils import timezone
from .models import PaymentNotification, Order

logger = logging.getLogger(__name__)

class MercadoPagoService:
    """Service for Mercado Pago payment integration"""

    def __init__(self):
        self.access_token = settings.MERCADO_PAGO_ACCESS_TOKEN
        if not self.access_token:
            raise ValueError("MERCADO_PAGO_ACCESS_TOKEN is not configured")
        
        self.sdk = mercadopago.SDK(self.access_token)

    def create_preference_from_order(self, order, buyer_data):
        """
        Cria a preferência baseada na Order salva e dados do comprador vindos do front.
        """
        try:
            # 1. Monta os itens
            items = []
            for item in order.items.all():
                items.append({
                    "id": str(item.product.id),
                    "title": item.product.name,
                    "description": item.product.description[:200] if item.product.description else "",
                    "quantity": int(item.quantity),
                    "currency_id": "BRL",
                    "unit_price": float(item.price)
                })

            # 2. Configura o pagador (Dados vêm do request, pois User pode estar desatualizado)
            payer = {
                "name": buyer_data.get('name', 'Cliente'),
                "email": buyer_data.get('email', order.user.email),
                "identification": {
                    "type": "CPF",
                    "number": buyer_data.get('cpf', '').replace('.', '').replace('-', '')
                }
            }

            # 3. Monta a preferência
            preference_data = {
                "items": items,
                "payer": payer,
                "back_urls": {
                    "success": f"{settings.FRONTEND_URL}/sucesso",
                    "failure": f"{settings.FRONTEND_URL}/erro",
                    "pending": f"{settings.FRONTEND_URL}/pendente"
                },
                "auto_return": "approved",
                "notification_url": f"{settings.BACKEND_URL}/api/webhooks/mercado-pago/",
                "external_reference": str(order.id), # VÍNCULO IMPORTANTE
                "statement_descriptor": "SUA LOJA",
                "expires": True,
                "expiration_date_from": timezone.now().isoformat(),
                "expiration_date_to": (timezone.now() + timezone.timedelta(days=1)).isoformat(),
            }

            preference_response = self.sdk.preference().create(preference_data)
            
            # Validação básica da resposta do MP
            if preference_response["status"] not in [200, 201]:
                raise Exception(f"MP Error: {preference_response.get('response', 'Unknown error')}")

            return preference_response["response"]

        except Exception as e:
            logger.error(f"Error creating preference: {str(e)}")
            raise e

    def process_payment_notification(self, mp_payment_id, payload):
        """
        Processa o webhook. Agora busca ORDER, não Checkout.
        """
        try:
            # Busca dados atualizados do pagamento no MP
            payment_info = self.sdk.payment().get(mp_payment_id)
            
            if payment_info["status"] != 200:
                logger.error(f"Payment lookup failed for ID {mp_payment_id}")
                return False
                
            payment_data = payment_info["response"]
            
            # Pega o ID da order que mandamos no create_preference
            order_id = payment_data.get('external_reference')
            status_mp = payment_data.get('status')
            
            if not order_id:
                logger.error("No external_reference found in payment data")
                return False

            # Busca a Order
            try:
                order = Order.objects.get(id=order_id)
            except Order.DoesNotExist:
                logger.error(f"Order {order_id} not found for payment {mp_payment_id}")
                return False

            # Atualiza status da Order
            previous_status = order.status
            
            if status_mp == 'approved':
                order.status = 'paid' # ou 'processing' dependendo da sua lógica de negócio
                # order.paid_at = timezone.now() # Se tiver esse campo
            elif status_mp == 'pending':
                order.status = 'pending'
            elif status_mp in ['rejected', 'cancelled']:
                order.status = 'cancelled'

            order.save()

            # Registra log da notificação (opcional, mas recomendado)
            PaymentNotification.objects.create(
                mercado_pago_id=str(mp_payment_id),
                order=order, # Certifique-se que seu model PaymentNotification tem FK para Order
                status=status_mp,
                payload=payment_data,
                processed=True
            )
            
            logger.info(f"Order {order.id} updated to {order.status} from MP status {status_mp}")
            return True

        except Exception as e:
            logger.error(f"Webhook error: {str(e)}")
            return False

    def process_merchant_order(self, merchant_order_id, payload):
        """Lida com notificações de merchant_order (menos comum para checkout simples)"""
        logger.info(f"Merchant Order received: {merchant_order_id} - Ignored for simple checkout")
        return True