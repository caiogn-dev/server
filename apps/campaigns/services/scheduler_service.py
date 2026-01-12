"""
Scheduler service for managing scheduled messages.
"""
import logging
from typing import Optional, Dict, Any, List
from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from django.utils import timezone

from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.services import MessageService
from ..models import ScheduledMessage

logger = logging.getLogger(__name__)
User = get_user_model()


class SchedulerService:
    """Service for scheduled message operations."""
    
    def schedule_message(
        self,
        account_id: str,
        to_number: str,
        scheduled_at: timezone.datetime,
        message_type: str = 'text',
        content: Optional[Dict[str, Any]] = None,
        template_id: Optional[str] = None,
        template_variables: Optional[Dict[str, Any]] = None,
        contact_name: str = '',
        is_recurring: bool = False,
        recurrence_rule: str = '',
        created_by: Optional[User] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScheduledMessage:
        """Schedule a new message."""
        account = WhatsAppAccount.objects.get(id=account_id)
        
        if scheduled_at <= timezone.now():
            raise ValueError("Scheduled time must be in the future")
        
        scheduled_message = ScheduledMessage.objects.create(
            account=account,
            to_number=to_number,
            contact_name=contact_name,
            message_type=message_type,
            content=content or {},
            template_id=template_id,
            template_variables=template_variables or {},
            scheduled_at=scheduled_at,
            is_recurring=is_recurring,
            recurrence_rule=recurrence_rule,
            next_occurrence=scheduled_at if is_recurring else None,
            created_by=created_by,
            metadata=metadata or {},
        )
        
        return scheduled_message
    
    def update_scheduled_message(
        self,
        message_id: str,
        **kwargs
    ) -> ScheduledMessage:
        """Update a scheduled message."""
        message = ScheduledMessage.objects.get(id=message_id)
        
        if message.status != ScheduledMessage.MessageStatus.SCHEDULED:
            raise ValueError("Cannot update message that is not scheduled")
        
        for key, value in kwargs.items():
            if hasattr(message, key):
                setattr(message, key, value)
        
        message.save()
        return message
    
    def cancel_scheduled_message(self, message_id: str) -> ScheduledMessage:
        """Cancel a scheduled message."""
        message = ScheduledMessage.objects.get(id=message_id)
        
        if message.status != ScheduledMessage.MessageStatus.SCHEDULED:
            raise ValueError("Cannot cancel message that is not scheduled")
        
        message.status = ScheduledMessage.MessageStatus.CANCELLED
        message.save()
        
        return message
    
    def get_pending_messages(
        self,
        account_id: Optional[str] = None,
        limit: int = 100,
    ) -> QuerySet:
        """Get messages that are due to be sent."""
        queryset = ScheduledMessage.objects.filter(
            status=ScheduledMessage.MessageStatus.SCHEDULED,
            scheduled_at__lte=timezone.now(),
            is_active=True,
        )
        
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        return queryset[:limit]
    
    def process_scheduled_messages(self, batch_size: int = 50) -> Dict[str, int]:
        """Process pending scheduled messages."""
        messages = self.get_pending_messages(limit=batch_size)
        
        sent = 0
        failed = 0
        
        for message in messages:
            try:
                self._send_scheduled_message(message)
                sent += 1
            except Exception as e:
                logger.error(f"Error sending scheduled message {message.id}: {e}")
                message.status = ScheduledMessage.MessageStatus.FAILED
                message.error_message = str(e)
                message.save()
                failed += 1
        
        return {'sent': sent, 'failed': failed}
    
    def _send_scheduled_message(self, scheduled_message: ScheduledMessage):
        """Send a scheduled message."""
        scheduled_message.status = ScheduledMessage.MessageStatus.PROCESSING
        scheduled_message.save()
        
        message_service = MessageService()
        
        try:
            if scheduled_message.template:
                message = message_service.send_template_message(
                    account_id=str(scheduled_message.account.id),
                    to=scheduled_message.to_number,
                    template_name=scheduled_message.template.name,
                    language_code=scheduled_message.template.language,
                    components=scheduled_message.template_variables.get('components', []),
                )
            elif scheduled_message.message_type == 'text':
                message = message_service.send_text_message(
                    account_id=str(scheduled_message.account.id),
                    to=scheduled_message.to_number,
                    text=scheduled_message.content.get('text', ''),
                )
            elif scheduled_message.message_type == 'image':
                message = message_service.send_image(
                    account_id=str(scheduled_message.account.id),
                    to=scheduled_message.to_number,
                    image_url=scheduled_message.content.get('image_url'),
                    caption=scheduled_message.content.get('caption', ''),
                )
            elif scheduled_message.message_type == 'document':
                message = message_service.send_document(
                    account_id=str(scheduled_message.account.id),
                    to=scheduled_message.to_number,
                    document_url=scheduled_message.content.get('document_url'),
                    filename=scheduled_message.content.get('filename', ''),
                    caption=scheduled_message.content.get('caption', ''),
                )
            else:
                raise ValueError(f"Unsupported message type: {scheduled_message.message_type}")
            
            scheduled_message.message_id = str(message.id)
            scheduled_message.whatsapp_message_id = message.whatsapp_message_id
            scheduled_message.status = ScheduledMessage.MessageStatus.SENT
            scheduled_message.sent_at = timezone.now()
            scheduled_message.save()
            
            # Handle recurring messages
            if scheduled_message.is_recurring and scheduled_message.recurrence_rule:
                self._schedule_next_occurrence(scheduled_message)
            
        except Exception as e:
            scheduled_message.status = ScheduledMessage.MessageStatus.FAILED
            scheduled_message.error_message = str(e)
            scheduled_message.save()
            raise
    
    def _schedule_next_occurrence(self, scheduled_message: ScheduledMessage):
        """Schedule the next occurrence of a recurring message."""
        # Simple implementation - for production, use dateutil.rrule
        rule = scheduled_message.recurrence_rule.lower()
        
        if 'daily' in rule:
            delta = timezone.timedelta(days=1)
        elif 'weekly' in rule:
            delta = timezone.timedelta(weeks=1)
        elif 'monthly' in rule:
            delta = timezone.timedelta(days=30)
        else:
            return
        
        next_time = scheduled_message.scheduled_at + delta
        
        # Create new scheduled message
        ScheduledMessage.objects.create(
            account=scheduled_message.account,
            to_number=scheduled_message.to_number,
            contact_name=scheduled_message.contact_name,
            message_type=scheduled_message.message_type,
            content=scheduled_message.content,
            template=scheduled_message.template,
            template_variables=scheduled_message.template_variables,
            scheduled_at=next_time,
            is_recurring=True,
            recurrence_rule=scheduled_message.recurrence_rule,
            next_occurrence=next_time,
            created_by=scheduled_message.created_by,
            metadata=scheduled_message.metadata,
        )
    
    def get_user_scheduled_messages(
        self,
        user: User,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> QuerySet:
        """Get scheduled messages for a user."""
        queryset = ScheduledMessage.objects.filter(
            created_by=user,
            is_active=True,
        )
        
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset[:limit]
    
    def get_scheduled_messages_stats(
        self,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get statistics for scheduled messages."""
        queryset = ScheduledMessage.objects.filter(is_active=True)
        
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        
        return {
            'total': queryset.count(),
            'scheduled': queryset.filter(status=ScheduledMessage.MessageStatus.SCHEDULED).count(),
            'sent': queryset.filter(status=ScheduledMessage.MessageStatus.SENT).count(),
            'failed': queryset.filter(status=ScheduledMessage.MessageStatus.FAILED).count(),
            'cancelled': queryset.filter(status=ScheduledMessage.MessageStatus.CANCELLED).count(),
            'recurring': queryset.filter(is_recurring=True).count(),
        }
