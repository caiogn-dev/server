"""
WhatsApp Automation Tasks (Celery)

Tarefas proativas automatizadas:
- Lembretes de pagamento PIX
- Recuperação de carrinho abandonado
- Notificações de status de pedido
- Solicitações de feedback
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_payment_reminder(self, order_id: str, reminder_type: str):
    """
    Envia lembrete de pagamento PIX
    
    Args:
        order_id: ID do pedido
        reminder_type: 'first' (30min), 'second' (2h), 'final' (24h)
    """
    from apps.stores.models.order import StoreOrder as Order
    from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService
    from apps.automation.models import AutoMessage
    
    try:
        order = Order.objects.get(id=order_id)
        
        if order.status != 'pending_payment':
            logger.info(f"Order {order_id} is not pending payment, skipping reminder")
            return
        
        # Busca template apropriado
        event_type_map = {
            'first': 'payment_reminder_1',
            'second': 'payment_reminder_2',
            'final': 'payment_expired',
        }
        
        event_type = event_type_map.get(reminder_type, 'payment_reminder_1')
        
        try:
            template = AutoMessage.objects.get(
                company=order.store.company_profile,
                event_type=event_type,
                is_active=True
            )
            
            # Calcula tempo restante
            if reminder_type == 'first':
                time_remaining = "30 minutos"
            elif reminder_type == 'second':
                time_remaining = "2 horas"
            else:
                time_remaining = "expirado"
            
            # Renderiza mensagem
            message = template.render({
                'customer_name': order.customer_name,
                'order_number': order.order_number,
                'amount': order.total,
                'pix_code': order.pix_code or 'N/A',
                'time_remaining': time_remaining,
            })
            
            # Envia mensagem
            from apps.whatsapp.models import WhatsAppAccount
            account = WhatsAppAccount.objects.filter(
                company_profile=order.store.company_profile
            ).first()
            
            if account:
                service = WhatsAppAPIService(account)
                service.send_text_message(
                    to=order.customer_phone,
                    text=message
                )
                
                logger.info(f"Payment reminder sent to {order.customer_phone} for order {order_id}")
                
                # Marca lembrete como enviado
                if not order.metadata:
                    order.metadata = {}
                order.metadata[f'payment_reminder_{reminder_type}_sent'] = timezone.now().isoformat()
                order.save()
            
        except AutoMessage.DoesNotExist:
            logger.warning(f"Template {event_type} not found for company {order.store.company_profile}")
            
    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found")
    except Exception as e:
        logger.error(f"Error sending payment reminder: {str(e)}")
        raise self.retry(exc=e)


@shared_task
def check_pending_payments():
    """
    Verifica pagamentos pendentes e agenda lembretes
    Executado a cada 10 minutos
    """
    from apps.stores.models.order import StoreOrder as Order
    
    now = timezone.now()
    
    # Lembrete 1: PIX gerado há 30 minutos
    pending_30min = Order.objects.filter(
        status='pending_payment',
        payment_method='pix',
        pix_generated_at__lte=now - timedelta(minutes=30),
        pix_generated_at__gt=now - timedelta(minutes=35),
    ).exclude(
        metadata__has_key='payment_reminder_first_sent'
    )
    
    for order in pending_30min:
        send_payment_reminder.delay(str(order.id), 'first')
        logger.info(f"Scheduled first payment reminder for order {order.id}")
    
    # Lembrete 2: PIX gerado há 2 horas
    pending_2h = Order.objects.filter(
        status='pending_payment',
        payment_method='pix',
        pix_generated_at__lte=now - timedelta(hours=2),
        pix_generated_at__gt=now - timedelta(hours=2, minutes=5),
    ).exclude(
        metadata__has_key='payment_reminder_second_sent'
    )
    
    for order in pending_2h:
        send_payment_reminder.delay(str(order.id), 'second')
        logger.info(f"Scheduled second payment reminder for order {order.id}")
    
    # Notificação final: PIX expirado (24h)
    expired_pix = Order.objects.filter(
        status='pending_payment',
        payment_method='pix',
        pix_generated_at__lte=now - timedelta(hours=24),
    ).exclude(
        metadata__has_key='payment_expired_notified'
    )
    
    for order in expired_pix:
        send_payment_reminder.delay(str(order.id), 'final')
        order.status = 'cancelled'
        order.metadata['cancellation_reason'] = 'pix_expired'
        order.metadata['payment_expired_notified'] = now.isoformat()
        order.save()
        logger.info(f"Order {order.id} cancelled due to PIX expiration")
    
    logger.info(f"Checked pending payments: {pending_30min.count()} first reminders, {pending_2h.count()} second reminders, {expired_pix.count()} expired")


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def send_cart_reminder(self, cart_id: str, reminder_type: str):
    """
    Envia lembrete de carrinho abandonado
    
    Args:
        cart_id: ID do carrinho
        reminder_type: '30min', '2h', '24h'
    """
    from apps.stores.models.cart import StoreCart as Cart
    from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService
    from apps.automation.models import AutoMessage
    
    try:
        cart = Cart.objects.get(id=cart_id)
        
        # Verifica se ainda tem itens
        if not cart.items.exists():
            logger.info(f"Cart {cart_id} is empty, skipping reminder")
            return
        
        # Verifica se já foi convertido em pedido
        from apps.stores.models.order import StoreOrder as Order
        recent_order = Order.objects.filter(
            customer_phone=cart.customer_phone,
            created_at__gte=cart.updated_at
        ).first()
        
        if recent_order:
            logger.info(f"Customer already placed order, skipping cart reminder")
            return
        
        # Busca template
        event_type_map = {
            '30min': 'cart_reminder_30',
            '2h': 'cart_reminder_2h',
            '24h': 'cart_reminder_24h',
        }
        
        event_type = event_type_map.get(reminder_type, 'cart_reminder')
        
        try:
            template = AutoMessage.objects.get(
                company=cart.store.company_profile,
                event_type=event_type,
                is_active=True
            )
            
            # Resume itens do carrinho
            items_summary = "\n".join([
                f"• {item.product.name} x{item.quantity} = R$ {item.total}"
                for item in cart.items.all()[:5]
            ])
            
            message = template.render({
                'customer_name': cart.customer_name or 'Cliente',
                'cart_items': items_summary,
                'cart_total': cart.total,
                'cart_item_count': cart.items.count(),
            })
            
            # Envia mensagem
            from apps.whatsapp.models import WhatsAppAccount
            account = WhatsAppAccount.objects.filter(
                company_profile=cart.store.company_profile
            ).first()
            
            if account:
                service = WhatsAppAPIService(account)
                
                # Envia mensagem com botões
                service.send_interactive_buttons(
                    to=cart.customer_phone,
                    body_text=message,
                    buttons=[
                        {'id': f'checkout_{cart.id}', 'title': '✅ Finalizar Pedido'},
                        {'id': f'view_cart_{cart.id}', 'title': '🛒 Ver Carrinho'},
                    ]
                )
                
                logger.info(f"Cart reminder sent to {cart.customer_phone} for cart {cart_id}")
                
        except AutoMessage.DoesNotExist:
            logger.warning(f"Template {event_type} not found")
            
    except Cart.DoesNotExist:
        logger.error(f"Cart {cart_id} not found")
    except Exception as e:
        logger.error(f"Error sending cart reminder: {str(e)}")
        raise self.retry(exc=e)


@shared_task
def check_abandoned_carts():
    """
    Verifica carrinhos abandonados
    Executado a cada 15 minutos
    """
    from apps.stores.models.cart import StoreCart as Cart
    
    now = timezone.now()
    
    # 30 minutos
    abandoned_30min = Cart.objects.filter(
        updated_at__lte=now - timedelta(minutes=30),
        updated_at__gt=now - timedelta(minutes=35),
        items__isnull=False,
    ).exclude(
        metadata__has_key='reminder_30min_sent'
    ).distinct()
    
    for cart in abandoned_30min:
        send_cart_reminder.delay(str(cart.id), '30min')
        if not cart.metadata:
            cart.metadata = {}
        cart.metadata['reminder_30min_sent'] = now.isoformat()
        cart.save()
    
    # 2 horas
    abandoned_2h = Cart.objects.filter(
        updated_at__lte=now - timedelta(hours=2),
        updated_at__gt=now - timedelta(hours=2, minutes=5),
        items__isnull=False,
    ).exclude(
        metadata__has_key='reminder_2h_sent'
    ).distinct()
    
    for cart in abandoned_2h:
        send_cart_reminder.delay(str(cart.id), '2h')
        if not cart.metadata:
            cart.metadata = {}
        cart.metadata['reminder_2h_sent'] = now.isoformat()
        cart.save()
    
    # 24 horas
    abandoned_24h = Cart.objects.filter(
        updated_at__lte=now - timedelta(hours=24),
        updated_at__gt=now - timedelta(hours=24, minutes=5),
        items__isnull=False,
    ).exclude(
        metadata__has_key='reminder_24h_sent'
    ).distinct()
    
    for cart in abandoned_24h:
        send_cart_reminder.delay(str(cart.id), '24h')
        if not cart.metadata:
            cart.metadata = {}
        cart.metadata['reminder_24h_sent'] = now.isoformat()
        cart.save()
    
    logger.info(f"Checked abandoned carts: {abandoned_30min.count()} (30min), {abandoned_2h.count()} (2h), {abandoned_24h.count()} (24h)")


@shared_task(bind=True, max_retries=2)
def notify_order_status_change(self, order_id: str, new_status: str):
    """
    Notifica cliente sobre mudança de status do pedido
    
    Args:
        order_id: ID do pedido
        new_status: Novo status
    """
    from apps.stores.models.order import StoreOrder as Order
    from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService
    from apps.automation.models import AutoMessage
    
    try:
        order = Order.objects.get(id=order_id)
        
        # Mapeia status para tipo de evento
        status_to_event = {
            'confirmed': 'order_confirmed',
            'preparing': 'order_preparing',
            'ready': 'order_ready',
            'out_for_delivery': 'order_out_for_delivery',
            'delivered': 'order_delivered',
            'cancelled': 'order_cancelled',
        }
        
        event_type = status_to_event.get(new_status)
        if not event_type:
            logger.warning(f"No template for status: {new_status}")
            return
        
        try:
            template = AutoMessage.objects.get(
                company=order.store.company_profile,
                event_type=event_type,
                is_active=True
            )
            
            # Status display
            status_display = {
                'confirmed': '✅ Confirmado',
                'preparing': '👨‍🍳 Em preparo',
                'ready': '✨ Pronto',
                'out_for_delivery': '🛵 Saiu para entrega',
                'delivered': '📦 Entregue',
                'cancelled': '❌ Cancelado',
            }.get(new_status, new_status)
            
            message = template.render({
                'customer_name': order.customer_name,
                'order_number': order.order_number,
                'order_status': status_display,
                'order_total': order.total,
            })
            
            # Envia mensagem
            from apps.whatsapp.models import WhatsAppAccount
            account = WhatsAppAccount.objects.filter(
                company_profile=order.store.company_profile
            ).first()
            
            if account:
                service = WhatsAppAPIService(account)
                service.send_text_message(
                    to=order.customer_phone,
                    text=message
                )
                
                logger.info(f"Status notification sent for order {order_id}: {new_status}")
                
        except AutoMessage.DoesNotExist:
            logger.warning(f"Template {event_type} not found")
            
    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found")
    except Exception as e:
        logger.error(f"Error notifying status change: {str(e)}")
        raise self.retry(exc=e)


@shared_task
def request_feedback(order_id: str):
    """
    Solicita avaliação após entrega
    Executado 30 minutos após pedido ser marcado como entregue
    """
    from apps.stores.models.order import StoreOrder as Order
    from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService
    from apps.automation.models import AutoMessage
    
    try:
        order = Order.objects.get(id=order_id)
        
        if order.status != 'delivered':
            logger.info(f"Order {order_id} not delivered, skipping feedback request")
            return
        
        try:
            template = AutoMessage.objects.get(
                company=order.store.company_profile,
                event_type='feedback_request',
                is_active=True
            )
            
            message = template.render({
                'customer_name': order.customer_name,
                'order_number': order.order_number,
            })
            
            from apps.whatsapp.models import WhatsAppAccount
            account = WhatsAppAccount.objects.filter(
                company_profile=order.store.company_profile
            ).first()
            
            if account:
                service = WhatsAppAPIService(account)
                
                # Envia com botões de avaliação
                service.send_interactive_buttons(
                    to=order.customer_phone,
                    body_text=message,
                    buttons=[
                        {'id': f'rating_5_{order.id}', 'title': '⭐⭐⭐⭐⭐'},
                        {'id': f'rating_3_{order.id}', 'title': '⭐⭐⭐'},
                        {'id': f'rating_1_{order.id}', 'title': '⭐'},
                    ]
                )
                
                logger.info(f"Feedback request sent for order {order_id}")
                
        except AutoMessage.DoesNotExist:
            logger.warning("Feedback template not found")
            
    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found")
    except Exception as e:
        logger.error(f"Error requesting feedback: {str(e)}")


@shared_task
def schedule_feedback_request(order_id: str):
    """Agenda solicitação de feedback para 30 min depois"""
    from celery import current_app
    
    # Agenda para executar em 30 minutos
    current_app.send_task(
        'apps.whatsapp.tasks.automation_tasks.request_feedback',
        args=[order_id],
        countdown=30 * 60  # 30 minutos
    )
    
    logger.info(f"Scheduled feedback request for order {order_id} in 30 minutes")
