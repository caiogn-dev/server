"""
Migration script to migrate data from old apps to new consolidated apps.

Run this after creating the new tables:
    python manage.py migrate
    python manage.py shell < migrate_to_v2.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
sys.path.insert(0, '/app')
django.setup()

from django.db import transaction
from django.utils import timezone
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_campaigns():
    """Migrate campaigns from old apps to marketing_v2."""
    from apps.campaigns.models import Campaign as OldCampaign
    from apps.marketing.models import EmailCampaign
    from apps.marketing_v2.models import Campaign as NewCampaign
    
    logger.info("Starting campaign migration...")
    
    # Migrate WhatsApp campaigns
    for old in OldCampaign.objects.all():
        try:
            NewCampaign.objects.get_or_create(
                id=old.id,
                defaults={
                    'name': old.name,
                    'description': old.description,
                    'channel': 'whatsapp',
                    'campaign_type': old.campaign_type.lower() if old.campaign_type else 'broadcast',
                    'store_id': old.account_id,  # Assuming account maps to store
                    'content': {
                        'template_name': old.template.name if old.template else None,
                        'template_language': old.template.language if old.template else 'pt_BR',
                    },
                    'status': old.status.lower() if old.status else 'draft',
                    'scheduled_at': old.scheduled_at,
                    'total_recipients': old.total_recipients,
                    'sent_count': old.messages_sent,
                    'delivered_count': old.messages_delivered,
                    'read_count': old.messages_read,
                    'failed_count': old.messages_failed,
                    'created_at': old.created_at,
                    'updated_at': old.updated_at,
                }
            )
        except Exception as e:
            logger.error(f"Failed to migrate campaign {old.id}: {e}")
    
    # Migrate Email campaigns
    for old in EmailCampaign.objects.all():
        try:
            NewCampaign.objects.get_or_create(
                id=old.id,
                defaults={
                    'name': old.name,
                    'description': old.description,
                    'channel': 'email',
                    'campaign_type': old.campaign_type.lower() if hasattr(old, 'campaign_type') else 'broadcast',
                    'store': old.store,
                    'content': {
                        'subject': old.subject,
                        'html': old.html_content,
                        'text': old.text_content,
                        'preview_text': getattr(old, 'preview_text', ''),
                    },
                    'from_name': getattr(old, 'from_name', ''),
                    'from_email': getattr(old, 'from_email', ''),
                    'reply_to': getattr(old, 'reply_to', ''),
                    'status': old.status.lower() if old.status else 'draft',
                    'scheduled_at': old.scheduled_at,
                    'total_recipients': old.total_recipients,
                    'sent_count': old.emails_sent,
                    'delivered_count': old.emails_delivered,
                    'opened_count': old.emails_opened,
                    'clicked_count': old.emails_clicked,
                    'created_at': old.created_at,
                    'updated_at': old.updated_at,
                }
            )
        except Exception as e:
            logger.error(f"Failed to migrate email campaign {old.id}: {e}")
    
    logger.info("Campaign migration completed!")


def migrate_scheduled_messages():
    """Migrate scheduled messages."""
    from apps.automation.models import ScheduledMessage as OldScheduled
    from apps.marketing_v2.models import ScheduledMessage as NewScheduled
    
    logger.info("Starting scheduled messages migration...")
    
    for old in OldScheduled.objects.all():
        try:
            NewScheduled.objects.get_or_create(
                id=old.id,
                defaults={
                    'recipient': old.to_number,
                    'channel': 'whatsapp' if old.account else 'email',
                    'content': {
                        'text': old.message_text,
                        'template_name': old.template_name,
                        'template_language': old.template_language,
                        'template_components': old.template_components,
                        'media_url': old.media_url,
                        'buttons': old.buttons,
                    },
                    'scheduled_at': old.scheduled_at,
                    'status': old.status.lower() if old.status else 'pending',
                    'sent_at': old.sent_at,
                    'external_id': old.whatsapp_message_id,
                    'error_message': old.error_message,
                    'created_at': old.created_at,
                    'updated_at': old.updated_at,
                }
            )
        except Exception as e:
            logger.error(f"Failed to migrate scheduled message {old.id}: {e}")
    
    logger.info("Scheduled messages migration completed!")


def migrate_templates():
    """Migrate message templates."""
    from apps.whatsapp.models import MessageTemplate as OldTemplate
    from apps.marketing.models import EmailTemplate
    from apps.marketing_v2.models import Template as NewTemplate
    
    logger.info("Starting template migration...")
    
    # Migrate WhatsApp templates
    for old in OldTemplate.objects.all():
        try:
            NewTemplate.objects.get_or_create(
                id=old.id,
                defaults={
                    'name': old.name,
                    'channel': 'whatsapp',
                    'content': {
                        'template_id': old.template_id,
                        'language': old.language,
                        'category': old.category,
                        'components': old.components,
                    },
                    'whatsapp_template_name': old.name,
                    'whatsapp_status': old.status.lower() if old.status else 'pending',
                    'store_id': old.account_id,
                    'created_at': old.created_at,
                    'updated_at': old.updated_at,
                }
            )
        except Exception as e:
            logger.error(f"Failed to migrate WhatsApp template {old.id}: {e}")
    
    # Migrate Email templates
    for old in EmailTemplate.objects.all():
        try:
            NewTemplate.objects.get_or_create(
                id=old.id,
                defaults={
                    'name': old.name,
                    'channel': 'email',
                    'template_type': old.template_type.lower() if old.template_type else 'custom',
                    'content': {
                        'subject': old.subject,
                        'html': old.html_content,
                        'text': old.text_content,
                        'preview_text': getattr(old, 'preview_text', ''),
                    },
                    'variables': old.variables,
                    'store': old.store,
                    'created_at': old.created_at,
                    'updated_at': old.updated_at,
                }
            )
        except Exception as e:
            logger.error(f"Failed to migrate email template {old.id}: {e}")
    
    logger.info("Template migration completed!")


def run_all_migrations():
    """Run all migration functions."""
    logger.info("=" * 60)
    logger.info("STARTING DATA MIGRATION TO V2")
    logger.info("=" * 60)
    
    try:
        with transaction.atomic():
            migrate_templates()
            migrate_campaigns()
            migrate_scheduled_messages()
            
        logger.info("=" * 60)
        logger.info("MIGRATION COMPLETED SUCCESSFULLY!")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == '__main__':
    run_all_migrations()
