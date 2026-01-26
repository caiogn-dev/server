"""
Instagram models - Instagram accounts, messages, and webhook events.
Uses Meta Graph API for Instagram Messaging.
"""
from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel
from apps.core.utils import token_encryption, mask_token

User = get_user_model()


class InstagramAccount(BaseModel):
    """Instagram Business Account configuration."""
    
    class AccountStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        SUSPENDED = 'suspended', 'Suspended'
        PENDING = 'pending', 'Pending Verification'
        EXPIRED = 'expired', 'Token Expired'

    name = models.CharField(max_length=255, help_text="Display name for this account")
    instagram_account_id = models.CharField(
        max_length=50, 
        unique=True, 
        db_index=True,
        help_text="Instagram Business Account ID (IGBA ID)"
    )
    instagram_user_id = models.CharField(
        max_length=50, 
        db_index=True,
        help_text="Instagram User ID"
    )
    facebook_page_id = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Connected Facebook Page ID"
    )
    username = models.CharField(max_length=100, help_text="Instagram @username")
    
    # App credentials (from Meta Developer Console)
    app_id = models.CharField(max_length=50, help_text="Instagram App ID")
    app_secret_encrypted = models.TextField(help_text="Encrypted App Secret")
    
    # Access token (long-lived)
    access_token_encrypted = models.TextField(help_text="Encrypted access token")
    token_expires_at = models.DateTimeField(null=True, blank=True)
    token_version = models.PositiveIntegerField(default=1)
    
    status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING
    )
    
    # Webhook configuration
    webhook_verify_token = models.CharField(max_length=255, blank=True)
    
    # Features
    messaging_enabled = models.BooleanField(default=True)
    auto_response_enabled = models.BooleanField(default=False)
    human_handoff_enabled = models.BooleanField(default=True)
    
    # Profile info (cached from API)
    profile_picture_url = models.URLField(blank=True)
    followers_count = models.PositiveIntegerField(default=0)
    
    metadata = models.JSONField(default=dict, blank=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='instagram_accounts',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'instagram_accounts'
        verbose_name = 'Instagram Account'
        verbose_name_plural = 'Instagram Accounts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} (@{self.username})"

    @property
    def access_token(self) -> str:
        """Decrypt and return the access token."""
        return token_encryption.decrypt(self.access_token_encrypted)

    @access_token.setter
    def access_token(self, value: str):
        """Encrypt and store the access token."""
        self.access_token_encrypted = token_encryption.encrypt(value)
        self.token_version += 1

    @property
    def app_secret(self) -> str:
        """Decrypt and return the app secret."""
        return token_encryption.decrypt(self.app_secret_encrypted)

    @app_secret.setter
    def app_secret(self, value: str):
        """Encrypt and store the app secret."""
        self.app_secret_encrypted = token_encryption.encrypt(value)

    @property
    def masked_token(self) -> str:
        """Return masked token for display."""
        return mask_token(self.access_token)

    def rotate_token(self, new_token: str):
        """Rotate the access token."""
        self.access_token = new_token
        self.save(update_fields=['access_token_encrypted', 'token_version', 'updated_at'])


class InstagramConversation(BaseModel):
    """Instagram DM conversation thread."""
    
    class ConversationStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        CLOSED = 'closed', 'Closed'
        ARCHIVED = 'archived', 'Archived'

    account = models.ForeignKey(
        InstagramAccount,
        on_delete=models.CASCADE,
        related_name='conversations'
    )
    
    # Instagram user info
    participant_id = models.CharField(max_length=50, db_index=True)
    participant_username = models.CharField(max_length=100, blank=True)
    participant_name = models.CharField(max_length=255, blank=True)
    participant_profile_pic = models.URLField(blank=True)
    
    status = models.CharField(
        max_length=20,
        choices=ConversationStatus.choices,
        default=ConversationStatus.ACTIVE
    )
    
    # Stats
    message_count = models.PositiveIntegerField(default=0)
    last_message_at = models.DateTimeField(null=True, blank=True)
    last_message_preview = models.CharField(max_length=255, blank=True)
    
    # Agent/Support
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_ig_conversations'
    )
    
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'instagram_conversations'
        verbose_name = 'Instagram Conversation'
        verbose_name_plural = 'Instagram Conversations'
        ordering = ['-last_message_at']
        unique_together = ['account', 'participant_id']
        indexes = [
            models.Index(fields=['account', 'status', '-last_message_at']),
        ]

    def __str__(self):
        return f"@{self.participant_username or self.participant_id}"


class InstagramMessage(BaseModel):
    """Instagram DM message."""
    
    class MessageType(models.TextChoices):
        TEXT = 'text', 'Text'
        IMAGE = 'image', 'Image'
        VIDEO = 'video', 'Video'
        AUDIO = 'audio', 'Audio'
        FILE = 'file', 'File'
        SHARE = 'share', 'Share (Post/Reel/Story)'
        STORY_MENTION = 'story_mention', 'Story Mention'
        STORY_REPLY = 'story_reply', 'Story Reply'
        REACTION = 'reaction', 'Reaction'
        DELETED = 'deleted', 'Deleted'
        UNKNOWN = 'unknown', 'Unknown'

    class MessageDirection(models.TextChoices):
        INBOUND = 'inbound', 'Inbound (received)'
        OUTBOUND = 'outbound', 'Outbound (sent)'

    class MessageStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        DELIVERED = 'delivered', 'Delivered'
        SEEN = 'seen', 'Seen'
        FAILED = 'failed', 'Failed'

    account = models.ForeignKey(
        InstagramAccount,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    conversation = models.ForeignKey(
        InstagramConversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    
    # Instagram message ID
    instagram_message_id = models.CharField(max_length=100, unique=True, db_index=True)
    
    direction = models.CharField(max_length=10, choices=MessageDirection.choices)
    message_type = models.CharField(max_length=20, choices=MessageType.choices)
    status = models.CharField(
        max_length=20,
        choices=MessageStatus.choices,
        default=MessageStatus.PENDING
    )
    
    # Participants
    sender_id = models.CharField(max_length=50, db_index=True)
    recipient_id = models.CharField(max_length=50, db_index=True)
    
    # Content
    text_content = models.TextField(blank=True)
    
    # Media attachments
    media_url = models.URLField(blank=True)
    media_type = models.CharField(max_length=50, blank=True)
    
    # For shares (posts, reels, stories)
    shared_media_id = models.CharField(max_length=100, blank=True)
    shared_media_url = models.URLField(blank=True)
    
    # Reply context
    reply_to_message_id = models.CharField(max_length=100, blank=True)
    
    # Timestamps
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    seen_at = models.DateTimeField(null=True, blank=True)
    
    # Error handling
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'instagram_messages'
        verbose_name = 'Instagram Message'
        verbose_name_plural = 'Instagram Messages'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['conversation', '-created_at']),
            models.Index(fields=['account', 'sender_id', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.direction}: {self.sender_id} -> {self.recipient_id} ({self.message_type})"


class InstagramWebhookEvent(BaseModel):
    """Webhook event log for idempotency and debugging."""
    
    class EventType(models.TextChoices):
        MESSAGES = 'messages', 'Messages'
        MESSAGING_POSTBACKS = 'messaging_postbacks', 'Messaging Postbacks'
        MESSAGING_SEEN = 'messaging_seen', 'Messaging Seen'
        MESSAGING_REFERRAL = 'messaging_referral', 'Messaging Referral'
        COMMENTS = 'comments', 'Comments'
        UNKNOWN = 'unknown', 'Unknown'

    class ProcessingStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        DUPLICATE = 'duplicate', 'Duplicate'

    account = models.ForeignKey(
        InstagramAccount,
        on_delete=models.CASCADE,
        related_name='webhook_events',
        null=True,
        blank=True
    )
    
    event_id = models.CharField(max_length=100, unique=True, db_index=True)
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING
    )
    
    payload = models.JSONField()
    headers = models.JSONField(default=dict)
    
    processed_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    
    related_message = models.ForeignKey(
        InstagramMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhook_events'
    )

    class Meta:
        db_table = 'instagram_webhook_events'
        verbose_name = 'Instagram Webhook Event'
        verbose_name_plural = 'Instagram Webhook Events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['processing_status', '-created_at']),
            models.Index(fields=['event_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.event_type}: {self.event_id} ({self.processing_status})"
