"""
Marketing models for Email and WhatsApp campaigns.
"""
import uuid
from django.db import models
from django.contrib.auth import get_user_model
from apps.stores.models import Store

User = get_user_model()


class EmailTemplate(models.Model):
    """Email template model."""
    
    class TemplateType(models.TextChoices):
        COUPON = 'coupon', 'Cupom de Desconto'
        WELCOME = 'welcome', 'Boas-vindas'
        PROMOTION = 'promotion', 'Promoção'
        ABANDONED_CART = 'abandoned_cart', 'Carrinho Abandonado'
        ORDER_CONFIRMATION = 'order_confirmation', 'Confirmação de Pedido'
        NEWSLETTER = 'newsletter', 'Newsletter'
        CUSTOM = 'custom', 'Personalizado'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='email_templates'
    )
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    template_type = models.CharField(
        max_length=30,
        choices=TemplateType.choices,
        default=TemplateType.CUSTOM
    )
    
    # Content
    subject = models.CharField(max_length=255)
    html_content = models.TextField()
    text_content = models.TextField(blank=True)
    
    # Preview
    preview_text = models.CharField(max_length=255, blank=True)
    thumbnail_url = models.URLField(blank=True)
    
    # Variables available in template
    variables = models.JSONField(default=list, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_email_templates'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store', 'template_type']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.template_type})"


class EmailCampaign(models.Model):
    """Email marketing campaign."""
    
    class CampaignStatus(models.TextChoices):
        DRAFT = 'draft', 'Rascunho'
        SCHEDULED = 'scheduled', 'Agendada'
        SENDING = 'sending', 'Enviando'
        SENT = 'sent', 'Enviada'
        PAUSED = 'paused', 'Pausada'
        CANCELLED = 'cancelled', 'Cancelada'
    
    class AudienceType(models.TextChoices):
        ALL = 'all', 'Todos (subscribers + clientes)'
        CUSTOMERS = 'customers', 'Apenas clientes (que fizeram pedidos)'
        SUBSCRIBERS = 'subscribers', 'Apenas subscribers'
        SEGMENT = 'segment', 'Segmento'
        CUSTOM = 'custom', 'Lista personalizada'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='email_campaigns'
    )
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Template
    template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campaigns'
    )
    subject = models.CharField(max_length=255)
    html_content = models.TextField()
    text_content = models.TextField(blank=True)
    
    # Sender
    from_name = models.CharField(max_length=100, blank=True)
    from_email = models.EmailField(blank=True)
    reply_to = models.EmailField(blank=True)
    
    # Audience
    audience_type = models.CharField(
        max_length=20,
        choices=AudienceType.choices,
        default=AudienceType.ALL
    )
    audience_filters = models.JSONField(default=dict, blank=True)
    recipient_list = models.JSONField(default=list, blank=True)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=CampaignStatus.choices,
        default=CampaignStatus.DRAFT
    )
    
    # Scheduling
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Statistics
    total_recipients = models.IntegerField(default=0)
    emails_sent = models.IntegerField(default=0)
    emails_delivered = models.IntegerField(default=0)
    emails_opened = models.IntegerField(default=0)
    emails_clicked = models.IntegerField(default=0)
    emails_bounced = models.IntegerField(default=0)
    emails_unsubscribed = models.IntegerField(default=0)
    
    # Metadata
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_email_campaigns'
    )
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store', 'status']),
            models.Index(fields=['scheduled_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.status})"
    
    @property
    def open_rate(self) -> float:
        if self.emails_delivered == 0:
            return 0
        return (self.emails_opened / self.emails_delivered) * 100
    
    @property
    def click_rate(self) -> float:
        if self.emails_opened == 0:
            return 0
        return (self.emails_clicked / self.emails_opened) * 100


class EmailRecipient(models.Model):
    """Email campaign recipient tracking."""
    
    class RecipientStatus(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        SENT = 'sent', 'Enviado'
        DELIVERED = 'delivered', 'Entregue'
        OPENED = 'opened', 'Aberto'
        CLICKED = 'clicked', 'Clicado'
        BOUNCED = 'bounced', 'Bounce'
        UNSUBSCRIBED = 'unsubscribed', 'Descadastrado'
        FAILED = 'failed', 'Falhou'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        EmailCampaign,
        on_delete=models.CASCADE,
        related_name='recipients'
    )
    
    email = models.EmailField()
    name = models.CharField(max_length=255, blank=True)
    
    status = models.CharField(
        max_length=20,
        choices=RecipientStatus.choices,
        default=RecipientStatus.PENDING
    )
    
    # Resend tracking
    resend_id = models.CharField(max_length=100, blank=True)
    
    # Timing
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    
    # Error tracking
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    
    # Personalization variables
    variables = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['campaign', 'email']
        indexes = [
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['email']),
        ]
    
    def __str__(self):
        return f"{self.email} - {self.status}"


class Subscriber(models.Model):
    """Email subscriber/contact."""
    
    class SubscriberStatus(models.TextChoices):
        ACTIVE = 'active', 'Ativo'
        UNSUBSCRIBED = 'unsubscribed', 'Descadastrado'
        BOUNCED = 'bounced', 'Bounce'
        COMPLAINED = 'complained', 'Reclamação'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='subscribers'
    )
    
    email = models.EmailField()
    name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    
    status = models.CharField(
        max_length=20,
        choices=SubscriberStatus.choices,
        default=SubscriberStatus.ACTIVE
    )
    
    # Segmentation
    tags = models.JSONField(default=list, blank=True)
    custom_fields = models.JSONField(default=dict, blank=True)
    
    # Source
    source = models.CharField(max_length=50, blank=True)  # checkout, popup, import
    
    # Stats
    total_orders = models.IntegerField(default=0)
    total_spent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    last_order_at = models.DateTimeField(null=True, blank=True)
    
    # Preferences
    accepts_marketing = models.BooleanField(default=True)
    
    subscribed_at = models.DateTimeField(auto_now_add=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['store', 'email']
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store', 'status']),
            models.Index(fields=['email']),
        ]
    
    def __str__(self):
        return f"{self.email} ({self.status})"


class EmailAutomation(models.Model):
    """
    Automated email triggers.
    Sends emails automatically when certain events occur.
    """
    
    class TriggerType(models.TextChoices):
        # User lifecycle
        NEW_USER = 'new_user', 'Novo Usuário'
        WELCOME = 'welcome', 'Boas-vindas'
        
        # Order lifecycle
        ORDER_CONFIRMED = 'order_confirmed', 'Pedido Confirmado'
        ORDER_PREPARING = 'order_preparing', 'Pedido em Preparo'
        ORDER_SHIPPED = 'order_shipped', 'Pedido Enviado'
        ORDER_DELIVERED = 'order_delivered', 'Pedido Entregue'
        ORDER_CANCELLED = 'order_cancelled', 'Pedido Cancelado'
        
        # Payment
        PAYMENT_CONFIRMED = 'payment_confirmed', 'Pagamento Confirmado'
        PAYMENT_FAILED = 'payment_failed', 'Pagamento Falhou'
        
        # Cart
        CART_ABANDONED = 'cart_abandoned', 'Carrinho Abandonado'
        
        # Marketing
        COUPON_SENT = 'coupon_sent', 'Cupom Enviado'
        BIRTHDAY = 'birthday', 'Aniversário'
        
        # Feedback
        REVIEW_REQUEST = 'review_request', 'Solicitar Avaliação'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='email_automations'
    )
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    trigger_type = models.CharField(
        max_length=30,
        choices=TriggerType.choices
    )
    
    # Email content
    subject = models.CharField(max_length=255)
    html_content = models.TextField()
    
    # Optional: use a template instead
    template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='automations'
    )
    
    # Timing
    delay_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Minutes to wait before sending (0 = immediate)"
    )
    
    # Conditions
    is_active = models.BooleanField(default=True)
    conditions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional conditions for triggering"
    )
    
    # Stats
    total_sent = models.PositiveIntegerField(default=0)
    total_opened = models.PositiveIntegerField(default=0)
    total_clicked = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    class Meta:
        ordering = ['trigger_type', 'name']
        indexes = [
            models.Index(fields=['store', 'trigger_type', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.store.name} - {self.get_trigger_type_display()}"


class EmailAutomationLog(models.Model):
    """Log of automated emails sent."""
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        SENT = 'sent', 'Enviado'
        FAILED = 'failed', 'Falhou'
        OPENED = 'opened', 'Aberto'
        CLICKED = 'clicked', 'Clicado'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    automation = models.ForeignKey(
        EmailAutomation,
        on_delete=models.CASCADE,
        related_name='logs'
    )
    
    recipient_email = models.EmailField()
    recipient_name = models.CharField(max_length=255, blank=True)
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    
    # Reference to what triggered this
    trigger_data = models.JSONField(default=dict, blank=True)
    
    # Resend tracking
    resend_id = models.CharField(max_length=100, blank=True)
    
    # Timing
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['automation', 'status']),
            models.Index(fields=['recipient_email']),
        ]
    
    def __str__(self):
        return f"{self.recipient_email} - {self.automation.trigger_type}"
