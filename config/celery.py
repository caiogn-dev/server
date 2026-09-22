"""
Celery configuration for WhatsApp Business Platform.
"""
import os
import logging
from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

app = Celery('whatsapp_business')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


app.conf.task_routes = {
    'apps.whatsapp.tasks.*': {'queue': 'whatsapp'},
    'apps.agents.tasks.*': {'queue': 'agents'},
    'apps.automation.tasks.*': {'queue': 'automation'},
    'apps.campaigns.tasks.*': {'queue': 'campaigns'},
}

app.conf.beat_schedule = {
    'cleanup-old-webhook-events': {
        'task': 'apps.whatsapp.tasks.cleanup_old_webhook_events',
        'schedule': 3600.0,  # Every hour
    },
    'sync-message-statuses': {
        'task': 'apps.whatsapp.tasks.sync_message_statuses',
        'schedule': 300.0,  # Every 5 minutes
    },
    # Process pending webhook events (fallback for missed events)
    'process-pending-webhook-events': {
        'task': 'apps.whatsapp.tasks.process_pending_webhook_events',
        'schedule': 30.0,  # Every 30 seconds
    },
    # Retry failed webhook events
    'retry-failed-webhook-events': {
        'task': 'apps.whatsapp.tasks.retry_failed_webhook_events',
        'schedule': 300.0,  # Every 5 minutes
    },
    # Automation tasks (WhatsApp sessions)
    # Lembrete de carrinho do bot: `check-abandoned-whatsapp-sessions`, abaixo.
    # Aqui havia 'check-abandoned-carts' apontando para um nome que nenhuma
    # tarefa usa (nunca rodou; saiu em 19/09 — migração stores/0084).
    'check-pending-pix-payments': {
        'task': 'apps.automation.tasks.check_pending_pix_payments',
        'schedule': 600.0,  # Every 10 minutes
    },
    # Reconciliação ativa: consulta o MP p/ pagamentos pendentes da última hora
    # e dispara o fluxo do webhook quando o aviso se perdeu (502 em restart etc.)
    'reconcile-pending-pix-payments': {
        'task': 'apps.stores.tasks.reconcile_pending_pix_payments',
        'schedule': 180.0,  # Every 3 minutes
    },
    # Token de OAuth do lojista vence em ~6 meses. Diária com 7 dias de margem:
    # dá uma semana de tentativas antes de a loja parar de aceitar pagamento.
    'renovar-tokens-oauth-mercadopago': {
        'task': 'apps.stores.tasks.renovar_tokens_oauth_do_mercadopago',
        'schedule': 86400.0,  # Daily
    },
    # REMOVED: check-pending-payments-new + check-abandoned-carts-new were
    # duplicates of the tasks above with different schedules (race condition).
    # Kept only the canonical apps.automation.tasks versions.
    'cleanup-expired-sessions': {
        'task': 'apps.automation.tasks.cleanup_expired_sessions',
        'schedule': 86400.0,  # Daily
    },
    # Scheduled messages
    'process-scheduled-messages': {
        'task': 'apps.automation.tasks.scheduled.process_scheduled_messages',
        'schedule': 60.0,  # Every minute
    },
    # Automated reports
    'process-scheduled-reports': {
        'task': 'apps.automation.tasks.scheduled.process_scheduled_reports',
        'schedule': 3600.0,  # Every hour
    },
    'cleanup-old-reports': {
        'task': 'apps.automation.tasks.scheduled.cleanup_old_reports',
        'schedule': 86400.0,  # Daily
    },
    # Process scheduled email automations
    'process-scheduled-email-automations': {
        'task': 'apps.marketing.tasks.process_scheduled_automations',
        'schedule': 60.0,  # Every minute
    },
    # Campaign tasks
    'check-scheduled-campaigns': {
        'task': 'apps.campaigns.tasks.check_scheduled_campaigns',
        'schedule': 60.0,  # Every minute
    },
    # Instagram token refresh (daily) — renew tokens expiring within 7 days
    'refresh-instagram-tokens': {
        'task': 'apps.instagram.tasks.refresh_instagram_tokens',
        'schedule': 86400.0,  # Daily
    },
    # Cleanup old IntentLog entries (daily at 3 AM)
    'cleanup-intent-logs': {
        'task': 'apps.automation.tasks.scheduled.cleanup_intent_logs',
        'schedule': 86400.0,  # Daily
        'kwargs': {'days_to_keep': 30},
    },
    # NOTE: process_scheduled_messages is now unified in apps.automation.tasks.scheduled
    # The task 'process-scheduled-messages' above handles all scheduled messages

    # StoreCart (storefront) abandoned cart reminders — distinct from CustomerSession carts
    'check-abandoned-store-carts': {
        'task': 'apps.whatsapp.tasks.check_abandoned_store_carts',
        'schedule': 900.0,  # every 15 min
    },
    # CustomerSession (WhatsApp bot) abandoned cart/checkout reminders — 5min / 20min / 2h
    'check-abandoned-whatsapp-sessions': {
        'task': 'apps.whatsapp.tasks.check_abandoned_whatsapp_sessions',
        'schedule': 300.0,  # every 5 min
    },
    # Re-engajamento de clientes inativos (10-30 dias sem pedido) — diário às 11h
    'check-inactive-customers': {
        'task': 'apps.whatsapp.tasks.check_inactive_customers',
        'schedule': crontab(hour=11, minute=0),
    },
    # Lembrete de PIX pendente dos pedidos do SITE — LIGADO pelo dono em
    # 21/09/2026. Manda em 30 min e 2 h, e em 24 h avisa que expirou E
    # CANCELA o pedido (pelo OrderService: devolve estoque, devolve cupom,
    # liquida o pagamento).
    #
    # A entrada anterior apontava para 'apps.whatsapp.tasks.
    # check_pending_payments' — nome que nenhuma tarefa registra. Ficou no
    # agendador sem nunca rodar, porque tarefa inexistente falha calada; saiu
    # em 19/09 (migração stores/0084). O nome certo é o de baixo, e há teste
    # que confere se toda entrada aponta para tarefa que existe.
    'check-store-pix-reminders': {
        'task': 'apps.whatsapp.tasks.automation_tasks.check_pending_payments',
        'schedule': 300.0,  # a cada 5 min — as janelas são de 5 min
    },
    # Toca Delivery — poll active corridas for status updates every 60s
    'sync-toca-delivery-statuses': {
        'task': 'apps.stores.tasks.sync_toca_delivery_statuses',
        'schedule': 60.0,
    },
    # Agent learning — extrai padrões de atendimentos a cada 6h
    'agent-learn-all': {
        'task': 'apps.agents.tasks.learn_all_active_agents',
        'schedule': 21600.0,  # 6h
    },
    # Decay de conhecimento obsoleto — diário
    'agent-decay-stale-knowledge': {
        'task': 'apps.agents.tasks.decay_stale_knowledge',
        'schedule': 86400.0,
    },
    # Cleanup de carrinhos abandonados — diário às 3h
    'cleanup-abandoned-carts': {
        'task': 'apps.stores.tasks.cleanup_abandoned_carts',
        'schedule': 86400.0,  # Daily
    },
    # Database backup — diário às 2h
    'daily-database-backup': {
        'task': 'apps.stores.tasks.daily_database_backup',
        'schedule': crontab(hour=2, minute=0),
    },
    # Database integrity check — a cada 6h
    'database-integrity-check': {
        'task': 'apps.stores.tasks.database_integrity_check',
        'schedule': 21600.0,  # Every 6 hours
    },
    # Billing: ciclo de vida de assinaturas — diário às 4h
    'enforce-subscription-lifecycle': {
        'task': 'stores.enforce_subscription_lifecycle',
        'schedule': crontab(hour=4, minute=0),  # diário 04:00
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery configuration."""
    logger.debug(f'Request: {self.request!r}')
