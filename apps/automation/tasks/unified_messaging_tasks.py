"""
Unified Celery Tasks for Messaging

This module consolidates all messaging-related Celery tasks.
Replaces separate tasks from campaigns, automation, and whatsapp apps.
"""

import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_scheduled_messages(self, batch_size=100):
    """
    Process all due scheduled messages.
    This is the unified task that replaces:
    - campaigns.tasks.process_campaign
    - automation.tasks.process_scheduled_messages
    - whatsapp.tasks (any scheduled message tasks)
    
    Args:
        batch_size: Maximum number of messages to process per run
        
    Returns:
        Dict with processing results
    """
    from apps.automation.services import UnifiedMessagingService
    
    try:
        results = UnifiedMessagingService.process_due_messages(batch_size=batch_size)
        logger.info(f"Processed scheduled messages: {results}")
        return results
    except Exception as exc:
        logger.error(f"Error processing scheduled messages: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def process_campaign_batch(campaign_id: str, batch_size: int = 100):
    """
    Process a batch of campaign recipients.
    
    Args:
        campaign_id: Campaign ID to process
        batch_size: Number of recipients to process
        
    Returns:
        Dict with processing results
    """
    from apps.campaigns.services import CampaignService
    
    service = CampaignService()
    try:
        result = service.process_campaign_batch(campaign_id, batch_size)
        
        # If there are more pending recipients, queue another batch
        if result['remaining'] > 0:
            process_campaign_batch.delay(campaign_id, batch_size)
        
        return result
    except Exception as e:
        logger.error(f"Error processing campaign {campaign_id}: {e}")
        raise


@shared_task
def schedule_campaign_messages(campaign_id: str):
    """
    Schedule all messages for a campaign using the unified service.
    
    Args:
        campaign_id: Campaign ID
        
    Returns:
        Number of messages scheduled
    """
    from apps.campaigns.services import CampaignService
    
    service = CampaignService()
    try:
        count = service.schedule_campaign_messages(campaign_id)
        return {'campaign_id': campaign_id, 'scheduled_count': count}
    except Exception as e:
        logger.error(f"Error scheduling campaign {campaign_id}: {e}")
        raise


@shared_task
def cleanup_old_scheduled_messages(days: int = 30):
    """
    Clean up old sent/failed scheduled messages.
    
    Args:
        days: Age in days of messages to clean up
    """
    from datetime import timedelta
    from apps.automation.models import ScheduledMessage
    
    cutoff_date = timezone.now() - timedelta(days=days)
    
    old_messages = ScheduledMessage.objects.filter(
        scheduled_at__lt=cutoff_date,
        status__in=[ScheduledMessage.Status.SENT, ScheduledMessage.Status.FAILED]
    )
    
    count = old_messages.count()
    old_messages.delete()
    
    logger.info(f"Cleaned up {count} old scheduled messages")
    return {'deleted_count': count}


@shared_task
def update_campaign_stats():
    """
    Update campaign statistics.
    Runs periodically to ensure stats are accurate.
    """
    from apps.campaigns.models import Campaign
    
    updated = 0
    campaigns = Campaign.objects.filter(
        status__in=[Campaign.CampaignStatus.RUNNING, Campaign.CampaignStatus.COMPLETED]
    )
    
    for campaign in campaigns:
        try:
            # Recalculate stats from recipients
            stats = campaign.recipients.aggregate(
                sent_count=models.Count('id', filter=models.Q(status=CampaignRecipient.RecipientStatus.SENT)),
                delivered_count=models.Count('id', filter=models.Q(status=CampaignRecipient.RecipientStatus.DELIVERED)),
                read_count=models.Count('id', filter=models.Q(status=CampaignRecipient.RecipientStatus.READ)),
                failed_count=models.Count('id', filter=models.Q(status=CampaignRecipient.RecipientStatus.FAILED)),
            )
            
            campaign.messages_sent = stats['sent_count'] or 0
            campaign.messages_delivered = stats['delivered_count'] or 0
            campaign.messages_read = stats['read_count'] or 0
            campaign.messages_failed = stats['failed_count'] or 0
            campaign.save(update_fields=[
                'messages_sent', 'messages_delivered', 
                'messages_read', 'messages_failed'
            ])
            
            updated += 1
        except Exception as e:
            logger.error(f"Error updating stats for campaign {campaign.id}: {e}")
    
    return {'updated_campaigns': updated}


# Import models at the end to avoid circular imports
from django.db import models
from apps.campaigns.models import CampaignRecipient