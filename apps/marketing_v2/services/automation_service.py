"""Automation Service for Marketing v2."""

from datetime import datetime
from django.db import transaction
from ..models import Automation, ScheduledMessage


class AutomationService:
    """Service for automation and scheduled messages."""

    @staticmethod
def create_automation(store, name, trigger, actions, conditions=None):
        """Create a new automation."""
        automation = Automation.objects.create(
            store=store,
            name=name,
            trigger=trigger,
            actions=actions,
            conditions=conditions or {}
        )
        return automation

    @staticmethod
    def schedule_message(store, recipient, content, scheduled_at, channel='whatsapp'):
        """Schedule a message for future delivery."""
        message = ScheduledMessage.objects.create(
            store=store,
            recipient=recipient,
            channel=channel,
            content=content,
            scheduled_at=scheduled_at
        )
        return message

    @staticmethod
    def process_pending_scheduled():
        """Process all pending scheduled messages that are due."""
        now = datetime.now()
        pending = ScheduledMessage.objects.filter(
            status=ScheduledMessage.Status.PENDING,
            scheduled_at__lte=now
        )
        return pending.count()
