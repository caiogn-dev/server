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

    account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='scheduled_messages'
    )

    to_number = models.CharField(max_length=20, db_index=True)
    contact_name = models.CharField(max_length=255, blank=True)

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

    content = models.JSONField(default=dict, blank=True, help_text="Additional content data")

    scheduled_at = models.DateTimeField(db_index=True)
    timezone = models.CharField(max_length=50, default='America/Sao_Paulo')

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    sent_at = models.DateTimeField(null=True, blank=True)

    whatsapp_message_id = models.CharField(max_length=255, blank=True)
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)

    is_recurring = models.BooleanField(default=False)
    recurrence_rule = models.CharField(max_length=255, blank=True, help_text="RRULE format")
    next_occurrence = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scheduled_messages'
    )
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    source = models.CharField(
        max_length=20,
        default='manual',
        help_text="Source: manual, campaign, automation, api"
    )
    campaign_id = models.UUIDField(null=True, blank=True, help_text="Related campaign if from campaign")

    class Meta:
        app_label = 'automation'
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
        'automation.CompanyProfile',
        on_delete=models.CASCADE,
        related_name='auto_messages'
    )

    event_type = models.CharField(max_length=30, choices=EventType.choices)
    name = models.CharField(max_length=255, help_text="Nome interno da mensagem")

    message_text = models.TextField(help_text="Texto da mensagem. Use {variáveis} para personalização")

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

    buttons = models.JSONField(
        default=list,
        blank=True,
        help_text="Botões interativos [{'id': 'btn1', 'title': 'Texto'}]"
    )

    is_active = models.BooleanField(default=True)
    delay_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Segundos para esperar antes de enviar"
    )

    conditions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Condições para enviar a mensagem"
    )

    priority = models.PositiveIntegerField(default=100)

    class Meta:
        app_label = 'automation'
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
