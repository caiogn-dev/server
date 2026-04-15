"""
Messaging v2 - Models completos e independentes.
"""
import uuid
from django.db import models
from django.conf import settings
from apps.core_v2.models import BaseModel


class PlatformAccount(BaseModel):
    """Conta de plataforma unificada (WhatsApp, Instagram, Messenger)."""
    
    class Platform(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        INSTAGRAM = 'instagram', 'Instagram'
        MESSENGER = 'messenger', 'Messenger'
    
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Ativo'
        INACTIVE = 'inactive', 'Inativo'
        PENDING = 'pending', 'Pendente'
        SUSPENDED = 'suspended', 'Suspenso'
    
    # Usuário dono da conta (usando created_by do BaseModel)
    
    # Plataforma
    platform = models.CharField(max_length=20, choices=Platform.choices)
    name = models.CharField(max_length=255)
    
    # Campos WhatsApp Business
    phone_number_id = models.CharField(max_length=50, blank=True, db_index=True)
    waba_id = models.CharField(max_length=50, blank=True, db_index=True)
    phone_number = models.CharField(max_length=20, blank=True)
    display_phone_number = models.CharField(max_length=30, blank=True)
    
    # Campos Messenger/Instagram
    page_id = models.CharField(max_length=255, blank=True, db_index=True)
    page_name = models.CharField(max_length=255, blank=True)
    instagram_account_id = models.CharField(max_length=255, blank=True)
    
    # Token de acesso
    access_token = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    webhook_verified = models.BooleanField(default=False)
    
    # Webhook
    webhook_verify_token = models.CharField(max_length=255, blank=True)
    
    # Configurações de IA
    auto_response_enabled = models.BooleanField(default=True)
    human_handoff_enabled = models.BooleanField(default=True)
    default_agent_id = models.UUIDField(null=True, blank=True)
    
    # Metadados
    category = models.CharField(max_length=255, blank=True)
    followers_count = models.IntegerField(default=0)
    
    # Timestamps
    last_sync_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'messaging_v2_platformaccount'
        ordering = ['-created_at']
        verbose_name = 'Conta de Plataforma'
        verbose_name_plural = 'Contas de Plataforma'
        constraints = [
            models.UniqueConstraint(
                fields=['created_by', 'platform', 'phone_number_id'],
                name='unique_whatsapp_account',
                condition=models.Q(platform='whatsapp', phone_number_id__gt='')
            ),
            models.UniqueConstraint(
                fields=['created_by', 'platform', 'waba_id'],
                name='unique_waba',
                condition=models.Q(platform='whatsapp', waba_id__gt='')
            ),
            models.UniqueConstraint(
                fields=['created_by', 'platform', 'page_id'],
                name='unique_messenger_page',
                condition=models.Q(platform='messenger', page_id__gt='')
            ),
            models.UniqueConstraint(
                fields=['created_by', 'platform', 'instagram_account_id'],
                name='unique_instagram_account',
                condition=models.Q(platform='instagram', instagram_account_id__gt='')
            ),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_platform_display()})"
    
    @property
    def is_whatsapp(self):
        return self.platform == self.Platform.WHATSAPP
    
    @property
    def is_instagram(self):
        return self.platform == self.Platform.INSTAGRAM
    
    @property
    def is_messenger(self):
        return self.platform == self.Platform.MESSENGER
    
    @property
    def user(self):
        """Compatibilidade com código que espera user em vez de created_by."""
        return self.created_by


class Conversation(BaseModel):
    """Conversa com cliente unificada para todas as plataformas."""
    
    class Platform(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        INSTAGRAM = 'instagram', 'Instagram'
        MESSENGER = 'messenger', 'Messenger'
    
    # Conta da plataforma
    platform_account = models.ForeignKey(
        PlatformAccount,
        on_delete=models.CASCADE,
        related_name='conversations'
    )
    
    # Identificação do cliente
    customer_id = models.CharField(max_length=255, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True, db_index=True)
    customer_profile_pic = models.URLField(blank=True)
    
    # Plataforma
    platform = models.CharField(max_length=20, choices=Platform.choices)
    
    # Status
    is_open = models.BooleanField(default=True)
    unread_count = models.IntegerField(default=0)
    
    # Timestamps
    last_message_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'messaging_v2_conversation'
        ordering = ['-last_message_at', '-created_at']
        verbose_name = 'Conversa'
        verbose_name_plural = 'Conversas'
        unique_together = ['platform_account', 'customer_id']
    
    def __str__(self):
        return f"Conversa com {self.customer_name or self.customer_id}"


class UnifiedMessage(BaseModel):
    """Mensagem unificada para todas as plataformas."""
    
    class Direction(models.TextChoices):
        INBOUND = 'inbound', 'Recebida'
        OUTBOUND = 'outbound', 'Enviada'
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        SENT = 'sent', 'Enviada'
        DELIVERED = 'delivered', 'Entregue'
        READ = 'read', 'Lida'
        FAILED = 'failed', 'Falhou'
    
    class MessageType(models.TextChoices):
        TEXT = 'text', 'Texto'
        IMAGE = 'image', 'Imagem'
        VIDEO = 'video', 'Vídeo'
        AUDIO = 'audio', 'Áudio'
        DOCUMENT = 'document', 'Documento'
        LOCATION = 'location', 'Localização'
        CONTACT = 'contact', 'Contato'
        TEMPLATE = 'template', 'Template'
        INTERACTIVE = 'interactive', 'Interativo'
    
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    
    # Direção e status
    direction = models.CharField(max_length=10, choices=Direction.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # Tipo e conteúdo
    message_type = models.CharField(max_length=20, choices=MessageType.choices, default=MessageType.TEXT)
    text = models.TextField(blank=True)
    media_url = models.URLField(blank=True)
    media_caption = models.TextField(blank=True)
    
    # IDs externos
    external_id = models.CharField(max_length=255, blank=True, db_index=True)
    
    # Template (se aplicável)
    template_name = models.CharField(max_length=255, blank=True)
    template_params = models.JSONField(default=dict, blank=True)
    
    # Timestamps de status
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Metadados
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'messaging_v2_unifiedmessage'
        ordering = ['-created_at']
        verbose_name = 'Mensagem'
        verbose_name_plural = 'Mensagens'
    
    def __str__(self):
        return f"{self.direction} - {self.text[:50]}..."


class MessageTemplate(BaseModel):
    """Template de mensagem aprovado pela Meta."""
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        APPROVED = 'approved', 'Aprovado'
        REJECTED = 'rejected', 'Rejeitado'
    
    class Category(models.TextChoices):
        UTILITY = 'UTILITY', 'Utilidade'
        MARKETING = 'MARKETING', 'Marketing'
        AUTHENTICATION = 'AUTHENTICATION', 'Autenticação'
    
    # Conta da plataforma
    platform_account = models.ForeignKey(
        PlatformAccount,
        on_delete=models.CASCADE,
        related_name='templates'
    )
    
    # Identificação
    name = models.CharField(max_length=255)
    language = models.CharField(max_length=10, default='pt_BR')
    
    # Categoria e status
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.UTILITY)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # Conteúdo
    header = models.JSONField(default=dict, blank=True)
    body = models.TextField()
    footer = models.TextField(blank=True)
    buttons = models.JSONField(default=list, blank=True)
    
    # ID externo na Meta
    external_id = models.CharField(max_length=255, blank=True)
    
    class Meta:
        db_table = 'messaging_v2_messagetemplate'
        ordering = ['-created_at']
        verbose_name = 'Template'
        verbose_name_plural = 'Templates'
        unique_together = ['platform_account', 'name', 'language']
    
    def __str__(self):
        return f"{self.name} ({self.language})"
