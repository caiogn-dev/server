"""
Order Signals - Sinais para notificações automáticas de status de pedido.

Este módulo escuta mudanças de status em StoreOrder e envia notificações
automáticas via WhatsApp para o cliente.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.stores.models import StoreOrder

logger = logging.getLogger(__name__)


# Mapeamento de status para mensagens padrão
DEFAULT_STATUS_MESSAGES = {
    'confirmed': """✅ *Pedido Confirmado!*

Olá {customer_name}!

Seu pedido *#{order_number}* foi confirmado e já está em nossa fila de preparo.

💰 Total: R$ {total:.2f}
🕐 Previsão: 30-45 minutos

Agradecemos a preferência! 🍝""",

    'preparing': """👨‍🍳 *Pedido em Preparo!*

Olá {customer_name}!

Seu pedido *#{order_number}* está sendo preparado com muito carinho!

Nossa equipe está trabalhando para que tudo fique perfeito.

Em breve avisaremos quando estiver pronto! 🍝""",

    'ready': """📦 *Pedido Pronto!*

Olá {customer_name}!

Seu pedido *#{order_number}* está pronto!

{delivery_text}

Agradecemos a preferência! 🍝""",

    'out_for_delivery': """🛵 *Saiu para Entrega!*

Olá {customer_name}!

Seu pedido *#{order_number}* saiu para entrega!

O entregador está a caminho do endereço:
{address}

Tempo estimado: 15-20 minutos

Agradecemos a preferência! 🍝""",

    'delivered': """✅ *Pedido Entregue!*

Olá {customer_name}!

Seu pedido *#{order_number}* foi entregue!

Esperamos que aproveite sua refeição. 🍝

Se tiver algum feedback, ficaremos felizes em ouvir!

Obrigado pela preferência!""",

    'cancelled': """❌ *Pedido Cancelado*

Olá {customer_name}!

Seu pedido *#{order_number}* foi cancelado.

Se tiver alguma dúvida ou precisar de ajuda, entre em contato conosco.

Agradecemos a compreensão.""",
}


def get_status_message(order: StoreOrder, status: str) -> str:
    """
    Busca mensagem automática configurada ou usa padrão.
    
    Args:
        order: Instância do pedido
        status: Novo status do pedido
    
    Returns:
        Texto da mensagem formatada
    """
    from apps.automation.models import AutoMessage
    
    # Mapeia status para event_type
    event_map = {
        'confirmed': 'order_confirmed',
        'preparing': 'order_preparing',
        'ready': 'order_ready',
        'out_for_delivery': 'order_out_for_delivery',
        'delivered': 'order_delivered',
        'cancelled': 'order_cancelled',
    }
    
    event_type = event_map.get(status)
    if not event_type:
        return None
    
    # Busca mensagem automática configurada
    try:
        # Obtém company da loja
        company = None
        if hasattr(order.store, 'automation_profile'):
            company = order.store.automation_profile
        
        if company:
            auto_message = AutoMessage.objects.filter(
                company=company,
                event_type=event_type,
                is_active=True
            ).first()
            
            if auto_message:
                # Renderiza mensagem com contexto
                context = {
                    'customer_name': order.customer_name or 'Cliente',
                    'order_number': order.order_number,
                    'total': order.total,
                    'address': order.delivery_address.get('address', 'Endereço não informado') if isinstance(order.delivery_address, dict) else str(order.delivery_address),
                }
                return auto_message.render_message(context)
    
    except Exception as e:
        logger.error(f"[get_status_message] Error fetching auto message: {e}")
    
    # Usa mensagem padrão
    template = DEFAULT_STATUS_MESSAGES.get(status)
    if not template:
        return None
    
    # Formata mensagem
    delivery_text = "Você pode retirar na loja quando quiser!" if order.delivery_method == 'pickup' else "Aguarde a entrega em breve!"
    
    address = order.delivery_address.get('address', 'Endereço não informado') if isinstance(order.delivery_address, dict) else str(order.delivery_address)
    
    return template.format(
        customer_name=order.customer_name or 'Cliente',
        order_number=order.order_number,
        total=order.total,
        delivery_text=delivery_text,
        address=address
    )


def send_whatsapp_notification(order: StoreOrder, message: str):
    """
    Envia notificação via WhatsApp.
    
    Args:
        order: Instância do pedido
        message: Texto da mensagem
    """
    try:
        from apps.whatsapp.services import MessageService
        from apps.whatsapp.utils import get_default_whatsapp_account
        from apps.core.utils import normalize_phone_number
        
        # Normaliza número de telefone
        phone = normalize_phone_number(order.customer_phone)
        if not phone:
            logger.warning(f"[send_whatsapp_notification] Invalid phone number for order {order.order_number}")
            return
        
        # Obtém conta WhatsApp
        account = None
        if order.store:
            account = order.store.get_whatsapp_account()
        
        if not account:
            account = get_default_whatsapp_account(create_if_missing=False)
        
        if not account:
            logger.warning(f"[send_whatsapp_notification] No WhatsApp account found for order {order.order_number}")
            return
        
        # Envia mensagem
        message_service = MessageService()
        message_service.send_text_message(
            account_id=str(account.id),
            to=phone,
            text=message,
            metadata={
                'source': 'order_status_notification',
                'order_id': str(order.id),
                'order_number': order.order_number,
                'status': order.status
            }
        )
        
        logger.info(f"[send_whatsapp_notification] Sent {order.status} notification for order {order.order_number}")
        
    except Exception as e:
        logger.error(f"[send_whatsapp_notification] Error sending notification: {e}")


@receiver(post_save, sender=StoreOrder)
def order_status_changed(sender, instance: StoreOrder, created: bool, **kwargs):
    """
    Signal handler para mudanças de status em StoreOrder.
    
    Envia notificação automática quando o status do pedido muda.
    """
    # Só processa se não for criação (status inicial é tratado separadamente)
    if created:
        # Para novos pedidos confirmados, envia notificação
        if instance.status == 'confirmed':
            message = get_status_message(instance, 'confirmed')
            if message:
                send_whatsapp_notification(instance, message)
        return
    
    # Para pedidos existentes, verifica se o status mudou
    # Usa o campo _previous_status se disponível, ou busca no banco
    try:
        # Tenta obter estado anterior do banco
        old_order = StoreOrder.objects.filter(id=instance.id).first()
        if old_order and old_order.status != instance.status:
            # Status mudou, envia notificação
            message = get_status_message(instance, instance.status)
            if message:
                send_whatsapp_notification(instance, message)
    except Exception as e:
        logger.error(f"[order_status_changed] Error processing status change: {e}")


def notify_order_status(order_id: str, status: str):
    """
    Função utilitária para notificar manualmente sobre status de pedido.
    
    Args:
        order_id: ID do pedido
        status: Status para notificar
    """
    try:
        order = StoreOrder.objects.filter(id=order_id).first()
        if not order:
            logger.warning(f"[notify_order_status] Order {order_id} not found")
            return
        
        message = get_status_message(order, status)
        if message:
            send_whatsapp_notification(order, message)
        else:
            logger.warning(f"[notify_order_status] No message for status {status}")
            
    except Exception as e:
        logger.error(f"[notify_order_status] Error: {e}")


# Task para Celery (processamento assíncrono)
def send_status_notification_task(order_id: str, status: str):
    """
    Task Celery para enviar notificação de status.
    
    Args:
        order_id: ID do pedido
        status: Status para notificar
    """
    notify_order_status(order_id, status)
