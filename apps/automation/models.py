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
    Company profile linked to a WhatsApp account AND a Store.
    Contains automation settings only - business data comes from Store.
    
    MIGRATION NOTE: This model is being refactored to be a OneToOne extension
    of Store. Fields company_name, business_type, description, business_hours
    are now read from Store via properties for backward compatibility.
    """
    
    class BusinessType(models.TextChoices):
        RESTAURANT = 'restaurant', 'Restaurante'
        ECOMMERCE = 'ecommerce', 'E-commerce'
        SERVICES = 'services', 'Serviços'
        RETAIL = 'retail', 'Varejo'
        HEALTHCARE = 'healthcare', 'Saúde'
        EDUCATION = 'education', 'Educação'
        OTHER = 'other', 'Outro'

    # Link to WhatsApp account (kept for backward compatibility)
    account = models.OneToOneField(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='company_profile',
        null=True,  # Allow null temporarily for migration
        blank=True
    )
    
    # NEW: Link to Store (source of truth for business data)
    store = models.OneToOneField(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='automation_profile',
        null=True,  # Allow null temporarily for migration
        blank=True
    )
    
    # DEPRECATED: Basic company info - now read from Store via properties
    # These fields will be removed after full migration
    _company_name = models.CharField(max_length=255, db_column='company_name', blank=True)
    _business_type = models.CharField(
        max_length=20,
        choices=BusinessType.choices,
        default=BusinessType.OTHER,
        db_column='business_type'
    )
    _description = models.TextField(blank=True, db_column='description')
    
    # Website and links - can be derived from store or set manually
    website_url = models.URLField(blank=True)
    menu_url = models.URLField(blank=True, help_text="URL do cardápio/catálogo")
    order_url = models.URLField(blank=True, help_text="URL para fazer pedidos")
    
    # DEPRECATED: Business hours - now read from Store via property
    _business_hours = models.JSONField(
        default=dict,
        blank=True,
        db_column='business_hours',
        help_text="DEPRECATED: Use store.operating_hours instead"
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
    
    # AI Agent (Langchain) integration
    use_ai_agent = models.BooleanField(
        default=False,
        help_text="Usar Agente IA (Langchain) para respostas avançadas"
    )
    default_agent = models.ForeignKey(
        'agents.Agent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='company_profiles',
        help_text="Agente IA padrão para respostas automáticas"
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

    # Properties to access Store data (unified interface)
    @property
    def company_name(self):
        """Get company name from Store if available, otherwise from profile."""
        if self.store:
            return self.store.name
        return self._company_name
    
    @company_name.setter
    def company_name(self, value):
        """Set company name (stored in profile for backward compatibility)."""
        self._company_name = value
    
    @property
    def business_type(self):
        """Get business type from Store if available."""
        if self.store:
            # Map store_type to business_type
            mapping = {
                'food': 'restaurant',
                'retail': 'retail',
                'services': 'services',
                'digital': 'ecommerce',
            }
            return mapping.get(self.store.store_type, 'other')
        return self._business_type
    
    @business_type.setter
    def business_type(self, value):
        """Set business type."""
        self._business_type = value
    
    @property
    def description(self):
        """Get description from Store if available."""
        if self.store:
            return self.store.description or ''
        return self._description
    
    @description.setter
    def description(self, value):
        """Set description."""
        self._description = value
    
    @property
    def phone_number(self):
        """Get phone number from Store or WhatsApp account."""
        if self.store:
            return self.store.whatsapp_number or self.store.phone
        return self.account.phone_number
    
    @property
    def email(self):
        """Get email from Store if available."""
        if self.store:
            return self.store.email
        return ''
    
    @property
    def address(self):
        """Get address from Store if available."""
        if self.store:
            return self.store.address
        return ''
    
    @property
    def city(self):
        """Get city from Store if available."""
        if self.store:
            return self.store.city
        return ''
    
    @property
    def state(self):
        """Get state from Store if available."""
        if self.store:
            return self.store.state
        return ''
    
    @property
    def store_slug(self):
        """Get store slug for generating URLs."""
        if self.store:
            return self.store.slug
        return None
    
    def get_menu_url(self):
        """Get menu URL (from store or manual)."""
        if self.menu_url:
            return self.menu_url
        if self.store:
            return f"https://{self.store.slug}.pastita.com.br"
        return ''
    
    def get_order_url(self):
        """Get order URL (from store or manual)."""
        if self.order_url:
            return self.order_url
        if self.store:
            return f"https://{self.store.slug}.pastita.com.br/cardapio"
        return ''
    
    def sync_from_store(self):
        """Sync business data from Store to profile."""
        if not self.store:
            return
        
        # Sync business hours
        if self.store.operating_hours:
            day_map = {
                'monday': 'mon', 'tuesday': 'tue', 'wednesday': 'wed',
                'thursday': 'thu', 'friday': 'fri', 'saturday': 'sat', 'sunday': 'sun'
            }
            business_hours = {}
            for day, hours in self.store.operating_hours.items():
                short_day = day_map.get(day.lower(), day.lower()[:3])
                business_hours[short_day] = {
                    'open': hours.get('open', '09:00'),
                    'close': hours.get('close', '18:00'),
                    'closed': not hours.get('open') or not hours.get('close')
                }
            self.business_hours = business_hours
        
        # Sync URLs if not manually set
        if not self.menu_url:
            self.menu_url = f"https://{self.store.slug}.pastita.com.br"
        if not self.order_url:
            self.order_url = f"https://{self.store.slug}.pastita.com.br/cardapio"
        
        self.save(update_fields=['business_hours', 'menu_url', 'order_url'])

    def __str__(self):
        return f"{self.company_name} ({self.phone_number})"

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
    
    # =========================================================================
    # PROPERTIES: Backward compatibility - read from Store when available
    # =========================================================================
    
    @property
    def company_name(self):
        """Return store name if linked, otherwise legacy field."""
        if self.store_id:
            return self.store.name
        return self._company_name
    
    @company_name.setter
    def company_name(self, value):
        """Set legacy field for backward compatibility."""
        self._company_name = value
    
    @property
    def description(self):
        """Return store description if linked, otherwise legacy field."""
        if self.store_id:
            return self.store.description
        return self._description
    
    @description.setter
    def description(self, value):
        """Set legacy field for backward compatibility."""
        self._description = value
    
    @property
    def business_hours(self):
        """Return store operating_hours if linked, otherwise legacy field."""
        if self.store_id:
            return self.store.operating_hours
        return self._business_hours
    
    @business_hours.setter
    def business_hours(self, value):
        """Set legacy field for backward compatibility."""
        self._business_hours = value
    
    @property
    def business_type(self):
        """Return store store_type if linked, otherwise legacy field."""
        if self.store_id:
            # Map store types to business types
            mapping = {
                'food': 'restaurant',
                'retail': 'retail',
                'services': 'services',
                'digital': 'ecommerce',
                'other': 'other'
            }
            return mapping.get(self.store.store_type, 'other')
        return self._business_type
    
    @business_type.setter
    def business_type(self, value):
        """Set legacy field for backward compatibility."""
        self._business_type = value
    
    def __str__(self):
        """Return string representation."""
        name = self.company_name if self.company_name else "Unnamed"
        phone = self.account.phone_number if self.account_id else "No WhatsApp"
        return f"{name} ({phone})"


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
        FAQ = 'faq', 'Perguntas Frequentes'

        # Cart and checkout
        CART_CREATED = 'cart_created', 'Carrinho Criado'
        CART_ABANDONED = 'cart_abandoned', 'Carrinho Abandonado'
        CART_REMINDER = 'cart_reminder', 'Lembrete de Carrinho'
        CART_REMINDER_30 = 'cart_reminder_30', 'Lembrete Carrinho (30min)'
        CART_REMINDER_2H = 'cart_reminder_2h', 'Lembrete Carrinho (2h)'
        CART_REMINDER_24H = 'cart_reminder_24h', 'Lembrete Carrinho (24h)'

        # Payment
        PIX_GENERATED = 'pix_generated', 'PIX Gerado'
        PIX_REMINDER = 'pix_reminder', 'Lembrete de PIX'
        PIX_EXPIRED = 'pix_expired', 'PIX Expirado'
        PAYMENT_CONFIRMED = 'payment_confirmed', 'Pagamento Confirmado'
        PAYMENT_FAILED = 'payment_failed', 'Pagamento Falhou'
        PAYMENT_REMINDER_1 = 'payment_reminder_1', 'Lembrete Pagamento (30min)'
        PAYMENT_REMINDER_2 = 'payment_reminder_2', 'Lembrete Pagamento (2h)'

        # Order status
        ORDER_RECEIVED = 'order_received', 'Pedido Recebido'
        ORDER_CONFIRMED = 'order_confirmed', 'Pedido Confirmado'
        ORDER_PREPARING = 'order_preparing', 'Pedido em Preparo'
        ORDER_READY = 'order_ready', 'Pedido Pronto'
        ORDER_SHIPPED = 'order_shipped', 'Pedido Enviado'
        ORDER_OUT_FOR_DELIVERY = 'order_out_for_delivery', 'Saiu para Entrega'
        ORDER_DELIVERED = 'order_delivered', 'Pedido Entregue'
        ORDER_CANCELLED = 'order_cancelled', 'Pedido Cancelado'

        # Feedback and Support
        FEEDBACK_REQUEST = 'feedback_request', 'Solicitar Avaliação'
        FEEDBACK_RECEIVED = 'feedback_received', 'Avaliação Recebida'
        HUMAN_HANDOFF = 'human_handoff', 'Transferido para Humano'
        HUMAN_ASSIGNED = 'human_assigned', 'Atendente Atribuído'

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


class IntentLog(BaseModel):
    """
    Log de detecção de intenções para analytics e debugging.
    """

    class MethodType(models.TextChoices):
        REGEX = 'regex', 'Regex'
        LLM = 'llm', 'LLM'
        NONE = 'none', 'Nenhum'

    class ResponseType(models.TextChoices):
        TEXT = 'text', 'Texto'
        BUTTONS = 'buttons', 'Botões'
        LIST = 'list', 'Lista'
        INTERACTIVE = 'interactive', 'Interativo'

    # Relacionamentos
    company = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name='intent_logs'
    )
    message = models.ForeignKey(
        'whatsapp.Message',
        on_delete=models.CASCADE,
        related_name='intent_logs',
        null=True,
        blank=True
    )
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.CASCADE,
        related_name='intent_logs',
        null=True,
        blank=True
    )

    # Dados da mensagem
    phone_number = models.CharField(max_length=20, db_index=True)
    message_text = models.TextField()

    # Dados da intenção detectada
    intent_type = models.CharField(max_length=50, db_index=True)
    method = models.CharField(max_length=10, choices=MethodType.choices, default=MethodType.REGEX)
    confidence = models.FloatField(default=0.0)

    # Handler e resposta
    handler_used = models.CharField(max_length=100, blank=True)
    response_text = models.TextField(blank=True)
    response_type = models.CharField(
        max_length=20,
        choices=ResponseType.choices,
        default=ResponseType.TEXT
    )

    # Performance
    processing_time_ms = models.IntegerField(default=0)

    # Dados extras
    entities = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'intent_logs'
        verbose_name = 'Intent Log'
        verbose_name_plural = 'Intent Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', '-created_at']),
            models.Index(fields=['intent_type', '-created_at']),
            models.Index(fields=['method', '-created_at']),
            models.Index(fields=['phone_number', '-created_at']),
        ]

    def __str__(self):
        return f"{self.phone_number} - {self.intent_type} ({self.method}) - {self.created_at}"


# ============================================================================
# FLOW BUILDER MODELS (POC)
# ============================================================================

class AgentFlow(BaseModel):
    """
    Fluxo de conversação visual (Flow Builder).
    Versão POC: Salva JSON do React Flow.
    """
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='flows')
    
    # JSON vindo do React Flow (nodes, edges, viewport)
    flow_json = models.JSONField(
        default=dict,
        help_text='Estrutura do React Flow: {nodes: [], edges: []}'
    )
    
    # Metadados
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text='Se verdadeiro, é o fluxo padrão da loja'
    )
    version = models.CharField(max_length=10, default='1.0')
    
    # Estatísticas
    total_executions = models.PositiveIntegerField(default=0)
    success_rate = models.FloatField(default=0.0)
    
    class Meta:
        db_table = 'agent_flows'
        ordering = ['-is_default', '-created_at']
        verbose_name = 'Fluxo de Atendimento'
        verbose_name_plural = 'Fluxos de Atendimento'
    
    def __str__(self):
        return f'{self.name} ({self.store.name})'
    
    def set_as_default(self):
        """Define este fluxo como padrão para a loja."""
        AgentFlow.objects.filter(
            store=self.store,
            is_default=True
        ).exclude(id=self.id).update(is_default=False)
        
        self.is_default = True
        self.save()


class FlowSession(BaseModel):
    """
    Estado da sessão de um usuário em um fluxo.
    """
    conversation = models.OneToOneField(
        'conversations.Conversation',
        on_delete=models.CASCADE,
        related_name='flow_session'
    )
    flow = models.ForeignKey(
        AgentFlow,
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    
    current_node_id = models.CharField(max_length=100, null=True, blank=True)
    context = models.JSONField(default=dict, help_text='Variáveis coletadas durante o fluxo')
    node_history = models.JSONField(default=list, help_text='Lista de nós visitados')
    
    is_waiting_input = models.BooleanField(default=False)
    input_type_expected = models.CharField(max_length=50, blank=True)
    
    last_interaction = models.DateTimeField(auto_now=True)
    is_expired = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'flow_sessions'
        verbose_name = 'Sessão de Fluxo'
        verbose_name_plural = 'Sessões de Fluxo'
    
    def __str__(self):
        return f'Sessão {self.conversation.phone_number} em {self.flow.name}'
    
    def reset(self):
        """Reseta a sessão para o início do fluxo."""
        self.current_node_id = None
        self.context = {}
        self.node_history = []
        self.is_waiting_input = False
        self.input_type_expected = ''
        self.save()


class FlowExecutionLog(BaseModel):
    """
    Log de execução para debug e analytics.
    """
    session = models.ForeignKey(
        FlowSession,
        on_delete=models.CASCADE,
        related_name='execution_logs'
    )
    flow = models.ForeignKey(
        AgentFlow,
        on_delete=models.CASCADE,
        related_name='execution_logs'
    )
    node_id = models.CharField(max_length=100)
    node_type = models.CharField(max_length=50)
    
    input_message = models.TextField(blank=True)
    output_message = models.TextField(blank=True)
    context_snapshot = models.JSONField(default=dict)
    
    execution_time_ms = models.PositiveIntegerField(default=0)
    tokens_used = models.PositiveIntegerField(default=0)
    
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        db_table = 'flow_execution_logs'
        ordering = ['-created_at']
        verbose_name = 'Log de Execução'
        verbose_name_plural = 'Logs de Execução'
    
    def __str__(self):
        status = '✅' if self.success else '❌'
        return f'{status} {self.node_type} em {self.flow.name}'
