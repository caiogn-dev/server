"""
Celery tasks para commerce - Pedidos e notificações.
"""
from celery import shared_task
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


@shared_task
def notify_new_order(order_id):
    """Notificar novo pedido via WebSocket."""
    from apps.commerce.models import Order
    
    try:
        order = Order.objects.select_related('store').get(id=order_id)
        channel_layer = get_channel_layer()
        
        # Broadcast para o grupo da loja
        async_to_sync(channel_layer.group_send)(
            f'orders_{order.store.slug}',
            {
                'type': 'new_order',
                'order': {
                    'id': str(order.id),
                    'customer_name': order.customer_name,
                    'total': str(order.total),
                    'status': order.status,
                    'created_at': order.created_at.isoformat()
                }
            }
        )
        
        return {'notified': True}
    except Exception as e:
        return {'error': str(e)}


@shared_task
def notify_order_update(order_id):
    """Notificar atualização de pedido via WebSocket."""
    from apps.commerce.models import Order
    
    try:
        order = Order.objects.select_related('store').get(id=order_id)
        channel_layer = get_channel_layer()
        
        async_to_sync(channel_layer.group_send)(
            f'orders_{order.store.slug}',
            {
                'type': 'order_update',
                'order': {
                    'id': str(order.id),
                    'status': order.status,
                    'updated_at': order.updated_at.isoformat()
                }
            }
        )
        
        return {'notified': True}
    except Exception as e:
        return {'error': str(e)}


@shared_task
def send_order_confirmation(order_id):
    """Enviar confirmação de pedido via WhatsApp."""
    from apps.commerce.models import Order
    from apps.messaging_v2.models import Conversation, UnifiedMessage
    from apps.messaging_v2.tasks import send_whatsapp_message
    
    try:
        order = Order.objects.get(id=order_id)
        
        # Criar conversa se não existir
        conversation, _ = Conversation.objects.get_or_create(
            customer_phone=order.customer_phone,
            defaults={
                'customer_name': order.customer_name,
                'platform': 'whatsapp',
                'store': order.store
            }
        )
        
        # Mensagem de confirmação
        message_text = f"""
Olá {order.customer_name}! 👋

Seu pedido #{order.id[:8]} foi recebido com sucesso! ✅

📋 *Resumo do Pedido:*
{order.items_summary}

💰 *Total:* R$ {order.total}

⏰ *Tempo estimado:* 30-45 minutos

Agradecemos a preferência! 🙏
        """.strip()
        
        message = UnifiedMessage.objects.create(
            conversation=conversation,
            direction=UnifiedMessage.Direction.OUTBOUND,
            text=message_text
        )
        
        send_whatsapp_message.delay(str(message.id))
        
        return {'sent': True}
    except Exception as e:
        return {'error': str(e)}


@shared_task
def update_dashboard_metrics(store_slug=None):
    """Atualizar métricas do dashboard em tempo real."""
    from apps.commerce.models import Order
    from apps.messaging_v2.models import Conversation
    from apps.commerce.models import Store
    
    try:
        channel_layer = get_channel_layer()
        
        if store_slug:
            store = Store.objects.get(slug=store_slug)
            
            # Calcular métricas
            today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            metrics = {
                'active_conversations': Conversation.objects.filter(
                    store=store, is_open=True
                ).count(),
                'pending_orders': Order.objects.filter(
                    store=store, status='pending'
                ).count(),
                'today_orders': Order.objects.filter(
                    store=store, created_at__gte=today
                ).count(),
                'today_revenue': sum(
                    float(o.total) for o in Order.objects.filter(
                        store=store, created_at__gte=today, status__in=['completed', 'paid']
                    )
                )
            }
            
            async_to_sync(channel_layer.group_send)(
                f'dashboard_{store_slug}',
                {
                    'type': 'metrics_update',
                    'data': metrics
                }
            )
        
        return {'updated': True}
    except Exception as e:
        return {'error': str(e)}
