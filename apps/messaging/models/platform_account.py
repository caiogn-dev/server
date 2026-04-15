"""
Unified Platform Account model.

Replaces:
- whatsapp.WhatsAppAccount
- instagram.InstagramAccount  
- messaging.MessengerAccount
- messaging_v2.PlatformAccount
- stores.StoreIntegration (for messaging platforms)
"""

import uuid
from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel
from apps.core.utils import token_encryption, mask_token

User = get_user_model()


class PlatformAccount(BaseModel):
    """
    Unified platform account for WhatsApp, Instagram, and Messenger.
    
    This is the single source of truth for all messaging platform accounts.
    """
    
    class PlatformType(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        INSTAGRAM = 'instagram', 'Instagram'
        MESSENGER = 'messenger', 'Messenger'
    
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        PENDING = 'pending', 'Pending Verification'
        SUSPENDED = 'suspended', 'Suspended'
        ERROR = 'error', 'Error'
    
    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='platform_accounts',
        help_text='Owner of this account'
    )
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.SET_NULL,
        related_name='platform_accounts',
        null=True,
        blank=True,
        help_text='Associated store'
    )
    
    # Platform identification
    platform = models.CharField(
        max_length=20,
        choices=PlatformType.choices,
        db_index=True,
        help_text='Messaging platform type'
    )
    name = models.CharField(
        max_length=255,
        help_text='Display name for this account'
    )
    
    # Platform-specific IDs
    external_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text='Platform-specific ID (page_id, instagram_business_id, phone_number_id)'
    )
    parent_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text='Parent ID (waba_id, facebook_page_id)'
    )
    
    # Phone number (mainly for WhatsApp)
    phone_number = models.CharField(max_length=20, blank=True)
    display_phone_number = models.CharField(max_length=30, blank=True)
    
    # Credentials (encrypted)
    access_token_encrypted = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    token_version = models.PositiveIntegerField(default=1)
    
    # Webhook
    webhook_verify_token = models.CharField(max_length=255, blank=True)
    webhook_verified = models.BooleanField(default=False)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    
    # AI Agent configuration
    default_agent = models.ForeignKey(
        'agents.Agent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='platform_accounts',
        help_text='Default AI agent for auto-responses'
    )
    auto_response_enabled = models.BooleanField(default=True)
    human_handoff_enabled = models.BooleanField(default=True)
    
    # Platform-specific metadata (JSON)
    # WhatsApp: quality_rating, messaging_limit_tier, etc
    # Instagram: followers_count, follows_count, media_count, etc
    # Messenger: category, followers_count, etc
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error_message = models.TextField(blank=True)
    
    class Meta:
        db_table = 'platform_accounts'
        verbose_name = 'Platform Account'
        verbose_name_plural = 'Platform Accounts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'platform', 'status']),
            models.Index(fields=['store', 'platform']),
            models.Index(fields=['external_id', 'platform']),
            models.Index(fields=['status', 'is_active']),
        ]
        unique_together = [
            ['platform', 'external_id'],
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_platform_display()})"
    
    # Encrypted token properties
    @property
    def access_token(self) -> str:
        """Decrypt and return the access token."""
        if not self.access_token_encrypted:
            return ''
        return token_encryption.decrypt(self.access_token_encrypted)
    
    @access_token.setter
    def access_token(self, value: str):
        """Encrypt and store the access token."""
        if value:
            self.access_token_encrypted = token_encryption.encrypt(value)
            self.token_version += 1
        else:
            self.access_token_encrypted = ''
    
    @property
    def masked_token(self) -> str:
        """Return masked token for display."""
        if not self.access_token_encrypted:
            return ''
        return mask_token(self.access_token)
    
    def rotate_token(self, new_token: str):
        """Rotate the access token."""
        self.access_token = new_token
        self.save(update_fields=['access_token_encrypted', 'token_version', 'updated_at'])
    
    def set_error(self, message: str):
        """Record an error for this account."""
        self.last_error_message = message
        self.last_error_at = __import__('django.utils.timezone').now()
        self.status = self.Status.ERROR
        self.save(update_fields=['last_error_message', 'last_error_at', 'status', 'updated_at'])
    
    def clear_error(self):
        """Clear error state."""
        self.last_error_message = ''
        self.last_error_at = None
        self.status = self.Status.ACTIVE
        self.save(update_fields=['last_error_message', 'last_error_at', 'status', 'updated_at'])
    
    def mark_verified(self):
        """Mark account as verified."""
        self.is_verified = True
        self.webhook_verified = True
        self.status = self.Status.ACTIVE
        self.save(update_fields=['is_verified', 'webhook_verified', 'status', 'updated_at'])
    
    # Platform-specific helper properties
    @property
    def is_whatsapp(self) -> bool:
        return self.platform == self.PlatformType.WHATSAPP
    
    @property
    def is_instagram(self) -> bool:
        return self.platform == self.PlatformType.INSTAGRAM
    
    @property
    def is_messenger(self) -> bool:
        return self.platform == self.PlatformType.MESSENGER
    
    # WhatsApp-specific helpers
    @property
    def waba_id(self) -> str:
        """Get WABA ID (WhatsApp Business Account ID)."""
        if self.is_whatsapp:
            return self.parent_id
        return ''
    
    @property
    def phone_number_id(self) -> str:
        """Get Phone Number ID (WhatsApp)."""
        if self.is_whatsapp:
            return self.external_id
        return ''
    
    # Instagram-specific helpers
    @property
    def instagram_business_id(self) -> str:
        """Get Instagram Business ID."""
        if self.is_instagram:
            return self.external_id
        return ''
    
    @property
    def facebook_page_id(self) -> str:
        """Get Facebook Page ID (for Instagram)."""
        if self.is_instagram:
            return self.parent_id
        return ''
    
    # Messenger-specific helpers
    @property
    def page_id(self) -> str:
        """Get Page ID (Messenger)."""
        if self.is_messenger:
            return self.external_id
        return ''
    
    @property
    def page_access_token(self) -> str:
        """Get page access token (alias for access_token)."""
        return self.access_token
    
    @page_access_token.setter
    def page_access_token(self, value: str):
        """Set page access token (alias for access_token)."""
        self.access_token = value
    
    # Metadata helpers
    def get_metadata(self, key: str, default=None):
        """Get a metadata value."""
        return self.metadata.get(key, default)
    
    def set_metadata(self, key: str, value):
        """Set a metadata value."""
        self.metadata[key] = value
        self.save(update_fields=['metadata', 'updated_at'])
    
    @property
    def followers_count(self) -> int:
        """Get followers count from metadata."""
        return self.get_metadata('followers_count', 0)
    
    @followers_count.setter
    def followers_count(self, value: int):
        """Set followers count in metadata."""
        self.set_metadata('followers_count', value)
    
    @property
    def quality_rating(self) -> str:
        """Get quality rating (WhatsApp)."""
        return self.get_metadata('quality_rating', '')
    
    @property
    def category(self) -> str:
        """Get category (Messenger)."""
        return self.get_metadata('category', '')
