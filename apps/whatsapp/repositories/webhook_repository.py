"""
Webhook Event Repository.
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timedelta
from django.db.models import QuerySet
from django.utils import timezone
from ..models import WebhookEvent, WhatsAppAccount


class WebhookEventRepository:
    """Repository for Webhook Event operations."""

    def get_by_id(self, event_id: UUID) -> Optional[WebhookEvent]:
        """Get event by ID."""
        try:
            return WebhookEvent.objects.get(id=event_id)
        except WebhookEvent.DoesNotExist:
            return None

    def get_by_event_id(self, event_id: str) -> Optional[WebhookEvent]:
        """Get event by external event ID."""
        try:
            return WebhookEvent.objects.get(event_id=event_id)
        except WebhookEvent.DoesNotExist:
            return None

    def exists_by_event_id(self, event_id: str) -> bool:
        """Check if event exists by external event ID."""
        return WebhookEvent.objects.filter(event_id=event_id).exists()

    def create(self, **kwargs) -> WebhookEvent:
        """Create a new webhook event."""
        return WebhookEvent.objects.create(**kwargs)

    def update_status(
        self,
        event: WebhookEvent,
        status: str,
        error_message: str = ''
    ) -> WebhookEvent:
        """Update event processing status."""
        event.processing_status = status
        event.error_message = error_message
        
        if status == WebhookEvent.ProcessingStatus.COMPLETED:
            event.processed_at = timezone.now()
        
        event.save()
        return event

    def mark_as_processing(self, event: WebhookEvent) -> WebhookEvent:
        """Mark event as processing."""
        return self.update_status(event, WebhookEvent.ProcessingStatus.PROCESSING)

    def mark_as_completed(self, event: WebhookEvent) -> WebhookEvent:
        """Mark event as completed."""
        return self.update_status(event, WebhookEvent.ProcessingStatus.COMPLETED)

    def mark_as_failed(self, event: WebhookEvent, error_message: str) -> WebhookEvent:
        """Mark event as failed."""
        event.retry_count += 1
        return self.update_status(
            event,
            WebhookEvent.ProcessingStatus.FAILED,
            error_message
        )

    def mark_as_duplicate(self, event: WebhookEvent) -> WebhookEvent:
        """Mark event as duplicate."""
        return self.update_status(event, WebhookEvent.ProcessingStatus.DUPLICATE)

    def get_pending_events(self, limit: int = 100) -> QuerySet[WebhookEvent]:
        """Get pending events for processing."""
        return WebhookEvent.objects.filter(
            processing_status=WebhookEvent.ProcessingStatus.PENDING
        ).select_related('account').order_by('created_at')[:limit]

    def get_failed_events_for_retry(
        self,
        max_retries: int = 3,
        limit: int = 100
    ) -> QuerySet[WebhookEvent]:
        """Get failed events eligible for retry."""
        return WebhookEvent.objects.filter(
            processing_status=WebhookEvent.ProcessingStatus.FAILED,
            retry_count__lt=max_retries
        ).select_related('account').order_by('created_at')[:limit]

    def get_by_account(
        self,
        account: WhatsAppAccount,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> QuerySet[WebhookEvent]:
        """Get events by account with optional filters."""
        queryset = WebhookEvent.objects.filter(account=account)
        
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        if status:
            queryset = queryset.filter(processing_status=status)
        
        return queryset.order_by('-created_at')[:limit]

    def cleanup_old_events(self, days: int = 30) -> int:
        """Delete old processed events."""
        cutoff_date = timezone.now() - timedelta(days=days)
        deleted, _ = WebhookEvent.objects.filter(
            created_at__lt=cutoff_date,
            processing_status__in=[
                WebhookEvent.ProcessingStatus.COMPLETED,
                WebhookEvent.ProcessingStatus.DUPLICATE
            ]
        ).delete()
        return deleted

    def get_event_stats(
        self,
        account: Optional[WhatsAppAccount] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> dict:
        """Get webhook event statistics."""
        queryset = WebhookEvent.objects.all()
        
        if account:
            queryset = queryset.filter(account=account)
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        from django.db.models import Count
        stats = queryset.values('processing_status').annotate(count=Count('id'))
        
        return {
            'total': queryset.count(),
            'by_status': {s['processing_status']: s['count'] for s in stats}
        }
