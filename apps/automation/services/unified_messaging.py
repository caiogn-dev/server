"""
Unified Messaging Service

This module provides a unified interface for all messaging operations across
campaigns, automation, and scheduled messages.

Usage:
    from apps.automation.services.unified_messaging import UnifiedMessagingService
    
    # Send a campaign message
    UnifiedMessagingService.send_campaign_message(campaign, recipient)
    
    # Schedule a message
    UnifiedMessagingService.schedule_message(account, to_number, message_data, scheduled_at)
    
    # Process scheduled messages (called by Celery)
    UnifiedMessagingService.process_due_messages()
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from django.utils import timezone
from django.db import transaction

from apps.whatsapp.models import WhatsAppAccount, Message
from apps.automation.models import ScheduledMessage
from apps.campaigns.models import Campaign, CampaignRecipient

logger = logging.getLogger(__name__)


class UnifiedMessagingService:
    """
    Unified service for all messaging operations.
    Consolidates functionality from campaigns, automation, and scheduled messages.
    """
    
    @staticmethod
    def schedule_message(
        account: WhatsAppAccount,
        to_number: str,
        message_data: Dict[str, Any],
        scheduled_at: datetime,
        source: str = 'manual',
        campaign_id: Optional[str] = None,
        created_by=None,
        contact_name: str = '',
        timezone_str: str = 'America/Sao_Paulo'
    ) -> ScheduledMessage:
        """
        Schedule a message for future delivery.
        This is the unified method used by campaigns, automation, and manual scheduling.
        
        Args:
            account: WhatsApp account to send from
            to_number: Recipient phone number
            message_data: Dict with message content (text, template, media, etc.)
            scheduled_at: When to send the message
            source: Source of the message (manual, campaign, automation, api)
            campaign_id: Optional campaign ID if part of a campaign
            created_by: User who created the scheduled message
            contact_name: Optional contact name
            timezone_str: Timezone for scheduling
            
        Returns:
            ScheduledMessage instance
        """
        # Determine message type from data
        message_type = message_data.get('message_type', 'text')
        
        # Extract content based on message type
        message_text = message_data.get('text', '')
        template_name = message_data.get('template_name', '')
        template_language = message_data.get('template_language', 'pt_BR')
        template_components = message_data.get('template_components', [])
        media_url = message_data.get('media_url', '')
        buttons = message_data.get('buttons', [])
        
        # Create the scheduled message
        scheduled = ScheduledMessage.objects.create(
            account=account,
            to_number=to_number,
            contact_name=contact_name,
            message_type=message_type,
            message_text=message_text,
            template_name=template_name,
            template_language=template_language,
            template_components=template_components,
            media_url=media_url,
            buttons=buttons,
            content=message_data.get('content', {}),
            scheduled_at=scheduled_at,
            timezone=timezone_str,
            status=ScheduledMessage.Status.PENDING,
            source=source,
            campaign_id=campaign_id,
            created_by=created_by,
        )
        
        logger.info(f"Scheduled message created: {scheduled.id} for {to_number} at {scheduled_at}")
        return scheduled
    
    @classmethod
    def schedule_campaign_messages(
        cls,
        campaign: Campaign,
        recipients: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> int:
        """
        Schedule messages for a campaign.
        Creates ScheduledMessage entries for each recipient.
        
        Args:
            campaign: Campaign instance
            recipients: List of dicts with 'phone_number', 'contact_name', 'variables'
            batch_size: Number of messages to create in each batch
            
        Returns:
            Number of messages scheduled
        """
        scheduled_count = 0
        
        # Prepare message data from campaign
        message_data = campaign.message_content or {}
        if campaign.template:
            message_data['message_type'] = 'template'
            message_data['template_name'] = campaign.template.name
            message_data['template_language'] = campaign.template.language
        
        with transaction.atomic():
            for recipient_data in recipients:
                phone = recipient_data.get('phone_number')
                name = recipient_data.get('contact_name', '')
                variables = recipient_data.get('variables', {})
                
                if not phone:
                    continue
                
                # Create or update CampaignRecipient
                recipient, created = CampaignRecipient.objects.update_or_create(
                    campaign=campaign,
                    phone_number=phone,
                    defaults={
                        'contact_name': name,
                        'variables': variables,
                        'status': CampaignRecipient.RecipientStatus.PENDING,
                    }
                )
                
                # Schedule the message
                scheduled = cls.schedule_message(
                    account=campaign.account,
                    to_number=phone,
                    message_data=message_data,
                    scheduled_at=campaign.scheduled_at or timezone.now(),
                    source='campaign',
                    campaign_id=str(campaign.id),
                    created_by=campaign.created_by,
                    contact_name=name,
                )
                
                # Link recipient to scheduled message
                recipient.message_id = str(scheduled.id)
                recipient.save(update_fields=['message_id'])
                
                scheduled_count += 1
                
                if scheduled_count % batch_size == 0:
                    logger.info(f"Scheduled {scheduled_count} messages for campaign {campaign.id}")
        
        # Update campaign stats
        campaign.total_recipients = scheduled_count
        campaign.save(update_fields=['total_recipients'])
        
        logger.info(f"Campaign {campaign.id}: {scheduled_count} messages scheduled")
        return scheduled_count
    
    @classmethod
    def process_due_messages(cls, batch_size: int = 100) -> Dict[str, int]:
        """
        Process all due scheduled messages.
        Called by Celery beat task.
        
        Args:
            batch_size: Maximum number of messages to process
            
        Returns:
            Dict with counts: {'processed': int, 'sent': int, 'failed': int}
        """
        now = timezone.now()
        
        # Get due messages
        due_messages = ScheduledMessage.objects.filter(
            status=ScheduledMessage.Status.PENDING,
            scheduled_at__lte=now
        ).select_related('account')[:batch_size]
        
        results = {'processed': 0, 'sent': 0, 'failed': 0}
        
        for scheduled in due_messages:
            try:
                results['processed'] += 1
                cls._send_scheduled_message(scheduled)
                results['sent'] += 1
            except Exception as e:
                logger.error(f"Failed to send scheduled message {scheduled.id}: {e}")
                scheduled.status = ScheduledMessage.Status.FAILED
                scheduled.error_message = str(e)
                scheduled.save(update_fields=['status', 'error_message'])
                results['failed'] += 1
                
                # Update campaign recipient if applicable
                if scheduled.campaign_id:
                    cls._update_campaign_recipient_status(
                        scheduled.campaign_id,
                        scheduled.to_number,
                        CampaignRecipient.RecipientStatus.FAILED,
                        error=str(e)
                    )
        
        return results
    
    @classmethod
    def _send_scheduled_message(cls, scheduled: ScheduledMessage) -> Message:
        """
        Send a scheduled message via WhatsApp.
        
        Args:
            scheduled: ScheduledMessage instance
            
        Returns:
            Sent Message instance
        """
        from apps.whatsapp.services import WhatsAppService
        
        account = scheduled.account
        
        # Prepare message based on type
        if scheduled.message_type == ScheduledMessage.MessageType.TEMPLATE:
            # Send template message
            message = WhatsAppService.send_template_message(
                account=account,
                to_number=scheduled.to_number,
                template_name=scheduled.template_name,
                language=scheduled.template_language,
                components=scheduled.template_components,
            )
        elif scheduled.message_type == ScheduledMessage.MessageType.TEXT:
            # Send text message
            message = WhatsAppService.send_text_message(
                account=account,
                to_number=scheduled.to_number,
                text=scheduled.message_text,
            )
        elif scheduled.message_type == ScheduledMessage.MessageType.IMAGE:
            # Send image message
            message = WhatsAppService.send_media_message(
                account=account,
                to_number=scheduled.to_number,
                media_url=scheduled.media_url,
                caption=scheduled.message_text,
                media_type='image',
            )
        else:
            # Default to text
            message = WhatsAppService.send_text_message(
                account=account,
                to_number=scheduled.to_number,
                text=scheduled.message_text or scheduled.content.get('text', ''),
            )
        
        # Update scheduled message
        scheduled.status = ScheduledMessage.Status.SENT
        scheduled.sent_at = timezone.now()
        scheduled.whatsapp_message_id = message.whatsapp_message_id
        scheduled.save(update_fields=['status', 'sent_at', 'whatsapp_message_id'])
        
        # Update campaign recipient if applicable
        if scheduled.campaign_id:
            cls._update_campaign_recipient_status(
                scheduled.campaign_id,
                scheduled.to_number,
                CampaignRecipient.RecipientStatus.SENT,
                message_id=message.whatsapp_message_id
            )
        
        return message
    
    @staticmethod
    def _update_campaign_recipient_status(
        campaign_id: str,
        phone_number: str,
        status: str,
        message_id: str = '',
        error: str = ''
    ):
        """Update campaign recipient status."""
        try:
            recipient = CampaignRecipient.objects.get(
                campaign_id=campaign_id,
                phone_number=phone_number
            )
            recipient.status = status
            
            if message_id:
                recipient.whatsapp_message_id = message_id
            if error:
                recipient.error_message = error
                recipient.failed_at = timezone.now()
            if status == CampaignRecipient.RecipientStatus.SENT:
                recipient.sent_at = timezone.now()
            
            recipient.save()
        except CampaignRecipient.DoesNotExist:
            pass
    
    @staticmethod
    def cancel_scheduled_message(scheduled_id: str) -> bool:
        """
        Cancel a scheduled message.
        
        Args:
            scheduled_id: ID of the scheduled message
            
        Returns:
            True if cancelled, False otherwise
        """
        try:
            scheduled = ScheduledMessage.objects.get(
                id=scheduled_id,
                status=ScheduledMessage.Status.PENDING
            )
            scheduled.status = ScheduledMessage.Status.CANCELLED
            scheduled.save(update_fields=['status'])
            
            # Update campaign recipient if applicable
            if scheduled.campaign_id:
                UnifiedMessagingService._update_campaign_recipient_status(
                    scheduled.campaign_id,
                    scheduled.to_number,
                    CampaignRecipient.RecipientStatus.SKIPPED
                )
            
            return True
        except ScheduledMessage.DoesNotExist:
            return False
    
    @staticmethod
    def get_message_stats(account: WhatsAppAccount = None) -> Dict[str, Any]:
        """
        Get unified messaging statistics.
        
        Args:
            account: Optional account to filter by
            
        Returns:
            Dict with statistics
        """
        qs = ScheduledMessage.objects.all()
        if account:
            qs = qs.filter(account=account)
        
        total = qs.count()
        pending = qs.filter(status=ScheduledMessage.Status.PENDING).count()
        sent = qs.filter(status=ScheduledMessage.Status.SENT).count()
        failed = qs.filter(status=ScheduledMessage.Status.FAILED).count()
        
        return {
            'total_scheduled': total,
            'pending': pending,
            'sent': sent,
            'failed': failed,
            'success_rate': (sent / (sent + failed) * 100) if (sent + failed) > 0 else 0,
        }
