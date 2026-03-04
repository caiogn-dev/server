""" Celery tasks para marketing_v2 - Automação. """
from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3)
def process_scheduled_messages(self):
    """Verificar e enviar mensagens agendadas para o momento."""
    from .models import ScheduledMessage
    from apps.messaging_v2.tasks import send_whatsapp_message
    from apps.messaging_v2.models import Conversation, UnifiedMessage

    now = timezone.now()
    pending = ScheduledMessage.objects.filter(
        status=ScheduledMessage.Status.PENDING,
        scheduled_at__lte=now
    )

    sent_count = 0
    for scheduled in pending:
        try:
            # Criar conversa e mensagem
            conversation, _ = Conversation.objects.get_or_create(
                customer_phone=scheduled.recipient,
                defaults={
                    'platform': scheduled.channel,
                    'store': scheduled.store
                }
            )
            message = UnifiedMessage.objects.create(
                conversation=conversation,
                direction=UnifiedMessage.Direction.OUTBOUND,
                text=scheduled.content.get('text', '')
            )
            # Enviar
            send_whatsapp_message.delay(str(message.id))

            scheduled.status = ScheduledMessage.Status.SENT
            scheduled.sent_at = now
            scheduled.save(update_fields=['status', 'sent_at'])
            sent_count += 1
        except Exception as e:
            scheduled.status = ScheduledMessage.Status.FAILED
            scheduled.error_message = str(e)
            scheduled.save(update_fields=['status', 'error_message'])

    return {'sent': sent_count}


@shared_task(bind=True, max_retries=3)
def execute_automation(self, automation_id, trigger_data):
    """Executar automação baseada em trigger."""
    from .models import Automation
    from apps.messaging_v2.tasks import send_whatsapp_message
    from apps.messaging_v2.models import Conversation, UnifiedMessage

    try:
        automation = Automation.objects.get(id=automation_id)
        if not automation.is_active:
            return {'error': 'Automation not active'}

        # Executar ações da automação
        for action in automation.actions:
            action_type = action.get('type')
            if action_type == 'send_message':
                phone = trigger_data.get('phone')
                if phone:
                    conversation, _ = Conversation.objects.get_or_create(
                        customer_phone=phone,
                        defaults={
                            'platform': 'whatsapp',
                            'store': automation.store
                        }
                    )
                    message = UnifiedMessage.objects.create(
                        conversation=conversation,
                        direction=UnifiedMessage.Direction.OUTBOUND,
                        text=action.get('message', '')
                    )
                    send_whatsapp_message.delay(str(message.id))

        return {'executed': True, 'automation_id': str(automation_id)}
    except Exception as e:
        raise self.retry(exc=e)
