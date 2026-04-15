"""
Unified Template model.

Replaces:
- whatsapp.MessageTemplate
- messaging_v2.MessageTemplate
- marketing_v2.Template
"""

import uuid
from django.db import models
from apps.core.models import BaseModel


class UnifiedTemplate(BaseModel):
    """
    Unified message template model.
    
    Supports templates for WhatsApp, and generic templates for other platforms.
    """
    
    class PlatformType(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        INSTAGRAM = 'instagram', 'Instagram'
        MESSENGER = 'messenger', 'Messenger'
        EMAIL = 'email', 'Email'
        SMS = 'sms', 'SMS'
    
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PENDING = 'pending', 'Pending Approval'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        PAUSED = 'paused', 'Paused'
    
    class Category(models.TextChoices):
        MARKETING = 'marketing', 'Marketing'
        UTILITY = 'utility', 'Utility'
        AUTHENTICATION = 'authentication', 'Authentication'
        CUSTOM = 'custom', 'Custom'
    
    class TemplateType(models.TextChoices):
        STANDARD = 'standard', 'Standard'
        CAROUSEL = 'carousel', 'Carousel'
        LTO = 'lto', 'Limited Time Offer'
        AUTH = 'auth', 'Authentication'
        ORDER = 'order', 'Order Details'
        CATALOG = 'catalog', 'Catalog'
    
    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    platform_account = models.ForeignKey(
        'messaging.PlatformAccount',
        on_delete=models.CASCADE,
        related_name='templates',
        null=True,
        blank=True,
        help_text='Associated platform account (for WhatsApp)'
    )
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='templates',
        null=True,
        blank=True
    )
    
    # Identification
    name = models.CharField(max_length=255)
    platform = models.CharField(
        max_length=20,
        choices=PlatformType.choices,
        default=PlatformType.WHATSAPP
    )
    template_type = models.CharField(
        max_length=20,
        choices=TemplateType.choices,
        default=TemplateType.STANDARD
    )
    
    # External ID (from platform)
    external_id = models.CharField(
        max_length=255,
        blank=True,
        help_text='Template ID from platform (e.g., Meta template ID)'
    )
    
    # Language
    language = models.CharField(max_length=10, default='pt_BR')
    
    # Category (for WhatsApp)
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.UTILITY
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    
    # Content
    header = models.JSONField(
        default=dict,
        blank=True,
        help_text='Header content (text, image, video, document)'
    )
    body = models.TextField(
        help_text='Main message body with {{variables}}'
    )
    footer = models.TextField(blank=True)
    
    # Buttons
    buttons = models.JSONField(
        default=list,
        blank=True,
        help_text='Button definitions'
    )
    
    # Full components (for WhatsApp API format)
    components = models.JSONField(
        default=list,
        blank=True,
        help_text='Full components in Meta API format'
    )
    
    # Variables
    variables = models.JSONField(
        default=list,
        blank=True,
        help_text='List of variable names used in template'
    )
    
    # Sample values (for submission)
    sample_values = models.JSONField(
        default=dict,
        blank=True,
        help_text='Sample values for variables'
    )
    
    # Rejection reason
    rejection_reason = models.TextField(blank=True)
    
    # Version control
    version = models.CharField(max_length=10, default='1.0')
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'unified_templates'
        verbose_name = 'Message Template'
        verbose_name_plural = 'Message Templates'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['platform_account', 'status']),
            models.Index(fields=['store', 'platform']),
            models.Index(fields=['name', 'language']),
            models.Index(fields=['status', 'category']),
            models.Index(fields=['external_id']),
        ]
        unique_together = [
            ['platform_account', 'name', 'language'],
        ]
    
    def __str__(self):
        return f"{self.name} ({self.language}) - {self.get_status_display()}"
    
    @property
    def is_approved(self) -> bool:
        return self.status == self.Status.APPROVED
    
    @property
    def is_rejected(self) -> bool:
        return self.status == self.Status.REJECTED
    
    @property
    def is_pending(self) -> bool:
        return self.status == self.Status.PENDING
    
    def mark_approved(self, external_id: str = None):
        """Mark template as approved."""
        self.status = self.Status.APPROVED
        self.approved_at = __import__('django.utils.timezone').now()
        if external_id:
            self.external_id = external_id
        self.save(update_fields=['status', 'approved_at', 'external_id', 'updated_at'])
    
    def mark_rejected(self, reason: str = None):
        """Mark template as rejected."""
        self.status = self.Status.REJECTED
        if reason:
            self.rejection_reason = reason
        self.save(update_fields=['status', 'rejection_reason', 'updated_at'])
    
    def mark_submitted(self):
        """Mark template as submitted for approval."""
        self.status = self.Status.PENDING
        self.submitted_at = __import__('django.utils.timezone').now()
        self.save(update_fields=['status', 'submitted_at', 'updated_at'])
    
    def render(self, variables: dict = None) -> str:
        """
        Render template with variables.
        
        Args:
            variables: Dictionary of variable values
            
        Returns:
            Rendered message text
        """
        if not variables:
            variables = {}
        
        text = self.body
        for key, value in variables.items():
            text = text.replace(f'{{{key}}}', str(value))
            text = text.replace(f'{{{{ {key} }}}}', str(value))
        return text
    
    def get_components_for_api(self, variables: dict = None) -> list:
        """
        Get components in Meta API format.
        
        Args:
            variables: Dictionary of variable values
            
        Returns:
            List of components for Meta API
        """
        if self.components:
            # If full components are stored, use them
            return self.components
        
        # Build components from parts
        components = []
        
        # Header
        if self.header:
            components.append({
                'type': 'HEADER',
                'format': self.header.get('format', 'TEXT'),
                **self.header
            })
        
        # Body
        body_text = self.render(variables)
        components.append({
            'type': 'BODY',
            'text': body_text
        })
        
        # Footer
        if self.footer:
            components.append({
                'type': 'FOOTER',
                'text': self.footer
            })
        
        # Buttons
        if self.buttons:
            components.append({
                'type': 'BUTTONS',
                'buttons': self.buttons
            })
        
        return components
