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

from apps.core.pii import mask_phone

logger = logging.getLogger(__name__)


def _get_store_profile(store):
    """
    Return the CompanyProfile for a Store.

    CompanyProfile uses related_name='automation_profile' on its store FK,
    so store.automation_profile is the correct accessor.
    """
    return getattr(store, 'automation_profile', None)


def _notifications_suppressed(order) -> bool:
    """Pedido de balcão silenciado pelo painel (metadata.suppress_notifications)."""
    metadata = order.metadata if isinstance(order.metadata, dict) else {}
    return bool(metadata.get('suppress_notifications'))


def _get_account_for_profile(profile):
    """Return the first active WhatsAppAccount linked to a CompanyProfile."""
    if profile is None:
        return None
    from apps.whatsapp.models import WhatsAppAccount
    return WhatsAppAccount.objects.filter(company_profile=profile).first()


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
    from django.core.cache import cache

    idempotency_key = f"pix_reminder:{order_id}:{reminder_type}"
    if not cache.add(idempotency_key, 1, timeout=3600):
        logger.info("Duplicate pix_reminder task for order %s type %s — skipped", order_id, reminder_type)
        return

    try:
        order = Order.objects.select_related('store').get(id=order_id)

        if order.payment_status not in ('pending', 'processing'):
            logger.info(f"Order {order_id} payment_status={order.payment_status}, skipping reminder")
            return

        profile = _get_store_profile(order.store)
        if not profile:
            logger.warning(f"No CompanyProfile for store {order.store_id}, skipping payment reminder")
            return

        event_type_map = {
            'first': 'payment_reminder_1',
            'second': 'payment_reminder_2',
            'final': 'payment_expired',
        }
        event_type = event_type_map.get(reminder_type, 'payment_reminder_1')

        try:
            template = AutoMessage.objects.get(
                company=profile,
                event_type=event_type,
                is_active=True
            )

            time_remaining = {'first': '30 minutos', 'second': '2 horas'}.get(reminder_type, 'expirado')

            message = template.render_message({
                'customer_name': order.customer_name,
                'order_number': order.order_number,
                'amount': order.total,
                'pix_code': order.pix_code or 'N/A',
                'time_remaining': time_remaining,
            })

            account = _get_account_for_profile(profile)
            if account:
                service = WhatsAppAPIService(account)
                service.send_text_message(to=order.customer_phone, text=message)
                logger.info("Payment reminder sent to %s for order %s", mask_phone(order.customer_phone), order_id)

                if not order.metadata:
                    order.metadata = {}
                order.metadata[f'payment_reminder_{reminder_type}_sent'] = timezone.now().isoformat()
                order.save(update_fields=['metadata'])

        except AutoMessage.DoesNotExist:
            logger.warning(f"Template {event_type} not found for store {order.store_id}")

    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found")
    except Exception as e:
        logger.error(f"Error sending payment reminder: {str(e)}")
        raise self.retry(exc=e)


@shared_task
def check_pending_payments():
    """
    Verifica pagamentos PIX pendentes e agenda lembretes (StoreOrder).
    Executado a cada 10 minutos.

    Exclui pedidos que já têm CustomerSession com PIX ativo — esses são
    cobertos pelo check_pending_pix_payments do apps.automation.tasks
    (evita lembrete duplicado em pedidos criados pelo WhatsApp bot).
    """
    from apps.stores.models.order import StoreOrder as Order
    from apps.automation.models import CustomerSession

    now = timezone.now()
    # IDs de orders já cobertos pela fila CustomerSession
    whatsapp_order_ids = set(
        CustomerSession.objects.filter(
            order__isnull=False,
            pix_code__gt='',
        ).values_list('order_id', flat=True)
    )
    base_qs = Order.objects.filter(
        payment_status='pending',
        payment_method='pix',
    ).exclude(id__in=whatsapp_order_ids)

    # Lembrete 1: criado há 30-35 min
    first_30 = list(
        base_qs.filter(
            created_at__lte=now - timedelta(minutes=30),
            created_at__gt=now - timedelta(minutes=35),
        ).exclude(metadata__has_key='payment_reminder_first_sent')
        .values_list('id', flat=True)
    )
    for oid in first_30:
        send_payment_reminder.delay(str(oid), 'first')
    if first_30:
        logger.info("Scheduled first PIX reminders for %d orders", len(first_30))

    # Lembrete 2: criado há 2h-2h05
    second_2h = list(
        base_qs.filter(
            created_at__lte=now - timedelta(hours=2),
            created_at__gt=now - timedelta(hours=2, minutes=5),
        ).exclude(metadata__has_key='payment_reminder_second_sent')
        .values_list('id', flat=True)
    )
    for oid in second_2h:
        send_payment_reminder.delay(str(oid), 'second')
    if second_2h:
        logger.info("Scheduled second PIX reminders for %d orders", len(second_2h))

    # Expirado: criado há mais de 24h
    expired = list(
        base_qs.filter(
            created_at__lte=now - timedelta(hours=24),
        ).exclude(metadata__has_key='payment_expired_notified')
        .values_list('id', flat=True)
    )
    for oid in expired:
        send_payment_reminder.delay(str(oid), 'final')
        Order.objects.filter(id=oid).update(
            status='cancelled',
            payment_status='failed',
        )
    if expired:
        logger.info("Cancelled %d PIX-expired orders", len(expired))


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
    from django.core.cache import cache

    idempotency_key = f"cart_reminder:{cart_id}:{reminder_type}"
    if not cache.add(idempotency_key, 1, timeout=3600):
        logger.info("Duplicate cart_reminder task for cart %s type %s — skipped", cart_id, reminder_type)
        return

    try:
        cart = Cart.objects.select_related('store').get(id=cart_id)
        cart_metadata = cart.metadata or {}
        customer_phone = (
            cart_metadata.get('customer_phone')
            or cart_metadata.get('phone_number')
            or getattr(cart.user, 'phone_number', '')
            or getattr(cart.user, 'phone', '')
        )
        customer_name = (
            cart_metadata.get('customer_name')
            or getattr(cart.user, 'name', '')
            or getattr(cart.user, 'first_name', '')
            or 'Cliente'
        )

        if not customer_phone:
            logger.info(f"Cart {cart_id} has no customer phone, skipping reminder")
            return

        if not cart.items.exists():
            logger.info(f"Cart {cart_id} is empty, skipping reminder")
            return

        from apps.stores.models.order import StoreOrder as Order
        recent_order = Order.objects.filter(
            customer_phone=customer_phone,
            created_at__gte=cart.updated_at
        ).first()

        if recent_order:
            logger.info("Customer already placed order, skipping cart reminder")
            return

        profile = _get_store_profile(cart.store)
        if not profile:
            logger.warning(f"No CompanyProfile for store {cart.store_id}, skipping cart reminder")
            return

        event_type_map = {
            '30min': 'cart_reminder_30',
            '2h': 'cart_reminder_2h',
            '24h': 'cart_reminder_24h',
        }
        event_type = event_type_map.get(reminder_type, 'cart_reminder')

        try:
            template = AutoMessage.objects.get(
                company=profile,
                event_type=event_type,
                is_active=True
            )

            items_summary = "\n".join([
                f"• {item.product.name} x{item.quantity} = R$ {item.total}"
                for item in cart.items.all()[:5]
            ])

            message = template.render_message({
                'customer_name': customer_name,
                'cart_items': items_summary,
                'cart_total': cart.total,
                'cart_item_count': cart.items.count(),
            })

            account = _get_account_for_profile(profile)
            if account:
                service = WhatsAppAPIService(account)
                service.send_interactive_buttons(
                    to=customer_phone,
                    body_text=message,
                    buttons=[
                        {'id': f'checkout_{cart.id}', 'title': '✅ Finalizar Pedido'},
                        {'id': f'view_cart_{cart.id}', 'title': '🛒 Ver Carrinho'},
                    ]
                )
                logger.info("Cart reminder sent to %s for cart %s", mask_phone(customer_phone), cart_id)

        except AutoMessage.DoesNotExist:
            logger.warning(f"Template {event_type} not found for store {cart.store_id}")

    except Cart.DoesNotExist:
        logger.error(f"Cart {cart_id} not found")
    except Exception as e:
        logger.error(f"Error sending cart reminder: {str(e)}")
        raise self.retry(exc=e)


@shared_task(name='apps.whatsapp.tasks.check_abandoned_store_carts')
def check_abandoned_carts():
    """
    Verifica carrinhos abandonados (StoreCart)
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
        cart.save(update_fields=['metadata'])

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
        cart.save(update_fields=['metadata'])

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
        cart.save(update_fields=['metadata'])

    logger.info(
        f"Checked abandoned carts: {abandoned_30min.count()} (30min), "
        f"{abandoned_2h.count()} (2h), {abandoned_24h.count()} (24h)"
    )


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
    from django.core.cache import cache

    # Atomic idempotency: cache.add returns False if key already exists
    idempotency_key = f"order_notify:{order_id}:{new_status}"
    if not cache.add(idempotency_key, 1, timeout=3600):
        logger.info("Skipping duplicate notification for order %s status %s", order_id, new_status)
        return

    try:
        order = Order.objects.select_related('store').get(id=order_id)

        if _notifications_suppressed(order):
            logger.info("Order %s has suppress_notifications — skipping status notification", order_id)
            return

        status_to_event = {
            'received': 'order_received',
            'processing': 'order_processing',
            'confirmed': 'order_confirmed',
            'paid': 'order_paid',
            'preparing': 'order_preparing',
            'ready': 'order_ready',
            'shipped': 'order_shipped',
            'out_for_delivery': 'order_out_for_delivery',
            'delivered': 'order_delivered',
            'completed': 'order_completed',
            'cancelled': 'order_cancelled',
            'refunded': 'order_refunded',
        }

        event_type = status_to_event.get(new_status)
        if not event_type:
            logger.debug(f"No notification template mapped for status: {new_status}")
            return

        profile = _get_store_profile(order.store)
        if not profile:
            logger.warning(f"No CompanyProfile for store {order.store_id}, skipping status notification")
            return

        # Toggle geral do painel (CompanyProfileDetail): desligado → silêncio
        # para a loja inteira, template e fallback.
        if not profile.order_status_notification_enabled:
            logger.info(
                "Store %s has order_status_notification_enabled=False — skipping status notification",
                order.store_id,
            )
            return

        try:
            template = AutoMessage.objects.get(
                company=profile,
                event_type=event_type,
                is_active=True
            )

            status_display = {
                'received': '📬 Recebido',
                'processing': '⏳ Em Processamento',
                'confirmed': '✅ Confirmado',
                'paid': '💰 Pagamento Confirmado',
                'preparing': '👨‍🍳 Em preparo',
                'ready': '✨ Pronto',
                'shipped': '🚚 Enviado',
                'out_for_delivery': '🛵 Saiu para entrega',
                'delivered': '📦 Entregue',
                'completed': '✨ Finalizado',
                'cancelled': '❌ Cancelado',
                'refunded': '💳 Reembolsado',
            }.get(new_status, new_status)

            message = template.render_message({
                'customer_name': order.customer_name,
                'order_number': order.order_number,
                'order_status': status_display,
                'order_total': order.total,
            })

            account = _get_account_for_profile(profile)
            if account:
                from apps.whatsapp.services.message_service import MessageService
                MessageService().send_text_message(
                    account_id=str(account.id),
                    to=order.customer_phone,
                    text=message,
                )
                logger.info(f"Status notification sent for order {order_id}: {new_status}")

        except AutoMessage.DoesNotExist:
            # No AutoMessage template configured — fall back to the model's built-in
            # notification (hardcoded defaults + optional store.metadata overrides).
            # This preserves backward compatibility for stores that haven't set up templates.
            logger.debug(f"No active template for event '{event_type}' on store {order.store_id}, using direct fallback")
            order._trigger_status_whatsapp_notification(new_status)

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
        order = Order.objects.select_related('store').get(id=order_id)

        if order.status != 'delivered':
            logger.info(f"Order {order_id} not delivered, skipping feedback request")
            return

        if _notifications_suppressed(order):
            logger.info("Order %s has suppress_notifications — skipping feedback request", order_id)
            return

        profile = _get_store_profile(order.store)
        if not profile:
            logger.warning(f"No CompanyProfile for store {order.store_id}, skipping feedback request")
            return

        try:
            template = AutoMessage.objects.get(
                company=profile,
                event_type='feedback_request',
                is_active=True
            )

            message = template.render_message({
                'customer_name': order.customer_name,
                'order_number': order.order_number,
            })

            account = _get_account_for_profile(profile)
            if account:
                service = WhatsAppAPIService(account)
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
            logger.debug(f"No feedback_request template for store {order.store_id}")

    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found")
    except Exception as e:
        logger.error(f"Error requesting feedback: {str(e)}")


@shared_task
def schedule_feedback_request(order_id: str):
    """Agenda solicitação de feedback para 30 min depois"""
    from celery import current_app

    current_app.send_task(
        'apps.whatsapp.tasks.automation_tasks.request_feedback',
        args=[order_id],
        countdown=30 * 60  # 30 minutos
    )

    logger.info(f"Scheduled feedback request for order {order_id} in 30 minutes")


@shared_task(bind=True, max_retries=2)
def send_session_cart_reminder(self, session_id: str, reminder_type: str):
    """
    Envia lembrete de carrinho abandonado para CustomerSessions criadas pelo bot WhatsApp.
    Diferente de send_cart_reminder que usa StoreCart do site.
    """
    from apps.automation.models import CustomerSession
    from django.core.cache import cache

    idempotency_key = f"session_reminder:{session_id}:{reminder_type}"
    if not cache.add(idempotency_key, 1, timeout=3600):
        logger.info("Duplicate session_reminder for session %s type %s — skipped", session_id, reminder_type)
        return

    try:
        session = CustomerSession.objects.select_related('company').get(id=session_id)

        if session.status not in ('active', 'cart_created', 'checkout'):
            logger.info("Session %s status=%s — skipping reminder", session_id, session.status)
            return

        notification_key = f'session_cart_reminder_{reminder_type}'
        if session.was_notification_sent(notification_key):
            return

        phone_number = session.phone_number
        if not phone_number:
            return

        account = _get_account_for_profile(session.company)
        if not account:
            logger.warning("No WhatsApp account for company %s", session.company_id)
            return

        first_name = (session.customer_name or '').split()[0] or 'você'

        if reminder_type == '5min':
            body = (
                f"Oi, {first_name}! 👋 Parece que você estava finalizando um pedido.\n\n"
                f"Ainda quer continuar? Estou aqui pra ajudar! 😊"
            )
        elif reminder_type == '20min':
            body = (
                f"Oi, {first_name}! 👋 Você deixou itens no carrinho.\n\n"
                f"Quer continuar seu pedido? 😊"
            )
        else:
            body = (
                f"Ei, {first_name}! 🥗 Seu carrinho ainda está te esperando.\n\n"
                f"Posso te ajudar a finalizar o pedido?"
            )

        from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService
        WhatsAppAPIService(account).send_interactive_buttons(
            to=phone_number,
            body_text=body,
            buttons=[
                {'id': 'continue_checkout', 'title': '✅ Continuar Pedido'},
                {'id': 'view_menu', 'title': '📋 Ver Cardápio'},
            ],
        )
        session.add_notification(notification_key)
        logger.info("Session cart reminder (%s) sent to %s", reminder_type, mask_phone(phone_number))

    except CustomerSession.DoesNotExist:
        logger.error("CustomerSession %s not found", session_id)
    except Exception as exc:
        logger.error("Error sending session cart reminder: %s", exc)
        raise self.retry(exc=exc)


@shared_task(name='apps.whatsapp.tasks.check_abandoned_whatsapp_sessions')
def check_abandoned_whatsapp_sessions():
    """
    Verifica CustomerSessions WhatsApp com carrinho/checkout abandonado.
    Executado a cada 5 minutos via Celery Beat.

    Buckets:
    - checkout 5min  → exit intent urgente (estava na hora de pagar)
    - cart   20min  → primeiro lembrete de carrinho
    - any     2h    → segundo lembrete
    """
    from apps.automation.models import CustomerSession

    now = timezone.now()

    # 5 minutos idle em checkout → exit intent (maior urgência)
    exit_intent = CustomerSession.objects.filter(
        status='checkout',
        last_activity_at__lte=now - timedelta(minutes=5),
        last_activity_at__gt=now - timedelta(minutes=10),
        cart_items_count__gt=0,
    ).exclude(
        notifications_sent__contains=[{'type': 'session_cart_reminder_5min'}]
    )

    count_5 = 0
    for session in exit_intent:
        send_session_cart_reminder.delay(str(session.id), '5min')
        count_5 += 1

    # 20 minutos idle → primeiro lembrete de carrinho
    idle_20min = CustomerSession.objects.filter(
        status__in=['active', 'cart_created', 'checkout'],
        last_activity_at__lte=now - timedelta(minutes=20),
        last_activity_at__gt=now - timedelta(minutes=25),
        cart_items_count__gt=0,
    ).exclude(
        notifications_sent__contains=[{'type': 'session_cart_reminder_20min'}]
    )

    count_20 = 0
    for session in idle_20min:
        send_session_cart_reminder.delay(str(session.id), '20min')
        count_20 += 1

    # 2 horas idle → segundo lembrete
    idle_2h = CustomerSession.objects.filter(
        status__in=['active', 'cart_created', 'checkout'],
        last_activity_at__lte=now - timedelta(hours=2),
        last_activity_at__gt=now - timedelta(hours=2, minutes=5),
        cart_items_count__gt=0,
    ).exclude(
        notifications_sent__contains=[{'type': 'session_cart_reminder_2h'}]
    )

    count_2h = 0
    for session in idle_2h:
        send_session_cart_reminder.delay(str(session.id), '2h')
        count_2h += 1

    logger.info(
        "Checked abandoned WhatsApp sessions: %d (5min checkout), %d (20min), %d (2h)",
        count_5, count_20, count_2h,
    )


def _reengagement_content(store, profile):
    """Corpo e botões do re-engajamento por loja.

    O texto cita um produto real da loja (destaque primeiro) em vez do
    antigo "que tal uma salada" fixo; o segundo botão vem de
    settings['bot_cta'] (mesmo CTA custom usado nos handlers do bot).
    """
    from apps.stores.models import StoreProduct

    product_name = (
        StoreProduct.objects
        .filter(store=store, is_active=True, status='active')
        .order_by('-featured', 'sort_order', '-created_at')
        .values_list('name', flat=True)
        .first()
    )
    if product_name:
        body = (
            f"Sentimos sua falta aqui na {store.name}! 😊\n\n"
            f"Que tal pedir {product_name} hoje? "
            f"Temos novidades no cardápio esperando por você."
        )
    else:
        body = (
            f"Sentimos sua falta aqui na {store.name}! 😊\n\n"
            f"Temos novidades no cardápio esperando por você."
        )

    buttons = [{'id': 'view_menu', 'title': '📋 Ver Cardápio'}]
    settings_data = getattr(profile, 'settings', None) or {}
    cta = settings_data.get('bot_cta') or {}
    if cta.get('id') and cta.get('title'):
        buttons.append({'id': str(cta['id']), 'title': str(cta['title'])[:20]})
    return body, buttons


@shared_task(bind=True, max_retries=2)
def send_reengagement_message(self, phone_number: str, store_id: str):
    """
    Envia mensagem de re-engajamento para clientes inativos (10-30 dias sem pedido).
    """
    from apps.stores.models import Store
    from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService
    from django.core.cache import cache

    idempotency_key = f"reengagement:{store_id}:{phone_number}"
    if not cache.add(idempotency_key, 1, timeout=86400):  # 24h
        return

    try:
        store = Store.objects.get(id=store_id)
        profile = _get_store_profile(store)
        if not profile:
            return
        account = _get_account_for_profile(profile)
        if not account:
            return

        body_text, buttons = _reengagement_content(store, profile)
        WhatsAppAPIService(account).send_interactive_buttons(
            to=phone_number,
            body_text=body_text,
            buttons=buttons,
        )
        logger.info("Re-engagement sent to %s for store %s", mask_phone(phone_number), store_id)

    except Store.DoesNotExist:
        logger.error("Store %s not found for re-engagement", store_id)
    except Exception as exc:
        logger.error("Error sending re-engagement: %s", exc)
        raise self.retry(exc=exc)


@shared_task(name='apps.whatsapp.tasks.check_inactive_customers')
def check_inactive_customers():
    """
    Identifica clientes com pedido entre 10 e 30 dias atrás (sem pedido nos últimos 10 dias)
    e dispara re-engajamento. Executado diariamente às 11h.
    """
    from apps.stores.models import StoreOrder

    now = timezone.now()
    window_start = now - timedelta(days=30)
    window_end = now - timedelta(days=10)

    # Clientes que tiveram pedido confirmado há 10-30 dias
    recent_orders = (
        StoreOrder.objects
        .filter(
            created_at__gte=window_start,
            created_at__lte=window_end,
            status__in=['delivered', 'completed', 'paid', 'confirmed'],
        )
        .values('customer_phone', 'store_id')
        .distinct()
    )

    # Filtra quem voltou a pedir nos últimos 10 dias (não precisa de re-engajamento)
    active_phones = set(
        StoreOrder.objects
        .filter(created_at__gte=window_end)
        .values_list('customer_phone', flat=True)
        .distinct()
    )

    count = 0
    seen = set()
    for row in recent_orders:
        phone = row['customer_phone']
        store_id = str(row['store_id'])
        key = (phone, store_id)
        if not phone or key in seen or phone in active_phones:
            continue
        seen.add(key)
        send_reengagement_message.delay(phone, store_id)
        count += 1

    logger.info("Re-engagement: %d customers targeted", count)
