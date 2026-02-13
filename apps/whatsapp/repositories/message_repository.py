"""
Message Repository.
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
from django.db.models import QuerySet, Q, Count
from django.utils import timezone
from ..models import Message, WhatsAppAccount


class MessageRepository:
    """Repository for Message operations."""

    def get_by_id(self, message_id: UUID) -> Optional[Message]:
        """Get message by ID."""
        try:
            return Message.objects.select_related('account', 'conversation').get(id=message_id)
        except Message.DoesNotExist:
            return None

    def get_by_whatsapp_id(self, whatsapp_message_id: str) -> Optional[Message]:
        """Get message by WhatsApp message ID."""
        try:
            return Message.objects.select_related('account', 'conversation').get(
                whatsapp_message_id=whatsapp_message_id
            )
        except Message.DoesNotExist:
            return None

    def get_by_account(
        self,
        account: WhatsAppAccount,
        direction: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> QuerySet[Message]:
        """Get messages by account with optional filters."""
        queryset = Message.objects.filter(account=account)
        
        if direction:
            queryset = queryset.filter(direction=direction)
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset.select_related('conversation')[:limit]

    def get_conversation_messages(
        self,
        account: WhatsAppAccount,
        phone_number: str,
        limit: int = 50
    ) -> QuerySet[Message]:
        """Get messages for a specific conversation."""
        return Message.objects.filter(
            account=account
        ).filter(
            Q(from_number=phone_number) | Q(to_number=phone_number)
        ).select_related('conversation').order_by('-created_at')[:limit]

    def create(self, **kwargs) -> Message:
        """Create a new message."""
        return Message.objects.create(**kwargs)

    def update_status(
        self,
        message: Message,
        status: str,
        timestamp: Optional[datetime] = None
    ) -> Message:
        """Update message status."""
        message.status = status
        timestamp = timestamp or timezone.now()
        
        if status == Message.MessageStatus.SENT:
            message.sent_at = timestamp
        elif status == Message.MessageStatus.DELIVERED:
            message.delivered_at = timestamp
        elif status == Message.MessageStatus.READ:
            message.read_at = timestamp
        elif status == Message.MessageStatus.FAILED:
            message.failed_at = timestamp
        
        message.save()
        return message

    def update_error(
        self,
        message: Message,
        error_code: str,
        error_message: str
    ) -> Message:
        """Update message with error information."""
        message.status = Message.MessageStatus.FAILED
        message.failed_at = timezone.now()
        message.error_code = error_code
        message.error_message = error_message
        message.save()
        return message

    def mark_as_processed_by_agent(self, message: Message) -> Message:
        """Mark message as processed by AI Agent."""
        message.processed_by_agent = True
        message.save(update_fields=['processed_by_agent', 'updated_at'])
        return message

    def get_pending_messages(self, limit: int = 100) -> QuerySet[Message]:
        """Get pending outbound messages."""
        return Message.objects.filter(
            direction=Message.MessageDirection.OUTBOUND,
            status=Message.MessageStatus.PENDING
        ).select_related('account')[:limit]

    def get_failed_messages(
        self,
        account: Optional[WhatsAppAccount] = None,
        since: Optional[datetime] = None
    ) -> QuerySet[Message]:
        """Get failed messages."""
        queryset = Message.objects.filter(status=Message.MessageStatus.FAILED)
        
        if account:
            queryset = queryset.filter(account=account)
        if since:
            queryset = queryset.filter(failed_at__gte=since)
        
        return queryset.select_related('account')

    def get_unprocessed_inbound(self, limit: int = 100) -> QuerySet[Message]:
        """Get unprocessed inbound messages."""
        return Message.objects.filter(
            direction=Message.MessageDirection.INBOUND,
            processed_by_agent=False
        ).select_related('account', 'conversation')[:limit]

    def get_message_stats(
        self,
        account: WhatsAppAccount,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get message statistics for an account."""
        queryset = Message.objects.filter(
            account=account,
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        
        stats = queryset.values('direction', 'status').annotate(count=Count('id'))
        
        result = {
            'total': queryset.count(),
            'inbound': 0,
            'outbound': 0,
            'by_status': {},
        }
        
        for stat in stats:
            if stat['direction'] == Message.MessageDirection.INBOUND:
                result['inbound'] += stat['count']
            else:
                result['outbound'] += stat['count']
            
            status = stat['status']
            if status not in result['by_status']:
                result['by_status'][status] = 0
            result['by_status'][status] += stat['count']
        
        return result

    def exists_by_whatsapp_id(self, whatsapp_message_id: str) -> bool:
        """Check if message exists by WhatsApp ID."""
        return Message.objects.filter(
            whatsapp_message_id=whatsapp_message_id
        ).exists()

    def bulk_create(self, messages: List[Dict[str, Any]]) -> List[Message]:
        """Bulk create messages."""
        message_objects = [Message(**msg) for msg in messages]
        return Message.objects.bulk_create(message_objects, ignore_conflicts=True)

    def delete_old_messages(self, days: int = 90) -> int:
        """Delete messages older than specified days."""
        cutoff_date = timezone.now() - timedelta(days=days)
        deleted, _ = Message.objects.filter(created_at__lt=cutoff_date).delete()
        return deleted
