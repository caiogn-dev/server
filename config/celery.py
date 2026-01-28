"""
Celery configuration for WhatsApp Business Platform.
"""
import os
import logging
from celery import Celery

logger = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('whatsapp_business')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.task_routes = {
    'apps.whatsapp.tasks.*': {'queue': 'whatsapp'},
    'apps.orders.tasks.*': {'queue': 'orders'},
    'apps.payments.tasks.*': {'queue': 'payments'},
    'apps.langflow.tasks.*': {'queue': 'langflow'},
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
    'check-pending-orders': {
        'task': 'apps.orders.tasks.check_pending_orders',
        'schedule': 600.0,
    },
    # Store cart abandoned (email notifications)
    'check-store-abandoned-carts': {
        'task': 'apps.orders.tasks.check_store_abandoned_carts',
        'schedule': 300.0,  # Every 5 minutes
    },
    # Automation tasks (WhatsApp sessions)
    'check-abandoned-carts': {
        'task': 'apps.automation.tasks.check_abandoned_carts',
        'schedule': 300.0,  # Every 5 minutes
    },
    'check-pending-pix-payments': {
        'task': 'apps.automation.tasks.check_pending_pix_payments',
        'schedule': 600.0,  # Every 10 minutes
    },
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
    'process-campaign-scheduled-messages': {
        'task': 'apps.campaigns.tasks.process_scheduled_messages',
        'schedule': 60.0,  # Every minute
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery configuration."""
    logger.debug(f'Request: {self.request!r}')
