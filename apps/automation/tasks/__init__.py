"""
Celery tasks for automation.

Canonical task locations:
- Mensagens agendadas / relatórios: apps.automation.tasks.scheduled
- Carrinho abandonado / PIX / sessões: este módulo (tasks/__init__.py)

unified_messaging_tasks.py foi DEPRECADO — não importar dali.
"""
import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

# Canonical scheduled-message and report tasks
from .scheduled import (
    send_scheduled_message,
    process_scheduled_messages,
    generate_report,
    process_scheduled_reports,
    cleanup_old_reports,
    cleanup_intent_logs,
)

logger = logging.getLogger(__name__)

__all__ = [
    # Notificações proativas
    'send_abandoned_cart_notification',
    'send_pix_reminder',
    # Tasks periódicas canônicas
    'check_abandoned_carts',
    'check_pending_pix_payments',
    'cleanup_expired_sessions',
    # Processamento de mensagem entrante (legado)
    'process_incoming_message',
    # Mensagens agendadas / relatórios (re-export de scheduled.py)
    'send_scheduled_message',
    'process_scheduled_messages',
    'generate_report',
    'process_scheduled_reports',
    'cleanup_old_reports',
    'cleanup_intent_logs',
]


@shared_task(bind=True, max_retries=3)
def send_abandoned_cart_notification(self, session_id: str):
    """Send abandoned cart notification.

    DELEGATOR: notificação enviada via AutomationService._send_notification(),
    que é o canal canônico para mensagens proativas (não passa pelo pipeline de
    resposta a mensagens entrantes do UnifiedService).
    """
    logger.warning(
        '[LEGACY] send_abandoned_cart_notification fired — delegating to AutomationService._send_notification. '
        'Caller should be updated.'
    )
    from ..models import CustomerSession, AutoMessage
    from ..services import AutomationService

    try:
        session = CustomerSession.objects.select_related('company').get(
            id=session_id,
            is_active=True
        )

        # Check if session is still abandoned (not completed)
        if session.status not in [
            CustomerSession.SessionStatus.CART_CREATED,
            CustomerSession.SessionStatus.CART_ABANDONED
        ]:
            logger.info(f"Session {session_id} no longer abandoned, skipping notification")
            return

        # Check if notification was already sent
        if session.was_notification_sent(AutoMessage.EventType.CART_ABANDONED):
            logger.info(f"Abandoned cart notification already sent for session {session_id}")
            return

        service = AutomationService()
        service._send_notification(
            session.company,
            session,
            AutoMessage.EventType.CART_ABANDONED,
            {}
        )

        logger.info(f"Abandoned cart notification sent for session {session_id}")

    except CustomerSession.DoesNotExist:
        logger.warning(f"Session not found: {session_id}")
    except Exception as e:
        logger.error(f"Error sending abandoned cart notification: {str(e)}")
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_pix_reminder(self, session_id: str):
    """Send PIX payment reminder.

    DELEGATOR: notificação enviada via AutomationService._send_notification(),
    que é o canal canônico para mensagens proativas (não passa pelo pipeline de
    resposta a mensagens entrantes do UnifiedService).
    """
    logger.warning(
        '[LEGACY] send_pix_reminder fired — delegating to AutomationService._send_notification. '
        'Caller should be updated.'
    )
    from ..models import CustomerSession, AutoMessage
    from ..services import AutomationService

    try:
        session = CustomerSession.objects.select_related('company').get(
            id=session_id,
            is_active=True
        )

        # Check if payment is still pending
        if session.status != CustomerSession.SessionStatus.PAYMENT_PENDING:
            logger.info(f"Session {session_id} no longer pending payment")
            return

        # Check if PIX expired
        if session.pix_expires_at and session.pix_expires_at < timezone.now():
            # Send expired notification instead
            service = AutomationService()
            service._send_notification(
                session.company,
                session,
                AutoMessage.EventType.PIX_EXPIRED,
                {}
            )
            return

        # Check if reminder was already sent
        if session.was_notification_sent(AutoMessage.EventType.PIX_REMINDER):
            return

        service = AutomationService()
        service._send_notification(
            session.company,
            session,
            AutoMessage.EventType.PIX_REMINDER,
            {
                'amount': str(session.cart_total),
            }
        )

        logger.info(f"PIX reminder sent for session {session_id}")

    except CustomerSession.DoesNotExist:
        logger.warning(f"Session not found: {session_id}")
    except Exception as e:
        logger.error(f"Error sending PIX reminder: {str(e)}")
        raise self.retry(exc=e, countdown=60)


@shared_task
def check_abandoned_carts():
    """
    Periodic task to check for abandoned carts.
    Run every 5 minutes.
    """
    from ..models import CustomerSession, CompanyProfile
    
    # Find sessions with carts created more than X minutes ago
    # that haven't progressed to checkout
    
    profiles = CompanyProfile.objects.filter(
        is_active=True,
        abandoned_cart_notification=True
    )
    
    for profile in profiles:
        threshold = timezone.now() - timedelta(minutes=profile.abandoned_cart_delay_minutes)
        
        abandoned_sessions = CustomerSession.objects.filter(
            company=profile,
            status=CustomerSession.SessionStatus.CART_CREATED,
            cart_created_at__lt=threshold,
            is_active=True
        )
        
        for session in abandoned_sessions:
            if not session.was_notification_sent('cart_abandoned'):
                send_abandoned_cart_notification.delay(str(session.id))
                session.status = CustomerSession.SessionStatus.CART_ABANDONED
                session.save(update_fields=['status'])


@shared_task
def check_pending_pix_payments():
    """
    Periodic task to check for pending PIX payments.
    Run every 10 minutes.
    """
    from ..models import CustomerSession
    
    # Find sessions with pending PIX that are about to expire
    threshold = timezone.now() + timedelta(minutes=30)
    
    pending_sessions = CustomerSession.objects.filter(
        status=CustomerSession.SessionStatus.PAYMENT_PENDING,
        pix_expires_at__lt=threshold,
        pix_expires_at__gt=timezone.now(),
        is_active=True
    )
    
    for session in pending_sessions:
        if not session.was_notification_sent('pix_reminder'):
            send_pix_reminder.delay(str(session.id))


@shared_task
def cleanup_expired_sessions():
    """
    Periodic task to cleanup expired sessions.
    Run daily.
    """
    from ..models import CustomerSession
    
    # Mark old inactive sessions as expired
    threshold = timezone.now() - timedelta(days=7)
    
    CustomerSession.objects.filter(
        last_activity_at__lt=threshold,
        status__in=[
            CustomerSession.SessionStatus.ACTIVE,
            CustomerSession.SessionStatus.CART_CREATED,
            CustomerSession.SessionStatus.CART_ABANDONED,
        ]
    ).update(status=CustomerSession.SessionStatus.EXPIRED)


@shared_task(bind=True, max_retries=3)
def process_incoming_message(self, account_id: str, from_number: str, message_text: str, message_type: str = 'text', message_data: dict = None):
    """Process incoming message and send auto-response.

    DELEGATOR: roteado para UnifiedService que é o pipeline canônico de resposta
    a mensagens entrantes. AutomationService.handle_incoming_message() foi
    substituído por este caminho.

    # TODO P5: remover esta task assim que todos os callers forem migrados para
    #          chamar o webhook/UnifiedService diretamente (sem passar por Celery).
    """
    logger.warning(
        '[LEGACY] process_incoming_message fired — delegating to UnifiedService. '
        'Caller should be updated.'
    )
    try:
        from apps.whatsapp.models import WhatsAppAccount
        from apps.conversations.models import Conversation
        from apps.automation.services.context_service import AutomationContextService
        from apps.automation.services.unified_service import UnifiedService

        try:
            account = WhatsAppAccount.objects.get(id=account_id, is_active=True)
        except WhatsAppAccount.DoesNotExist:
            logger.warning('[LEGACY] process_incoming_message: account %s not found, aborting.', account_id)
            return None

        conversation = Conversation.objects.filter(
            account=account,
            phone_number=from_number,
        ).order_by('-updated_at').first()

        if not conversation:
            logger.warning(
                '[LEGACY] process_incoming_message: no conversation found for %s — cannot delegate to UnifiedService.',
                from_number,
            )
            return None

        interactive_reply = None
        if message_type == 'interactive' and message_data:
            button_reply = message_data.get('button_reply') or {}
            list_reply = message_data.get('list_reply') or {}
            reply = button_reply or list_reply
            if reply:
                interactive_reply = {
                    'type': 'button' if button_reply else 'list',
                    'id': reply.get('id', ''),
                    'title': reply.get('title', ''),
                }

        service = UnifiedService(account=account, conversation=conversation)
        response = service.process_message(
            message_text=message_text or '',
            interactive_reply=interactive_reply,
        )

        if response:
            from apps.whatsapp.services.message_service import MessageService
            MessageService().send_text_message(
                account_id=str(account.id),
                to=from_number,
                text=response.content,
                metadata={'source': 'legacy_process_incoming_message_delegator'},
            )
            logger.info('[LEGACY] process_incoming_message: delegated response sent to %s', from_number)
            return response.content

        return None

    except Exception as e:
        logger.error(f"Error in process_incoming_message delegator: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=30)
