"""
WhatsApp models - WhatsApp accounts, messages, and webhook events.
"""
from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel
from apps.core.utils import token_encryption, mask_token

User = get_user_model()


class WhatsAppAccount(BaseModel):
    """WhatsApp Business Account configuration."""
    
    class AccountStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        SUSPENDED = 'suspended', 'Suspended'
        PENDING = 'pending', 'Pending Verification'

    name = models.CharField(max_length=255)
    phone_number_id = models.CharField(max_length=50, unique=True, db_index=True)
    waba_id = models.CharField(max_length=50, db_index=True)
    phone_number = models.CharField(max_length=20)
    display_phone_number = models.CharField(max_length=30, blank=True)
    
    access_token_encrypted = models.TextField()
    token_expires_at = models.DateTimeField(null=True, blank=True)
    token_version = models.PositiveIntegerField(default=1)
    
    status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING
    )
    
    webhook_verify_token = models.CharField(max_length=255, blank=True)
    
    # AI Agent (Langchain) configuration
    default_agent = models.ForeignKey(
        'agents.Agent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_accounts',
        help_text='Agente IA padrão para respostas automáticas'
    )
    auto_response_enabled = models.BooleanField(default=True)
    human_handoff_enabled = models.BooleanField(default=True)
    
    metadata = models.JSONField(default=dict, blank=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='whatsapp_accounts',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'whatsapp_accounts'
        verbose_name = 'WhatsApp Account'
        verbose_name_plural = 'WhatsApp Accounts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.display_phone_number or self.phone_number})"

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
    def masked_token(self) -> str:
        """Return masked token for display."""
        return mask_token(self.access_token)

    def rotate_token(self, new_token: str):
        """Rotate the access token."""
        self.access_token = new_token
        self.save(update_fields=['access_token_encrypted', 'token_version', 'updated_at'])


class Message(BaseModel):
    """WhatsApp message model."""
    
    class MessageType(models.TextChoices):
        TEXT = 'text', 'Text'
        IMAGE = 'image', 'Image'
        VIDEO = 'video', 'Video'
        AUDIO = 'audio', 'Audio'
        DOCUMENT = 'document', 'Document'
        STICKER = 'sticker', 'Sticker'
        LOCATION = 'location', 'Location'
        CONTACTS = 'contacts', 'Contacts'
        INTERACTIVE = 'interactive', 'Interactive'
        TEMPLATE = 'template', 'Template'
        REACTION = 'reaction', 'Reaction'
        BUTTON = 'button', 'Button'
        ORDER = 'order', 'Order'
        SYSTEM = 'system', 'System'
        UNKNOWN = 'unknown', 'Unknown'

    class MessageDirection(models.TextChoices):
        INBOUND = 'inbound', 'Inbound'
        OUTBOUND = 'outbound', 'Outbound'

    class MessageStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        DELIVERED = 'delivered', 'Delivered'
        READ = 'read', 'Read'
        FAILED = 'failed', 'Failed'

    account = models.ForeignKey(
        WhatsAppAccount,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='messages'
    )
    
    whatsapp_message_id = models.CharField(max_length=100, unique=True, db_index=True)
    direction = models.CharField(max_length=10, choices=MessageDirection.choices)
    message_type = models.CharField(max_length=20, choices=MessageType.choices)
    status = models.CharField(
        max_length=20,
        choices=MessageStatus.choices,
        default=MessageStatus.PENDING
    )
    
    from_number = models.CharField(max_length=20, db_index=True)
    to_number = models.CharField(max_length=20, db_index=True)
    
    content = models.JSONField(default=dict)
    text_body = models.TextField(blank=True)
    
    media_id = models.CharField(max_length=100, blank=True)
    media_url = models.URLField(blank=True)
    media_mime_type = models.CharField(max_length=100, blank=True)
    media_sha256 = models.CharField(max_length=64, blank=True)
    
    template_name = models.CharField(max_length=255, blank=True)
    template_language = models.CharField(max_length=10, blank=True)
    
    context_message_id = models.CharField(max_length=100, blank=True)
    
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)
    processed_by_agent = models.BooleanField(default=False, help_text='Processado pelo agente IA')

    class Meta:
        db_table = 'whatsapp_messages'
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'from_number', '-created_at']),
            models.Index(fields=['account', 'to_number', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.direction}: {self.from_number} -> {self.to_number} ({self.message_type})"


class WebhookEvent(BaseModel):
    """Webhook event log for idempotency and debugging."""
    
    class EventType(models.TextChoices):
        MESSAGE = 'message', 'Message'
        STATUS = 'status', 'Status Update'
        ERROR = 'error', 'Error'
        UNKNOWN = 'unknown', 'Unknown'

    class ProcessingStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        DUPLICATE = 'duplicate', 'Duplicate'

    account = models.ForeignKey(
        WhatsAppAccount,
        on_delete=models.CASCADE,
        related_name='webhook_events',
        null=True,
        blank=True
    )
    
    event_id = models.CharField(max_length=100, unique=True, db_index=True)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
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
        Message,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='webhook_events'
    )

    class Meta:
        db_table = 'whatsapp_webhook_events'
        verbose_name = 'Webhook Event'
        verbose_name_plural = 'Webhook Events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['processing_status', '-created_at']),
            models.Index(fields=['event_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.event_type}: {self.event_id} ({self.processing_status})"


class MessageTemplate(BaseModel):
    """WhatsApp message template."""
    
    class TemplateStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    class TemplateCategory(models.TextChoices):
        MARKETING = 'marketing', 'Marketing'
        UTILITY = 'utility', 'Utility'
        AUTHENTICATION = 'authentication', 'Authentication'

    account = models.ForeignKey(
        WhatsAppAccount,
        on_delete=models.CASCADE,
        related_name='templates'
    )
    
    template_id = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=255)
    language = models.CharField(max_length=10, default='pt_BR')
    category = models.CharField(max_length=20, choices=TemplateCategory.choices)
    status = models.CharField(
        max_length=20,
        choices=TemplateStatus.choices,
        default=TemplateStatus.PENDING
    )
    
    components = models.JSONField(default=list)
    
    class Meta:
        db_table = 'whatsapp_templates'
        verbose_name = 'Message Template'
        verbose_name_plural = 'Message Templates'
        unique_together = ['account', 'name', 'language']

    def __str__(self):
        return f"{self.name} ({self.language}) - {self.status}"
"""
WhatsApp Flows models - Flows and Flow Responses.
"""
from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class Flow(models.Model):
    """
    WhatsApp Flow - Formulários nativos do WhatsApp.
    
    Permite criar formulários interativos que os usuários
    preenchem diretamente no WhatsApp.
    """
    
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Rascunho'
        PUBLISHED = 'published', 'Publicado'
        ARCHIVED = 'archived', 'Arquivado'
        DEPRECATED = 'deprecated', 'Descontinuado'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, verbose_name='Nome')
    description = models.TextField(blank=True, verbose_name='Descrição')
    
    # Definição JSON do flow (screens, components, data)
    json_definition = models.JSONField(
        default=dict,
        verbose_name='Definição JSON',
        help_text='Estrutura do flow conforme documentação do Meta'
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name='Status'
    )
    
    # IDs do Meta
    flow_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Flow ID (Meta)',
        help_text='ID do flow na API do WhatsApp Business'
    )
    
    # Conta associada
    account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='flows',
        verbose_name='Conta WhatsApp'
    )
    
    category = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Categoria'
    )
    
    version = models.CharField(
        max_length=20,
        default='1.0',
        verbose_name='Versão'
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')
    published_at = models.DateTimeField(null=True, blank=True, verbose_name='Publicado em')
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_flows',
        verbose_name='Criado por'
    )
    
    class Meta:
        db_table = 'whatsapp_flows'
        verbose_name = 'Flow'
        verbose_name_plural = 'Flows'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['flow_id']),
            models.Index(fields=['status']),
            models.Index(fields=['account', 'status']),
        ]
    
    def __str__(self):
        return f"{self.name} (v{self.version})"
    
    def is_published(self):
        """Verifica se o flow está publicado no Meta."""
        return self.status == self.Status.PUBLISHED and self.flow_id is not None


class FlowResponse(models.Model):
    """
    Respostas de flows enviados aos usuários.
    """
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        COMPLETED = 'completed', 'Completo'
        EXPIRED = 'expired', 'Expirado'
        ERROR = 'error', 'Erro'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    flow = models.ForeignKey(
        Flow,
        on_delete=models.CASCADE,
        related_name='responses',
        verbose_name='Flow'
    )
    
    # Contato que respondeu
    from_number = models.CharField(
        max_length=20,
        verbose_name='Número do remetente'
    )
    
    # ID da mensagem de flow
    flow_message_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='ID da Mensagem'
    )
    
    # Dados da resposta
    response_data = models.JSONField(
        default=dict,
        verbose_name='Dados da Resposta'
    )
    
    # Dados brutos do webhook
    raw_webhook_data = models.JSONField(
        default=dict,
        verbose_name='Dados Brutos do Webhook'
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='Status'
    )
    
    final_screen = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Screen Final'
    )
    
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name='Enviado em')
    responded_at = models.DateTimeField(null=True, blank=True, verbose_name='Respondido em')
    
    class Meta:
        db_table = 'whatsapp_flow_responses'
        verbose_name = 'Resposta de Flow'
        verbose_name_plural = 'Respostas de Flows'
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['flow', 'status']),
            models.Index(fields=['from_number', 'status']),
            models.Index(fields=['flow_message_id']),
        ]
    
    def __str__(self):
        return f"Resposta de {self.from_number} para {self.flow.name}"
# ============================================
# MESSAGE CONTEXT - Quoted Messages & Forwarding
# ============================================

class MessageContext(models.Model):
    """
    Contexto de mensagens - para reply e encaminhamento.
    
    Permite rastrear:
    - Mensagens citadas (quoted messages)
    - Mensagens encaminhadas (forwarded)
    - Thread de conversa
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Mensagem que tem contexto
    message = models.OneToOneField(
        Message,
        on_delete=models.CASCADE,
        related_name='context',
        verbose_name='Mensagem',
        null=True,
        blank=True
    )
    
    # ID da mensagem original citada
    quoted_message_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID Mensagem Citada'
    )
    
    # Conteúdo da mensagem citada (snapshot)
    quoted_message_content = models.TextField(
        blank=True,
        verbose_name='Conteúdo da Mensagem Citada'
    )
    
    # Tipo da mensagem citada
    quoted_message_type = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Tipo da Mensagem Citada'
    )
    
    # Remetente da mensagem citada
    quoted_sender_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='ID do Remetente Original'
    )
    
    # Encaminhamento
    is_forwarded = models.BooleanField(
        default=False,
        verbose_name='É Encaminhada'
    )
    
    forwarded_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Número de Encaminhamentos'
    )
    
    is_frequently_forwarded = models.BooleanField(
        default=False,
        verbose_name='Frequentemente Encaminhada'
    )
    
    # Metadados
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    
    class Meta:
        db_table = 'whatsapp_message_contexts'
        verbose_name = 'Contexto de Mensagem'
        verbose_name_plural = 'Contextos de Mensagens'
        indexes = [
            models.Index(fields=['quoted_message_id']),
            models.Index(fields=['is_forwarded']),
            models.Index(fields=['is_frequently_forwarded']),
        ]
    
    def __str__(self):
        if self.is_forwarded:
            return "Forwarded message (x%s)" % self.forwarded_count
        elif self.quoted_message_id:
            return "Reply to %s" % self.quoted_message_id
        return "Message context"
    
    def set_quoted_message(self, message_id, content, message_type, sender_id):
        """Define a mensagem citada."""
        self.quoted_message_id = message_id
        self.quoted_message_content = content
        self.quoted_message_type = message_type
        self.quoted_sender_id = sender_id
        self.save()
    
    def mark_as_forwarded(self, count=1):
        """Marca como mensagem encaminhada."""
        self.is_forwarded = True
        self.forwarded_count = count
        if count >= 5:
            self.is_frequently_forwarded = True
        self.save()

# ADVANCED MESSAGE TEMPLATES - Coupon, Auth, Order
# ============================================

class AdvancedTemplate(models.Model):
    """
    Templates avançados do WhatsApp.
    
    Suporta:
    - Carousel (carrossel de produtos)
    - Limited Time Offer (cupom com timer)
    - Authentication (OTP/2FA)
    - Order Details (detalhes de pedido)
    """
    
    class TemplateType(models.TextChoices):
        CAROUSEL = 'carousel', 'Carrossel'
        LTO = 'lto', 'Limited Time Offer (Cupom)'
        AUTH = 'auth', 'Autenticação (OTP)'
        ORDER = 'order', 'Detalhes de Pedido'
        CATALOG = 'catalog', 'Catálogo'
    
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Rascunho'
        PENDING = 'pending', 'Pendente Aprovação'
        APPROVED = 'approved', 'Aprovado'
        REJECTED = 'rejected', 'Rejeitado'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    name = models.CharField(max_length=255, verbose_name='Nome')
    description = models.TextField(blank=True, verbose_name='Descrição')
    
    template_type = models.CharField(
        max_length=20,
        choices=TemplateType.choices,
        verbose_name='Tipo de Template'
    )
    
    # Configuração específica do template (JSON)
    config = models.JSONField(
        default=dict,
        verbose_name='Configuração',
        help_text='Configuração específica por tipo'
    )
    
    # Componentes do template
    components = models.JSONField(
        default=list,
        verbose_name='Componentes',
        help_text='Componentes no formato da API do Meta'
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name='Status'
    )
    
    # ID do template no Meta (após publicação)
    meta_template_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID no Meta'
    )
    
    # Conta WhatsApp
    account = models.ForeignKey(
        WhatsAppAccount,
        on_delete=models.CASCADE,
        related_name='advanced_templates',
        verbose_name='Conta WhatsApp'
    )
    
    language = models.CharField(
        max_length=10,
        default='pt_BR',
        verbose_name='Idioma'
    )
    
    category = models.CharField(
        max_length=20,
        default='MARKETING',
        verbose_name='Categoria'
    )
    
    # Controle de versão
    version = models.CharField(max_length=10, default='1.0', verbose_name='Versão')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name='Submetido em')
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='Aprovado em')
    
    # Motivo da rejeição (se houver)
    rejection_reason = models.TextField(blank=True, verbose_name='Motivo da Rejeição')
    
    class Meta:
        db_table = 'whatsapp_advanced_templates'
        verbose_name = 'Template Avançado'
        verbose_name_plural = 'Templates Avançados'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['template_type', 'status']),
            models.Index(fields=['account', 'status']),
            models.Index(fields=['meta_template_id']),
        ]
    
    def __str__(self):
        return "%s (%s)" % (self.name, self.get_template_type_display())
    
    def is_approved(self):
        return self.status == self.Status.APPROVED
    
    def is_rejected(self):
        return self.status == self.Status.REJECTED


class AdvancedTemplateLog(models.Model):
    """
    Log de envios de templates avançados.
    """
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        SENT = 'sent', 'Enviado'
        DELIVERED = 'delivered', 'Entregue'
        READ = 'read', 'Lido'
        FAILED = 'failed', 'Falhou'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    template = models.ForeignKey(
        AdvancedTemplate,
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name='Template'
    )
    
    # Destinatário
    to_number = models.CharField(max_length=20, verbose_name='Número')
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='Status'
    )
    
    # ID da mensagem no WhatsApp
    whatsapp_message_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID da Mensagem'
    )
    
    # Dados enviados (para templates dinâmicos)
    sent_data = models.JSONField(
        default=dict,
        verbose_name='Dados Enviados'
    )
    
    # Erro (se houver)
    error_message = models.TextField(blank=True, verbose_name='Erro')
    
    # Timestamps
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='Enviado em')
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name='Entregue em')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='Lido em')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    
    class Meta:
        db_table = 'whatsapp_advanced_template_logs'
        verbose_name = 'Log de Template Avançado'
        verbose_name_plural = 'Logs de Templates Avançados'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['template', 'status']),
            models.Index(fields=['to_number', 'status']),
            models.Index(fields=['whatsapp_message_id']),
        ]
    
    def __str__(self):
        return "Log %s - %s" % (self.template.name, self.status)

# WHATSAPP ANALYTICS - Métricas e Relatórios
# ============================================

class WhatsAppAnalytics(models.Model):
    """
    Métricas diárias de analytics do WhatsApp.
    
    Armazena dados de:
    - Conversações (total, por categoria)
    - Mensagens (enviadas, entregues, lidas)
    - Custos
    - Quality ratings
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Conta e data
    account = models.ForeignKey(
        WhatsAppAccount,
        on_delete=models.CASCADE,
        related_name='analytics',
        verbose_name='Conta WhatsApp'
    )
    
    date = models.DateField(verbose_name='Data')
    
    # Métricas de conversações
    total_conversations = models.PositiveIntegerField(default=0, verbose_name='Total Conversações')
    user_initiated = models.PositiveIntegerField(default=0, verbose_name='Iniciadas pelo Usuário')
    business_initiated = models.PositiveIntegerField(default=0, verbose_name='Iniciadas pelo Negócio')
    
    # Por categoria
    marketing_conversations = models.PositiveIntegerField(default=0, verbose_name='Marketing')
    utility_conversations = models.PositiveIntegerField(default=0, verbose_name='Utilidade')
    authentication_conversations = models.PositiveIntegerField(default=0, verbose_name='Autenticação')
    service_conversations = models.PositiveIntegerField(default=0, verbose_name='Serviço')
    
    # Métricas de mensagens
    messages_sent = models.PositiveIntegerField(default=0, verbose_name='Mensagens Enviadas')
    messages_delivered = models.PositiveIntegerField(default=0, verbose_name='Mensagens Entregues')
    messages_read = models.PositiveIntegerField(default=0, verbose_name='Mensagens Lidas')
    
    # Taxas (percentuais)
    delivery_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Taxa de Entrega %')
    read_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Taxa de Leitura %')
    
    # Custos (em dólares)
    total_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name='Custo Total')
    marketing_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name='Custo Marketing')
    utility_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name='Custo Utilidade')
    authentication_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name='Custo Autenticação')
    service_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name='Custo Serviço')
    
    # Quality rating
    quality_rating = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Qualidade'
    )
    
    # Metadados
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')
    
    class Meta:
        db_table = 'whatsapp_analytics'
        verbose_name = 'Analytics do WhatsApp'
        verbose_name_plural = 'Analytics do WhatsApp'
        ordering = ['-date']
        unique_together = ['account', 'date']
        indexes = [
            models.Index(fields=['account', 'date']),
            models.Index(fields=['date']),
            models.Index(fields=['quality_rating']),
        ]
    
    def __str__(self):
        return "Analytics %s - %s" % (self.account.name, self.date)
    
    def calculate_rates(self):
        """Calcula as taxas de entrega e leitura."""
        if self.messages_sent > 0:
            self.delivery_rate = (self.messages_delivered / self.messages_sent) * 100
            self.read_rate = (self.messages_read / self.messages_sent) * 100
            self.save()


class WhatsAppAnalyticsReport(models.Model):
    """
    Relatórios agendados de analytics.
    """
    
    class ReportType(models.TextChoices):
        DAILY = 'daily', 'Diário'
        WEEKLY = 'weekly', 'Semanal'
        MONTHLY = 'monthly', 'Mensal'
    
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Ativo'
        PAUSED = 'paused', 'Pausado'
        ARCHIVED = 'archived', 'Arquivado'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    name = models.CharField(max_length=255, verbose_name='Nome')
    
    report_type = models.CharField(
        max_length=20,
        choices=ReportType.choices,
        verbose_name='Tipo de Relatório'
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name='Status'
    )
    
    # Contas incluídas
    accounts = models.ManyToManyField(
        WhatsAppAccount,
        related_name='analytics_reports',
        verbose_name='Contas'
    )
    
    # Métricas incluídas
    include_conversations = models.BooleanField(default=True, verbose_name='Incluir Conversações')
    include_messages = models.BooleanField(default=True, verbose_name='Incluir Mensagens')
    include_costs = models.BooleanField(default=True, verbose_name='Incluir Custos')
    include_quality = models.BooleanField(default=True, verbose_name='Incluir Qualidade')
    
    # Destinatários (emails)
    recipients = models.JSONField(default=list, verbose_name='Destinatários')
    
    # Agendamento
    schedule_day = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Dia do Agendamento',
        help_text='Dia da semana (0-6) para semanal, ou dia do mês (1-31) para mensal'
    )
    
    schedule_time = models.TimeField(
        default='08:00',
        verbose_name='Horário'
    )
    
    # Última execução
    last_run_at = models.DateTimeField(null=True, blank=True, verbose_name='Última Execução')
    last_run_status = models.CharField(max_length=20, blank=True, verbose_name='Status da Última Execução')
    
    # Controle
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')
    
    class Meta:
        db_table = 'whatsapp_analytics_reports'
        verbose_name = 'Relatório de Analytics'
        verbose_name_plural = 'Relatórios de Analytics'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name

