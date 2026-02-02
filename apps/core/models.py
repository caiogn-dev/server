"""
Core models - Base models for the application.
"""
import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()


class BaseModel(models.Model):
    """Abstract base model with common fields."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


class TimestampedModel(models.Model):
    """Abstract model with timestamp fields only."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseMessageModel(BaseModel):
    """
    Abstract base model for messaging platforms (WhatsApp, Instagram, etc.).
    Provides common fields for messages across different platforms.
    """
    
    class MessageDirection(models.TextChoices):
        INBOUND = 'inbound', 'Inbound'
        OUTBOUND = 'outbound', 'Outbound'
    
    class MessageStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        DELIVERED = 'delivered', 'Delivered'
        READ = 'read', 'Read'
        FAILED = 'failed', 'Failed'
    
    class MessageType(models.TextChoices):
        TEXT = 'text', 'Text'
        IMAGE = 'image', 'Image'
        VIDEO = 'video', 'Video'
        AUDIO = 'audio', 'Audio'
        DOCUMENT = 'document', 'Document'
        LOCATION = 'location', 'Location'
        CONTACT = 'contact', 'Contact'
        INTERACTIVE = 'interactive', 'Interactive'
        TEMPLATE = 'template', 'Template'
    
    # Message metadata
    direction = models.CharField(
        max_length=10,
        choices=MessageDirection.choices,
        db_index=True
    )
    status = models.CharField(
        max_length=20,
        choices=MessageStatus.choices,
        default=MessageStatus.PENDING,
        db_index=True
    )
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.TEXT
    )
    
    # Content
    text_content = models.TextField(blank=True)
    media_url = models.URLField(blank=True)
    media_caption = models.TextField(blank=True)
    
    # External platform IDs
    external_message_id = models.CharField(max_length=100, blank=True, db_index=True)
    
    # Timestamps
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Error tracking
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        abstract = True
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['external_message_id']),
        ]


class UserProfile(models.Model):
    """Extended user profile with additional fields for e-commerce."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    phone = models.CharField(max_length=20, blank=True)
    cpf = models.CharField(max_length=14, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_profiles'
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"Profile of {self.user.email}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create UserProfile when a new User is created."""
    if created:
        UserProfile.objects.get_or_create(user=instance)


# ============================================
# Multi-Tenant Models
# ============================================


class TenantModel(models.Model):
    """
    Abstract base model for all multi-tenant models.
    
    Every model that belongs to a tenant should inherit from this.
    Provides automatic tenant filtering and isolation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='%(class)s_set',
        help_text='The tenant/store this record belongs to'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created'
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_updated'
    )
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['tenant', 'updated_at']),
        ]


class TenantQuerySet(models.QuerySet):
    """
    QuerySet that automatically filters by tenant.
    """
    
    def for_tenant(self, tenant):
        """Filter by specific tenant."""
        return self.filter(tenant=tenant)
    
    def for_request(self, request):
        """Filter by tenant from request."""
        if hasattr(request, 'tenant') and request.tenant:
            return self.filter(tenant=request.tenant)
        return self.none()


class TenantManager(models.Manager):
    """
    Manager that returns TenantQuerySet.
    """
    
    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)
    
    def for_tenant(self, tenant):
        return self.get_queryset().for_tenant(tenant)
    
    def for_request(self, request):
        return self.get_queryset().for_request(request)
