"""
Automation models - Company profiles, auto messages, customer sessions, scheduled messages, and reports.
"""
from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel

User = get_user_model()


class ScheduledMessage(BaseModel):
    """
    Scheduled messages for future delivery.
    This is the unified model for all scheduled WhatsApp messages.
    Used by both automation and campaigns apps.
    """
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        PROCESSING = 'processing', 'Processando'
        SENT = 'sent', 'Enviado'
        FAILED = 'failed', 'Falhou'
        CANCELLED = 'cancelled', 'Cancelado'
    
    class MessageType(models.TextChoices):
        TEXT = 'text', 'Texto'
        TEMPLATE = 'template', 'Template'
        IMAGE = 'image', 'Imagem'
        DOCUMENT = 'document', 'Documento'
        INTERACTIVE = 'interactive', 'Interativo'
    
    # Link to WhatsApp account
    account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='scheduled_messages'
    )
    
    # Recipient
    to_number = models.CharField(max_length=20, db_index=True)
    contact_name = models.CharField(max_length=255, blank=True)
    
    # Message content
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.TEXT
    )
    message_text = models.TextField(blank=True)
    template_name = models.CharField(max_length=255, blank=True)
    template_language = models.CharField(max_length=10, default='pt_BR')
    template_components = models.JSONField(default=list, blank=True)
    media_url = models.URLField(blank=True)
    buttons = models.JSONField(default=list, blank=True)
    
    # Additional content field for flexibility (used by campaigns)
    content = models.JSONField(default=dict, blank=True, help_text="Additional content data")
    
    # Scheduling
    scheduled_at = models.DateTimeField(db_index=True)
    timezone = models.CharField(max_length=50, default='America/Sao_Paulo')
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    
    # Result
    whatsapp_message_id = models.CharField(max_length=255, blank=True)
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    
    # Recurrence support
    is_recurring = models.BooleanField(default=False)
    recurrence_rule = models.CharField(max_length=255, blank=True, help_text="RRULE format")
    next_occurrence = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scheduled_messages'
    )
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Source tracking
    source = models.CharField(
        max_length=20,
        default='manual',
        help_text="Source: manual, campaign, automation, api"
    )
    campaign_id = models.UUIDField(null=True, blank=True, help_text="Related campaign if from campaign")

    class Meta:
        db_table = 'scheduled_messages'
        verbose_name = 'Scheduled Message'
        verbose_name_plural = 'Scheduled Messages'
        ordering = ['scheduled_at']
        indexes = [
            models.Index(fields=['account', 'status', 'scheduled_at']),
            models.Index(fields=['status', 'scheduled_at']),
            models.Index(fields=['source', 'status']),
        ]

    def __str__(self):
        return f"{self.to_number} - {self.scheduled_at} ({self.status})"
    
    def get_message_content(self) -> dict:
        """Get message content in a unified format."""
        if self.message_type == self.MessageType.TEXT:
            return {'text': self.message_text}
        elif self.message_type == self.MessageType.TEMPLATE:
            return {
                'template_name': self.template_name,
                'language': self.template_language,
                'components': self.template_components,
            }
        elif self.message_type == self.MessageType.IMAGE:
            return {'image_url': self.media_url, 'caption': self.message_text}
        elif self.message_type == self.MessageType.DOCUMENT:
            return {'document_url': self.media_url, 'caption': self.message_text}
        elif self.message_type == self.MessageType.INTERACTIVE:
            return {'body_text': self.message_text, 'buttons': self.buttons}
        return self.content or {}


class ReportSchedule(BaseModel):
    """
    Scheduled automated reports.
    """
    
    class Frequency(models.TextChoices):
        DAILY = 'daily', 'Diário'
        WEEKLY = 'weekly', 'Semanal'
        MONTHLY = 'monthly', 'Mensal'
    
    class ReportType(models.TextChoices):
        MESSAGES = 'messages', 'Mensagens'
        ORDERS = 'orders', 'Pedidos'
        CONVERSATIONS = 'conversations', 'Conversas'
        AUTOMATION = 'automation', 'Automação'
        PAYMENTS = 'payments', 'Pagamentos'
        FULL = 'full', 'Completo'
    
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Ativo'
        PAUSED = 'paused', 'Pausado'
        DISABLED = 'disabled', 'Desativado'
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Report configuration
    report_type = models.CharField(
        max_length=20,
        choices=ReportType.choices,
        default=ReportType.FULL
    )
    
    # Filters
    account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='report_schedules',
        help_text="Filter by account (optional)"
    )
    company = models.ForeignKey(
        'automation.CompanyProfile',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='report_schedules',
        help_text="Filter by company (optional)"
    )
    
    # Schedule
    frequency = models.CharField(
        max_length=20,
        choices=Frequency.choices,
        default=Frequency.WEEKLY
    )
    day_of_week = models.PositiveSmallIntegerField(
        default=1,
        help_text="Day of week for weekly reports (1=Monday, 7=Sunday)"
    )
    day_of_month = models.PositiveSmallIntegerField(
        default=1,
        help_text="Day of month for monthly reports"
    )
    hour = models.PositiveSmallIntegerField(
        default=8,
        help_text="Hour to send report (0-23)"
    )
    timezone = models.CharField(max_length=50, default='America/Sao_Paulo')
    
    # Recipients
    recipients = models.JSONField(
        default=list,
        help_text="List of email addresses to send report to"
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    
    # Tracking
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    run_count = models.PositiveIntegerField(default=0)
    
    # Owner
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='report_schedules'
    )
    
    # Additional settings
    include_charts = models.BooleanField(default=True)
    export_format = models.CharField(
        max_length=10,
        default='xlsx',
        choices=[('csv', 'CSV'), ('xlsx', 'Excel')]
    )
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'report_schedules'
        verbose_name = 'Report Schedule'
        verbose_name_plural = 'Report Schedules'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()})"

    def calculate_next_run(self):
        """Calculate the next run time based on frequency."""
        from django.utils import timezone as tz
        from datetime import timedelta
        import pytz
        
        local_tz = pytz.timezone(self.timezone)
        now = tz.now().astimezone(local_tz)
        
        if self.frequency == self.Frequency.DAILY:
            next_run = now.replace(hour=self.hour, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
        
        elif self.frequency == self.Frequency.WEEKLY:
            days_ahead = self.day_of_week - now.isoweekday()
            if days_ahead < 0 or (days_ahead == 0 and now.hour >= self.hour):
                days_ahead += 7
            next_run = now.replace(hour=self.hour, minute=0, second=0, microsecond=0)
            next_run += timedelta(days=days_ahead)
        
        elif self.frequency == self.Frequency.MONTHLY:
            next_run = now.replace(day=self.day_of_month, hour=self.hour, minute=0, second=0, microsecond=0)
            if next_run <= now:
                # Move to next month
                if now.month == 12:
                    next_run = next_run.replace(year=now.year + 1, month=1)
                else:
                    next_run = next_run.replace(month=now.month + 1)
        
        self.next_run_at = next_run.astimezone(pytz.UTC)
        return self.next_run_at


class GeneratedReport(BaseModel):
    """
    Generated report files.
    """
    
    class Status(models.TextChoices):
        GENERATING = 'generating', 'Gerando'
        COMPLETED = 'completed', 'Concluído'
        FAILED = 'failed', 'Falhou'
    
    schedule = models.ForeignKey(
        ReportSchedule,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='generated_reports'
    )
    
    name = models.CharField(max_length=255)
    report_type = models.CharField(max_length=20)
    
    # Period
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.GENERATING
    )
    
    # File
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    file_format = models.CharField(max_length=10, default='xlsx')
    
    # Stats
    records_count = models.PositiveIntegerField(default=0)
    generation_time_ms = models.PositiveIntegerField(default=0)
    
    # Error
    error_message = models.TextField(blank=True)
    
    # Email
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_recipients = models.JSONField(default=list, blank=True)
    
    # Owner
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_reports'
    )

    class Meta:
        db_table = 'generated_reports'
        verbose_name = 'Generated Report'
        verbose_name_plural = 'Generated Reports'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.created_at.strftime('%Y-%m-%d')})"


class CompanyProfile(BaseModel):
    """
    Company profile linked to a WhatsApp account.
    Contains all business information and automation settings.
    """
    
    class BusinessType(models.TextChoices):
        RESTAURANT = 'restaurant', 'Restaurante'
        ECOMMERCE = 'ecommerce', 'E-commerce'
        SERVICES = 'services', 'Serviços'
        RETAIL = 'retail', 'Varejo'
        HEALTHCARE = 'healthcare', 'Saúde'
        EDUCATION = 'education', 'Educação'
        OTHER = 'other', 'Outro'

    # Link to WhatsApp account
    account = models.OneToOneField(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='company_profile'
    )
    
    # Basic company info
    company_name = models.CharField(max_length=255)
    business_type = models.CharField(
        max_length=20,
        choices=BusinessType.choices,
        default=BusinessType.OTHER
    )
    description = models.TextField(blank=True)
    
    # Website and links
    website_url = models.URLField(blank=True)
    menu_url = models.URLField(blank=True, help_text="URL do cardápio/catálogo")
    order_url = models.URLField(blank=True, help_text="URL para fazer pedidos")
    
    # Business hours (JSON format)
    business_hours = models.JSONField(
        default=dict,
        blank=True,
        help_text="Horário de funcionamento por dia da semana"
    )
    
    # Automation settings
    auto_reply_enabled = models.BooleanField(default=True)
    welcome_message_enabled = models.BooleanField(default=True)
    menu_auto_send = models.BooleanField(
        default=True,
        help_text="Enviar cardápio automaticamente na primeira mensagem"
    )
    
    # Notification settings
    abandoned_cart_notification = models.BooleanField(default=True)
    abandoned_cart_delay_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Minutos para esperar antes de notificar carrinho abandonado"
    )
    
    pix_notification_enabled = models.BooleanField(default=True)
    payment_confirmation_enabled = models.BooleanField(default=True)
    order_status_notification_enabled = models.BooleanField(default=True)
    delivery_notification_enabled = models.BooleanField(default=True)
    
    # Integration settings
    external_api_key = models.CharField(
        max_length=255,
        blank=True,
        help_text="API key para o site externo se conectar"
    )
    webhook_secret = models.CharField(
        max_length=255,
        blank=True,
        help_text="Secret para validar webhooks do site"
    )
    
    # Langflow integration (optional)
    use_langflow = models.BooleanField(
        default=False,
        help_text="Usar Langflow para respostas avançadas"
    )
    langflow_flow_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="ID do flow no Langflow"
    )
    
    # Custom settings
    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configurações personalizadas"
    )

    class Meta:
        db_table = 'company_profiles'
        verbose_name = 'Company Profile'
        verbose_name_plural = 'Company Profiles'

    def __str__(self):
        return f"{self.company_name} ({self.account.phone_number})"

    def generate_api_key(self):
        """Generate a new API key for external integrations."""
        import secrets
        self.external_api_key = secrets.token_urlsafe(32)
        self.save(update_fields=['external_api_key'])
        return self.external_api_key

    def generate_webhook_secret(self):
        """Generate a new webhook secret."""
        import secrets
        self.webhook_secret = secrets.token_urlsafe(32)
        self.save(update_fields=['webhook_secret'])
        return self.webhook_secret


class AutoMessage(BaseModel):
    """
    Automated message templates for different events.
    Each company can customize messages for each event type.
    """
    
    class EventType(models.TextChoices):
        # Welcome and general
        WELCOME = 'welcome', 'Boas-vindas'
        MENU = 'menu', 'Cardápio/Catálogo'
        BUSINESS_HOURS = 'business_hours', 'Horário de Funcionamento'
        OUT_OF_HOURS = 'out_of_hours', 'Fora do Horário'
        
        # Cart and checkout
        CART_CREATED = 'cart_created', 'Carrinho Criado'
        CART_ABANDONED = 'cart_abandoned', 'Carrinho Abandonado'
        CART_REMINDER = 'cart_reminder', 'Lembrete de Carrinho'
        
        # Payment
        PIX_GENERATED = 'pix_generated', 'PIX Gerado'
        PIX_REMINDER = 'pix_reminder', 'Lembrete de PIX'
        PIX_EXPIRED = 'pix_expired', 'PIX Expirado'
        PAYMENT_CONFIRMED = 'payment_confirmed', 'Pagamento Confirmado'
        PAYMENT_FAILED = 'payment_failed', 'Pagamento Falhou'
        
        # Order status
        ORDER_CONFIRMED = 'order_confirmed', 'Pedido Confirmado'
        ORDER_PREPARING = 'order_preparing', 'Pedido em Preparo'
        ORDER_READY = 'order_ready', 'Pedido Pronto'
        ORDER_SHIPPED = 'order_shipped', 'Pedido Enviado'
        ORDER_OUT_FOR_DELIVERY = 'order_out_for_delivery', 'Saiu para Entrega'
        ORDER_DELIVERED = 'order_delivered', 'Pedido Entregue'
        ORDER_CANCELLED = 'order_cancelled', 'Pedido Cancelado'
        
        # Feedback
        FEEDBACK_REQUEST = 'feedback_request', 'Solicitar Avaliação'
        
        # Custom
        CUSTOM = 'custom', 'Personalizado'

    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name='auto_messages'
    )
    
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    name = models.CharField(max_length=255, help_text="Nome interno da mensagem")
    
    # Message content
    message_text = models.TextField(help_text="Texto da mensagem. Use {variáveis} para personalização")
    
    # Optional media
    media_url = models.URLField(blank=True, help_text="URL de imagem/documento para enviar junto")
    media_type = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ('image', 'Imagem'),
            ('document', 'Documento'),
            ('video', 'Vídeo'),
        ]
    )
    
    # Interactive buttons (optional)
    buttons = models.JSONField(
        default=list,
        blank=True,
        help_text="Botões interativos [{'id': 'btn1', 'title': 'Texto'}]"
    )
    
    # Scheduling
    is_active = models.BooleanField(default=True)
    delay_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Segundos para esperar antes de enviar"
    )
    
    # Conditions
    conditions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Condições para enviar a mensagem"
    )
    
    # Priority (lower = higher priority)
    priority = models.PositiveIntegerField(default=100)

    class Meta:
        db_table = 'auto_messages'
        verbose_name = 'Auto Message'
        verbose_name_plural = 'Auto Messages'
        ordering = ['company', 'event_type', 'priority']
        unique_together = ['company', 'event_type', 'name']

    def __str__(self):
        return f"{self.company.company_name} - {self.get_event_type_display()}"

    def render_message(self, context: dict) -> str:
        """Render message with context variables."""
        message = self.message_text
        for key, value in context.items():
            message = message.replace(f"{{{key}}}", str(value))
        return message


class CustomerSession(BaseModel):
    """
    Track customer session between website and WhatsApp.
    Links cart, orders, and payments to a customer.
    """
    
    class SessionStatus(models.TextChoices):
        ACTIVE = 'active', 'Ativa'
        CART_CREATED = 'cart_created', 'Carrinho Criado'
        CART_ABANDONED = 'cart_abandoned', 'Carrinho Abandonado'
        CHECKOUT = 'checkout', 'Em Checkout'
        PAYMENT_PENDING = 'payment_pending', 'Aguardando Pagamento'
        PAYMENT_CONFIRMED = 'payment_confirmed', 'Pagamento Confirmado'
        ORDER_PLACED = 'order_placed', 'Pedido Realizado'
        COMPLETED = 'completed', 'Concluída'
        EXPIRED = 'expired', 'Expirada'

    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name='customer_sessions'
    )
    
    # Customer identification
    phone_number = models.CharField(max_length=20, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True)
    customer_email = models.EmailField(blank=True)
    
    # Session tracking
    session_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="ID da sessão no site externo"
    )
    external_customer_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="ID do cliente no site externo"
    )
    
    status = models.CharField(
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.ACTIVE
    )
    
    # Cart data
    cart_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Dados do carrinho"
    )
    cart_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    cart_items_count = models.PositiveIntegerField(default=0)
    cart_created_at = models.DateTimeField(null=True, blank=True)
    cart_updated_at = models.DateTimeField(null=True, blank=True)
    
    # Payment data
    pix_code = models.TextField(blank=True)
    pix_qr_code = models.TextField(blank=True)
    pix_expires_at = models.DateTimeField(null=True, blank=True)
    payment_id = models.CharField(max_length=100, blank=True)
    
    # Order reference
    order = models.ForeignKey(
        'stores.StoreOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_sessions'
    )
    external_order_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="ID do pedido no site externo"
    )
    
    # Conversation link
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_sessions'
    )
    
    # Notification tracking
    notifications_sent = models.JSONField(
        default=list,
        blank=True,
        help_text="Lista de notificações enviadas"
    )
    last_notification_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    last_activity_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'customer_sessions'
        verbose_name = 'Customer Session'
        verbose_name_plural = 'Customer Sessions'
        ordering = ['-last_activity_at']
        indexes = [
            models.Index(fields=['company', 'phone_number', '-created_at']),
            models.Index(fields=['session_id']),
            models.Index(fields=['status', '-last_activity_at']),
        ]

    def __str__(self):
        return f"{self.phone_number} - {self.status} ({self.company.company_name})"

    def add_notification(self, notification_type: str):
        """Record that a notification was sent."""
        from django.utils import timezone
        self.notifications_sent.append({
            'type': notification_type,
            'sent_at': timezone.now().isoformat()
        })
        self.last_notification_at = timezone.now()
        self.save(update_fields=['notifications_sent', 'last_notification_at'])

    def was_notification_sent(self, notification_type: str) -> bool:
        """Check if a notification type was already sent."""
        return any(n['type'] == notification_type for n in self.notifications_sent)


class AutomationLog(BaseModel):
    """
    Log of all automation actions for debugging and analytics.
    """
    
    class ActionType(models.TextChoices):
        MESSAGE_RECEIVED = 'message_received', 'Mensagem Recebida'
        MESSAGE_SENT = 'message_sent', 'Mensagem Enviada'
        WEBHOOK_RECEIVED = 'webhook_received', 'Webhook Recebido'
        SESSION_CREATED = 'session_created', 'Sessão Criada'
        SESSION_UPDATED = 'session_updated', 'Sessão Atualizada'
        NOTIFICATION_SENT = 'notification_sent', 'Notificação Enviada'
        ERROR = 'error', 'Erro'

    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name='automation_logs'
    )
    session = models.ForeignKey(
        CustomerSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs'
    )
    
    action_type = models.CharField(max_length=30, choices=ActionType.choices)
    description = models.TextField()
    
    # Related data
    phone_number = models.CharField(max_length=20, blank=True)
    event_type = models.CharField(max_length=50, blank=True)
    
    # Request/Response data
    request_data = models.JSONField(default=dict, blank=True)
    response_data = models.JSONField(default=dict, blank=True)
    
    # Error tracking
    is_error = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'automation_logs'
        verbose_name = 'Automation Log'
        verbose_name_plural = 'Automation Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', '-created_at']),
            models.Index(fields=['action_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.company.company_name} - {self.action_type} - {self.created_at}"
