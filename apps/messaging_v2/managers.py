"""
Custom managers for unified messaging models.

Provides platform-specific querysets and convenience methods.
"""
from django.db import models
from django.db.models import Q


class UnifiedMessageQuerySet(models.QuerySet):
    """Base queryset for UnifiedMessage."""
    
    def inbound(self):
        """Filter for inbound messages."""
        return self.filter(direction='inbound')
    
    def outbound(self):
        """Filter for outbound messages."""
        return self.filter(direction='outbound')
    
    def pending(self):
        """Filter for pending messages."""
        return self.filter(status='pending')
    
    def sent(self):
        """Filter for sent messages."""
        return self.filter(status='sent')
    
    def delivered(self):
        """Filter for delivered messages."""
        return self.filter(status='delivered')
    
    def read(self):
        """Filter for read messages."""
        return self.filter(status='read')
    
    def failed(self):
        """Filter for failed messages."""
        return self.filter(status='failed')
    
    def by_platform(self, platform):
        """Filter by platform."""
        return self.filter(platform=platform)
    
    def by_conversation(self, conversation_id):
        """Filter by conversation."""
        return self.filter(conversation_id=conversation_id)
    
    def by_sender(self, sender_id):
        """Filter by sender."""
        return self.filter(sender_id=sender_id)
    
    def by_recipient(self, recipient_id):
        """Filter by recipient."""
        return self.filter(recipient_id=recipient_id)
    
    def by_type(self, message_type):
        """Filter by message type."""
        return self.filter(message_type=message_type)
    
    def with_media(self):
        """Filter for messages with media."""
        return self.exclude(
            Q(media_url='') | Q(media_url__isnull=True)
        )
    
    def text_only(self):
        """Filter for text-only messages."""
        return self.filter(message_type='text')
    
    def unread(self):
        """Filter for unread messages (inbound only)."""
        return self.filter(
            direction='inbound'
        ).exclude(status='read')
    
    def recent(self, hours=24):
        """Filter for recent messages."""
        from django.utils import timezone
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(hours=hours)
        return self.filter(created_at__gte=cutoff)
    
    def search_text(self, query):
        """Search in text content."""
        return self.filter(text_content__icontains=query)
    
    def processed_by_agent(self):
        """Filter for messages processed by AI agent."""
        return self.filter(processed_by_agent=True)
    
    def not_processed_by_agent(self):
        """Filter for messages not processed by AI agent."""
        return self.filter(processed_by_agent=False)


class WhatsAppManager(models.Manager):
    """
    Manager for WhatsApp-specific queries.
    
    Provides convenient access to WhatsApp messages with
    platform-specific filtering.
    """
    
    def get_queryset(self):
        return UnifiedMessageQuerySet(self.model, using=self._db).filter(
            platform='whatsapp'
        )
    
    def by_phone_number(self, phone_number):
        """Filter by phone number (sender or recipient)."""
        return self.get_queryset().filter(
            models.Q(sender_id=phone_number) | models.Q(recipient_id=phone_number)
        )
    
    def templates(self):
        """Filter for template messages."""
        return self.get_queryset().filter(message_type='template')
    
    def interactive(self):
        """Filter for interactive messages."""
        return self.get_queryset().filter(message_type='interactive')
    
    def with_context(self):
        """Filter for messages with reply context."""
        return self.get_queryset().exclude(
            models.Q(reply_to_external_id='') | Q(reply_to_external_id__isnull=True)
        )


class InstagramManager(models.Manager):
    """
    Manager for Instagram-specific queries.
    
    Provides convenient access to Instagram messages with
    platform-specific filtering.
    """
    
    def get_queryset(self):
        return UnifiedMessageQuerySet(self.model, using=self._db).filter(
            platform='instagram'
        )
    
    def by_username(self, username):
        """Filter by username (sender or recipient)."""
        return self.get_queryset().filter(
            models.Q(sender_name=username) | models.Q(recipient_name=username)
        )
    
    def story_replies(self):
        """Filter for story reply messages."""
        return self.get_queryset().filter(message_type='story_reply')
    
    def post_shares(self):
        """Filter for post share messages."""
        return self.get_queryset().filter(
            message_type__in=['post_share', 'reel_share', 'profile_share']
        )
    
    def unsent(self):
        """Filter for unsent messages."""
        return self.get_queryset().filter(status='unsent')
    
    def reactions(self):
        """Filter for reaction messages."""
        return self.get_queryset().filter(message_type='reaction')


class MessengerManager(models.Manager):
    """
    Manager for Messenger-specific queries.
    
    Provides convenient access to Messenger messages with
    platform-specific filtering.
    """
    
    def get_queryset(self):
        return UnifiedMessageQuerySet(self.model, using=self._db).filter(
            platform='messenger'
        )
    
    def by_psid(self, psid):
        """Filter by Page-scoped ID."""
        return self.get_queryset().filter(
            models.Q(sender_id=psid) | models.Q(recipient_id=psid)
        )
    
    def quick_replies(self):
        """Filter for quick reply messages."""
        return self.get_queryset().filter(message_type='quick_reply')
    
    def postbacks(self):
        """Filter for postback messages."""
        return self.get_queryset().filter(message_type='postback')
    
    def with_templates(self):
        """Filter for messages with templates."""
        return self.get_queryset().exclude(
            models.Q(template_name='') | Q(template_name__isnull=True)
        )


class UnifiedMessageManager(models.Manager):
    """
    Default manager for UnifiedMessage.
    
    Provides the base queryset and platform-specific managers.
    """
    
    def get_queryset(self):
        return UnifiedMessageQuerySet(self.model, using=self._db)
    
    # Platform-specific accessors
    def whatsapp(self):
        """Get WhatsApp messages."""
        return self.get_queryset().filter(platform='whatsapp')
    
    def instagram(self):
        """Get Instagram messages."""
        return self.get_queryset().filter(platform='instagram')
    
    def messenger(self):
        """Get Messenger messages."""
        return self.get_queryset().filter(platform='messenger')
    
    # Convenience methods
    def get_by_external_id(self, external_id, platform=None):
        """Get message by external platform ID."""
        qs = self.get_queryset().filter(external_id=external_id)
        if platform:
            qs = qs.filter(platform=platform)
        return qs.first()
    
    def get_conversation_messages(self, conversation_id, platform=None):
        """Get all messages for a conversation."""
        qs = self.get_queryset().filter(conversation_id=conversation_id)
        if platform:
            qs = qs.filter(platform=platform)
        return qs.order_by('created_at')
    
    def get_thread(self, participant_a, participant_b, platform=None):
        """Get messages between two participants."""
        qs = self.get_queryset().filter(
            models.Q(
                sender_id=participant_a,
                recipient_id=participant_b
            ) | models.Q(
                sender_id=participant_b,
                recipient_id=participant_a
            )
        )
        if platform:
            qs = qs.filter(platform=platform)
        return qs.order_by('created_at')


class MessageTemplateQuerySet(models.QuerySet):
    """QuerySet for MessageTemplate."""
    
    def approved(self):
        """Filter for approved templates."""
        return self.filter(status='approved')
    
    def pending(self):
        """Filter for pending templates."""
        return self.filter(status='pending')
    
    def by_platform(self, platform):
        """Filter by platform."""
        return self.filter(platform=platform)
    
    def by_type(self, template_type):
        """Filter by template type."""
        return self.filter(template_type=template_type)
    
    def by_language(self, language):
        """Filter by language."""
        return self.filter(language=language)
    
    def search(self, query):
        """Search in name and description."""
        return self.filter(
            models.Q(name__icontains=query) | Q(description__icontains=query)
        )


class MessageTemplateManager(models.Manager):
    """Manager for MessageTemplate."""
    
    def get_queryset(self):
        return MessageTemplateQuerySet(self.model, using=self._db)
    
    def get_by_external_id(self, external_id):
        """Get template by external platform ID."""
        return self.get_queryset().filter(external_template_id=external_id).first()
    
    def get_active_for_account(self, platform, account_id):
        """Get active templates for an account."""
        return self.get_queryset().filter(
            platform=platform,
            platform_account_id=account_id,
            status='approved'
        )


class WebhookEventQuerySet(models.QuerySet):
    """QuerySet for PlatformWebhookEvent."""
    
    def pending(self):
        """Filter for pending events."""
        return self.filter(processing_status='pending')
    
    def completed(self):
        """Filter for completed events."""
        return self.filter(processing_status='completed')
    
    def failed(self):
        """Filter for failed events."""
        return self.filter(processing_status='failed')
    
    def duplicates(self):
        """Filter for duplicate events."""
        return self.filter(processing_status='duplicate')
    
    def by_platform(self, platform):
        """Filter by platform."""
        return self.filter(platform=platform)
    
    def by_type(self, event_type):
        """Filter by event type."""
        return self.filter(event_type=event_type)
    
    def recent(self, hours=24):
        """Filter for recent events."""
        from django.utils import timezone
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(hours=hours)
        return self.filter(created_at__gte=cutoff)


class WebhookEventManager(models.Manager):
    """Manager for PlatformWebhookEvent."""
    
    def get_queryset(self):
        return WebhookEventQuerySet(self.model, using=self._db)
    
    def get_by_event_id(self, platform, event_id):
        """Get event by platform event ID."""
        return self.get_queryset().filter(
            platform=platform,
            event_id=event_id
        ).first()
    
    def is_duplicate(self, platform, event_id, payload_hash=None):
        """Check if event is a duplicate."""
        qs = self.get_queryset().filter(
            platform=platform,
            event_id=event_id
        )
        if payload_hash:
            qs = qs.filter(payload_hash=payload_hash)
        return qs.exists()
