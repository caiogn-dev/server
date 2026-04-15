"""
Unified Conversation model.

Replaces:
- conversations.Conversation
- messaging.MessengerConversation
- instagram.InstagramConversation
- messaging_v2.Conversation
"""

import uuid
from django.db import models
from apps.core.models import BaseModel


class UnifiedConversation(BaseModel):
    """
    Unified conversation model for all messaging platforms.
    
    A conversation represents a chat session between a business and a customer
    on a specific messaging platform.
    """
    
    class PlatformType(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        INSTAGRAM = 'instagram', 'Instagram'
        MESSENGER = 'messenger', 'Messenger'
    
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        ARCHIVED = 'archived', 'Archived'
        BLOCKED = 'blocked', 'Blocked'
    
    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    platform_account = models.ForeignKey(
        'messaging.PlatformAccount',
        on_delete=models.CASCADE,
        related_name='conversations',
        help_text='Platform account this conversation belongs to'
    )
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='conversations',
        null=True,
        blank=True
    )
    
    # Platform identification
    platform = models.CharField(
        max_length=20,
        choices=PlatformType.choices,
        db_index=True
    )
    
    # External ID (platform-specific conversation ID)
    external_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text='Platform-specific conversation ID'
    )
    
    # Customer information
    customer_phone = models.CharField(
        max_length=20,
        db_index=True,
        help_text='Customer phone number or identifier'
    )
    customer_name = models.CharField(max_length=255, blank=True)
    customer_email = models.EmailField(blank=True)
    customer_profile_pic = models.URLField(blank=True)
    
    # Customer IDs on different platforms
    # WhatsApp: phone number
    # Instagram: participant_id (IGSID)
    # Messenger: PSID (Page-scoped ID)
    customer_platform_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text='Platform-specific customer ID'
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    is_active = models.BooleanField(default=True)
    unread_count = models.IntegerField(default=0)
    
    # Assignment
    assigned_to = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_conversations'
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    
    # AI/Automation
    ai_enabled = models.BooleanField(default=True)
    last_agent_response = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_message_preview = models.TextField(blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    # Source tracking
    source = models.CharField(
        max_length=50,
        default='organic',
        help_text='Source: organic, ad, campaign, etc'
    )
    
    class Meta:
        db_table = 'unified_conversations'
        verbose_name = 'Conversation'
        verbose_name_plural = 'Conversations'
        ordering = ['-last_message_at', '-created_at']
        indexes = [
            models.Index(fields=['platform_account', 'customer_phone', '-created_at']),
            models.Index(fields=['store', 'platform', 'status']),
            models.Index(fields=['customer_phone', 'platform']),
            models.Index(fields=['status', 'is_active', '-last_message_at']),
            models.Index(fields=['assigned_to', 'status']),
        ]
        unique_together = [
            ['platform_account', 'customer_platform_id'],
        ]
    
    def __str__(self):
        return f"Chat with {self.customer_name or self.customer_phone} ({self.get_platform_display()})"
    
    def mark_read(self):
        """Mark conversation as read."""
        self.unread_count = 0
        self.save(update_fields=['unread_count', 'updated_at'])
    
    def increment_unread(self):
        """Increment unread count."""
        self.unread_count += 1
        self.save(update_fields=['unread_count', 'updated_at'])
    
    def update_last_message(self, preview: str, timestamp=None):
        """Update last message info."""
        self.last_message_preview = preview[:200] if preview else ''
        self.last_message_at = timestamp or __import__('django.utils.timezone').now()
        self.save(update_fields=['last_message_preview', 'last_message_at', 'updated_at'])
    
    def assign_to(self, user):
        """Assign conversation to a user."""
        self.assigned_to = user
        self.assigned_at = __import__('django.utils.timezone').now()
        self.save(update_fields=['assigned_to', 'assigned_at', 'updated_at'])
    
    def unassign(self):
        """Unassign conversation."""
        self.assigned_to = None
        self.assigned_at = None
        self.save(update_fields=['assigned_to', 'assigned_at', 'updated_at'])
    
    # Platform-specific helpers
    @property
    def is_whatsapp(self) -> bool:
        return self.platform == self.PlatformType.WHATSAPP
    
    @property
    def is_instagram(self) -> bool:
        return self.platform == self.PlatformType.INSTAGRAM
    
    @property
    def is_messenger(self) -> bool:
        return self.platform == self.PlatformType.MESSENGER
    
    @property
    def psid(self) -> str:
        """Get PSID (Messenger Page-scoped ID)."""
        if self.is_messenger:
            return self.customer_platform_id
        return ''
    
    @property
    def igsid(self) -> str:
        """Get IGSID (Instagram-scoped ID)."""
        if self.is_instagram:
            return self.customer_platform_id
        return ''
