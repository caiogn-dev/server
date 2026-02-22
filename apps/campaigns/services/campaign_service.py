"""
Campaign service for managing marketing campaigns.
"""
import logging
from typing import Optional, Dict, Any, List
from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from django.utils import timezone

from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.services import MessageService
# Import unified messaging service for integration
from apps.automation.services import UnifiedMessagingService
from ..models import Campaign, CampaignRecipient, ContactList

logger = logging.getLogger(__name__)
User = get_user_model()


class CampaignService:
    """Service for campaign operations."""
    
    def create_campaign(
        self,
        account_id: str,
        name: str,
        campaign_type: str = Campaign.CampaignType.BROADCAST,
        description: str = '',
        template_id: Optional[str] = None,
        message_content: Optional[Dict[str, Any]] = None,
        audience_filters: Optional[Dict[str, Any]] = None,
        contact_list: Optional[List[Dict[str, Any]]] = None,
        scheduled_at: Optional[timezone.datetime] = None,
        created_by: Optional[User] = None,
    ) -> Campaign:
        """Create a new campaign."""
        account = WhatsAppAccount.objects.get(id=account_id)
        
        campaign = Campaign.objects.create(
            account=account,
            name=name,
            campaign_type=campaign_type,
            description=description,
            template_id=template_id,
            message_content=message_content or {},
            audience_filters=audience_filters or {},
            contact_list=contact_list or [],
            scheduled_at=scheduled_at,
            status=Campaign.CampaignStatus.DRAFT,
            created_by=created_by,
        )
        
        # Create recipients if contact list provided
        if contact_list:
            created_count = self._create_recipients(campaign, contact_list)
            campaign.total_recipients = created_count
            campaign.save(update_fields=['total_recipients'])
            logger.info(f"Campaign {campaign.id} created with {created_count} recipients")
        
        return campaign
    
    def update_campaign(
        self,
        campaign_id: str,
        **kwargs
    ) -> Campaign:
        """Update a campaign."""
        campaign = Campaign.objects.get(id=campaign_id)
        
        if campaign.status not in [Campaign.CampaignStatus.DRAFT, Campaign.CampaignStatus.SCHEDULED]:
            raise ValueError("Cannot update campaign that is running or completed")
        
        for key, value in kwargs.items():
            if hasattr(campaign, key):
                setattr(campaign, key, value)
        
        campaign.save()
        return campaign
    
    def schedule_campaign(
        self,
        campaign_id: str,
        scheduled_at: timezone.datetime,
    ) -> Campaign:
        """Schedule a campaign."""
        campaign = Campaign.objects.get(id=campaign_id)
        
        if campaign.status != Campaign.CampaignStatus.DRAFT:
            raise ValueError("Only draft campaigns can be scheduled")
        
        if scheduled_at <= timezone.now():
            raise ValueError("Scheduled time must be in the future")
        
        campaign.scheduled_at = scheduled_at
        campaign.status = Campaign.CampaignStatus.SCHEDULED
        campaign.save()
        
        return campaign
    
    def start_campaign(self, campaign_id: str) -> Campaign:
        """Start a campaign immediately."""
        import time
        
        campaign = Campaign.objects.get(id=campaign_id)
        
        if campaign.status not in [Campaign.CampaignStatus.DRAFT, Campaign.CampaignStatus.SCHEDULED]:
            raise ValueError("Campaign cannot be started")
        
        campaign.status = Campaign.CampaignStatus.RUNNING
        campaign.started_at = timezone.now()
        campaign.save()
        
        logger.info(f"Campaign {campaign_id} started with {campaign.total_recipients} recipients")
        
        # Trigger async processing (with fallback if Celery unavailable)
        celery_available = self._check_celery_connection()
        
        if celery_available:
            try:
                from ..tasks import process_campaign
                process_campaign.delay(str(campaign.id))
                logger.info(f"Campaign {campaign_id} queued for async processing via Celery")
            except Exception as e:
                logger.warning(f"Celery task failed for campaign {campaign_id}: {e}")
                celery_available = False
        
        if not celery_available:
            # Fallback: process synchronously in batches
            logger.info(f"Processing campaign {campaign_id} synchronously (Celery unavailable)")
            total_processed = 0
            
            while True:
                # Refresh campaign status
                campaign.refresh_from_db()
                
                if campaign.status != Campaign.CampaignStatus.RUNNING:
                    logger.info(f"Campaign {campaign_id} stopped (status: {campaign.status})")
                    break
                
                result = self.process_campaign_batch(campaign_id, batch_size=50)
                total_processed += result.get('processed', 0)
                
                if result['remaining'] == 0:
                    logger.info(f"Campaign {campaign_id} completed synchronously. Total: {total_processed}")
                    break
                
                logger.info(f"Campaign {campaign_id}: processed {result['processed']}, remaining {result['remaining']}")
                
                # Small delay between batches
                time.sleep(0.5)
        
        return campaign
    
    def _check_celery_connection(self) -> bool:
        """Check if Celery broker is available."""
        try:
            from config.celery import app
            conn = app.connection()
            conn.ensure_connection(max_retries=1, timeout=2)
            conn.close()
            return True
        except Exception as e:
            logger.warning(f"Celery broker not available: {e}")
            return False
    
    def pause_campaign(self, campaign_id: str) -> Campaign:
        """Pause a running campaign."""
        campaign = Campaign.objects.get(id=campaign_id)
        
        if campaign.status != Campaign.CampaignStatus.RUNNING:
            raise ValueError("Only running campaigns can be paused")
        
        campaign.status = Campaign.CampaignStatus.PAUSED
        campaign.save()
        
        return campaign
    
    def resume_campaign(self, campaign_id: str) -> Campaign:
        """Resume a paused campaign."""
        campaign = Campaign.objects.get(id=campaign_id)
        
        if campaign.status != Campaign.CampaignStatus.PAUSED:
            raise ValueError("Only paused campaigns can be resumed")
        
        campaign.status = Campaign.CampaignStatus.RUNNING
        campaign.save()
        
        # Trigger async processing
        from ..tasks import process_campaign
        process_campaign.delay(str(campaign.id))
        
        return campaign
    
    def cancel_campaign(self, campaign_id: str) -> Campaign:
        """Cancel a campaign."""
        campaign = Campaign.objects.get(id=campaign_id)
        
        if campaign.status in [Campaign.CampaignStatus.COMPLETED, Campaign.CampaignStatus.CANCELLED]:
            raise ValueError("Campaign is already completed or cancelled")
        
        campaign.status = Campaign.CampaignStatus.CANCELLED
        campaign.save()
        
        return campaign
    
    def add_recipients(
        self,
        campaign_id: str,
        contacts: List[Dict[str, Any]],
    ) -> int:
        """Add recipients to a campaign."""
        campaign = Campaign.objects.get(id=campaign_id)
        
        if campaign.status not in [Campaign.CampaignStatus.DRAFT, Campaign.CampaignStatus.SCHEDULED]:
            raise ValueError("Cannot add recipients to running campaign")
        
        count = self._create_recipients(campaign, contacts)
        
        # Update total
        campaign.total_recipients = campaign.recipients.count()
        campaign.save(update_fields=['total_recipients'])
        
        return count
    
    def remove_recipient(
        self,
        campaign_id: str,
        phone_number: str,
    ) -> bool:
        """Remove a recipient from a campaign."""
        try:
            recipient = CampaignRecipient.objects.get(
                campaign_id=campaign_id,
                phone_number=phone_number
            )
            
            if recipient.status != CampaignRecipient.RecipientStatus.PENDING:
                raise ValueError("Cannot remove recipient that has been processed")
            
            recipient.delete()
            
            # Update total
            campaign = Campaign.objects.get(id=campaign_id)
            campaign.total_recipients = campaign.recipients.count()
            campaign.save(update_fields=['total_recipients'])
            
            return True
        except CampaignRecipient.DoesNotExist:
            return False
    
    def get_campaign_stats(self, campaign_id: str) -> Dict[str, Any]:
        """Get campaign statistics."""
        campaign = Campaign.objects.get(id=campaign_id)
        
        return {
            'id': str(campaign.id),
            'name': campaign.name,
            'status': campaign.status,
            'total_recipients': campaign.total_recipients,
            'messages_sent': campaign.messages_sent,
            'messages_delivered': campaign.messages_delivered,
            'messages_read': campaign.messages_read,
            'messages_failed': campaign.messages_failed,
            'delivery_rate': campaign.delivery_rate,
            'read_rate': campaign.read_rate,
            'pending': campaign.recipients.filter(
                status=CampaignRecipient.RecipientStatus.PENDING
            ).count(),
            'started_at': campaign.started_at.isoformat() if campaign.started_at else None,
            'completed_at': campaign.completed_at.isoformat() if campaign.completed_at else None,
        }
    
    def process_campaign_batch(
        self,
        campaign_id: str,
        batch_size: int = 100,
    ) -> Dict[str, int]:
        """Process a batch of campaign recipients."""
        campaign = Campaign.objects.get(id=campaign_id)
        
        if campaign.status != Campaign.CampaignStatus.RUNNING:
            logger.warning(f"Campaign {campaign_id} is not running (status: {campaign.status})")
            return {'processed': 0, 'remaining': 0}
        
        # Get pending recipients
        recipients = list(campaign.recipients.filter(
            status=CampaignRecipient.RecipientStatus.PENDING
        )[:batch_size])
        
        if not recipients:
            logger.info(f"Campaign {campaign_id}: No pending recipients found")
            remaining = campaign.recipients.filter(
                status=CampaignRecipient.RecipientStatus.PENDING
            ).count()
            if remaining == 0:
                campaign.status = Campaign.CampaignStatus.COMPLETED
                campaign.completed_at = timezone.now()
                campaign.save()
            return {'processed': 0, 'remaining': remaining}
        
        logger.info(f"Campaign {campaign_id}: Processing {len(recipients)} recipients")
        
        message_service = MessageService()
        processed = 0
        failed = 0
        
        for recipient in recipients:
            try:
                logger.debug(f"Sending message to {recipient.phone_number}")
                
                # Send message
                if campaign.template:
                    message = message_service.send_template_message(
                        account_id=str(campaign.account.id),
                        to=recipient.phone_number,
                        template_name=campaign.template.name,
                        language_code=campaign.template.language,
                        components=self._build_template_components(
                            campaign.message_content,
                            recipient.variables
                        ),
                    )
                else:
                    text = self._personalize_message(
                        campaign.message_content.get('text', ''),
                        recipient.variables
                    )
                    message = message_service.send_text_message(
                        account_id=str(campaign.account.id),
                        to=recipient.phone_number,
                        text=text,
                    )
                
                recipient.message_id = str(message.id)
                recipient.whatsapp_message_id = message.whatsapp_message_id
                recipient.status = CampaignRecipient.RecipientStatus.SENT
                recipient.sent_at = timezone.now()
                recipient.save()
                
                campaign.messages_sent += 1
                processed += 1
                
                logger.info(f"Campaign {campaign_id}: Sent to {recipient.phone_number} (msg_id: {message.whatsapp_message_id})")
                
            except Exception as e:
                logger.error(f"Campaign {campaign_id}: Error sending to {recipient.phone_number}: {e}", exc_info=True)
                recipient.status = CampaignRecipient.RecipientStatus.FAILED
                recipient.failed_at = timezone.now()
                recipient.error_message = str(e)
                recipient.save()
                
                campaign.messages_failed += 1
                failed += 1
        
        # Check if campaign is complete
        remaining = campaign.recipients.filter(
            status=CampaignRecipient.RecipientStatus.PENDING
        ).count()
        
        if remaining == 0:
            campaign.status = Campaign.CampaignStatus.COMPLETED
            campaign.completed_at = timezone.now()
            logger.info(f"Campaign {campaign_id} completed: {campaign.messages_sent} sent, {campaign.messages_failed} failed")
        
        campaign.save()
        
        return {'processed': processed, 'failed': failed, 'remaining': remaining}
    
    def _create_recipients(
        self,
        campaign: Campaign,
        contacts: List[Dict[str, Any]],
    ) -> int:
        """Create campaign recipients from contact list."""
        created = 0
        for contact in contacts:
            phone = contact.get('phone') or contact.get('phone_number')
            if not phone:
                continue
            
            _, was_created = CampaignRecipient.objects.get_or_create(
                campaign=campaign,
                phone_number=phone,
                defaults={
                    'contact_name': contact.get('name', ''),
                    'variables': contact.get('variables', {}),
                }
            )
            if was_created:
                created += 1
        
        return created
    
    def _build_template_components(
        self,
        content: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Build template components with personalization."""
        components = content.get('components', [])
        
        for component in components:
            if 'parameters' in component:
                for param in component['parameters']:
                    if param.get('type') == 'text' and 'variable' in param:
                        var_name = param['variable']
                        param['text'] = variables.get(var_name, param.get('text', ''))
        
        return components
    
    def _personalize_message(
        self,
        text: str,
        variables: Dict[str, Any],
    ) -> str:
        """Personalize message text with variables."""
        for key, value in variables.items():
            text = text.replace(f'{{{{{key}}}}}', str(value))
        return text
    
    # Contact List methods
    def create_contact_list(
        self,
        account_id: str,
        name: str,
        contacts: List[Dict[str, Any]],
        description: str = '',
        source: str = 'manual',
        created_by: Optional[User] = None,
    ) -> ContactList:
        """Create a contact list."""
        account = WhatsAppAccount.objects.get(id=account_id)
        
        contact_list = ContactList.objects.create(
            account=account,
            name=name,
            description=description,
            contacts=contacts,
            contact_count=len(contacts),
            source=source,
            imported_at=timezone.now() if source != 'manual' else None,
            created_by=created_by,
        )
        
        return contact_list
    
    def schedule_campaign_messages(
        self,
        campaign_id: str,
    ) -> int:
        """
        Schedule campaign messages using UnifiedMessagingService.
        
        Args:
            campaign_id: Campaign ID
            
        Returns:
            Number of messages scheduled
        """
        campaign = Campaign.objects.get(id=campaign_id)
        
        # Get pending recipients
        recipients = campaign.recipients.filter(
            status=CampaignRecipient.RecipientStatus.PENDING
        ).values('phone_number', 'contact_name', 'variables')
        
        # Prepare message data
        message_data = campaign.message_content or {}
        if campaign.template:
            message_data['message_type'] = 'template'
            message_data['template_name'] = campaign.template.name
            message_data['template_language'] = campaign.template.language
        
        # Use unified service to schedule
        scheduled_count = UnifiedMessagingService.schedule_campaign_messages(
            campaign=campaign,
            recipients=list(recipients),
        )
        
        logger.info(f"Campaign {campaign_id}: {scheduled_count} messages scheduled via UnifiedMessagingService")
        return scheduled_count
    
    def import_contacts_from_csv(
        self,
        account_id: str,
        name: str,
        csv_content: str,
        created_by: Optional[User] = None,
    ) -> ContactList:
        """Import contacts from CSV content."""
        import csv
        from io import StringIO
        
        reader = csv.DictReader(StringIO(csv_content))
        contacts = []
        
        for row in reader:
            phone = row.get('phone') or row.get('phone_number') or row.get('telefone')
            if phone:
                contacts.append({
                    'phone': phone,
                    'name': row.get('name') or row.get('nome', ''),
                    'variables': {k: v for k, v in row.items() if k not in ['phone', 'phone_number', 'telefone', 'name', 'nome']},
                })
        
        return self.create_contact_list(
            account_id=account_id,
            name=name,
            contacts=contacts,
            source='csv',
            created_by=created_by,
        )
