from django.db import models
from django.conf import settings
import uuid


class MessengerAccount(models.Model):
    """Conta do Messenger/Facebook conectada"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='messenger_accounts')
    
    # Identificadores
    page_id = models.CharField(max_length=255, unique=True)
    page_name = models.CharField(max_length=255)
    page_access_token = models.TextField()
    
    # Configurações
    app_id = models.CharField(max_length=255, null=True, blank=True)
    app_secret = models.CharField(max_length=255, null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    webhook_verified = models.BooleanField(default=False)
    
    # Metadados
    category = models.CharField(max_length=255, blank=True)
    followers_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'messenger_accounts'
        ordering = ['-created_at']
        verbose_name = 'Messenger Account'
        verbose_name_plural = 'Messenger Accounts'
    
    def __str__(self):
        return self.page_name


class MessengerProfile(models.Model):
    """Configurações de perfil do Messenger"""
    account = models.OneToOneField(MessengerAccount, on_delete=models.CASCADE, related_name='profile')
    
    # Greeting
    greeting_text = models.TextField(blank=True, help_text="Mensagem de saudação inicial")
    
    # Get Started Button
    get_started_payload = models.CharField(max_length=1000, blank=True, default='GET_STARTED')
    
    # Persistent Menu
    persistent_menu = models.JSONField(default=dict, blank=True)
    
    # Ice Breakers
    ice_breakers = models.JSONField(default=list, blank=True)
    
    # Whitelisted domains
    whitelisted_domains = models.JSONField(default=list, blank=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'messenger_profiles'


class MessengerConversation(models.Model):
    """Conversas do Messenger"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(MessengerAccount, on_delete=models.CASCADE, related_name='conversations')
    
    # Identificadores
    messenger_conversation_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    
    # Participante (usuário do Facebook)
    psid = models.CharField(max_length=255, help_text="Page-scoped ID do usuário")
    participant_name = models.CharField(max_length=255, blank=True)
    participant_profile_pic = models.URLField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    unread_count = models.IntegerField(default=0)
    
    # Timestamps
    last_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'messenger_conversations'
        ordering = ['-last_message_at', '-created_at']
        verbose_name = 'Messenger Conversation'
        verbose_name_plural = 'Messenger Conversations'
    
    def __str__(self):
        return f"Chat com {self.participant_name or self.psid}"


class MessengerMessage(models.Model):
    """Mensagens do Messenger"""
    MESSAGE_TYPES = [
        ('TEXT', 'Texto'),
        ('IMAGE', 'Imagem'),
        ('VIDEO', 'Vídeo'),
        ('AUDIO', 'Áudio'),
        ('FILE', 'Arquivo'),
        ('STICKER', 'Sticker'),
        ('TEMPLATE', 'Template'),
        ('QUICK_REPLY', 'Resposta Rápida'),
        ('POSTBACK', 'Postback'),
        ('CALL', 'Chamada'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(MessengerConversation, on_delete=models.CASCADE, related_name='messages')
    
    # Identificadores
    messenger_message_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    
    # Conteúdo
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='TEXT')
    content = models.TextField(blank=True)
    attachment_url = models.URLField(null=True, blank=True)
    attachment_type = models.CharField(max_length=50, blank=True)
    
    # Template/Buttons
    template_payload = models.JSONField(default=dict, blank=True)
    quick_replies = models.JSONField(default=list, blank=True)
    
    # Direção
    is_from_page = models.BooleanField(default=False)  # True = enviada pela página
    
    # Status
    is_read = models.BooleanField(default=False)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'messenger_messages'
        ordering = ['created_at']
        verbose_name = 'Messenger Message'
        verbose_name_plural = 'Messenger Messages'
    
    def __str__(self):
        return f"{self.message_type}: {self.content[:50] if self.content else '(sem texto)'}"


class MessengerBroadcast(models.Model):
    """Broadcasts (mensagens em massa) do Messenger"""
    STATUS_CHOICES = [
        ('DRAFT', 'Rascunho'),
        ('SCHEDULED', 'Agendado'),
        ('PROCESSING', 'Processando'),
        ('COMPLETED', 'Concluído'),
        ('FAILED', 'Falhou'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(MessengerAccount, on_delete=models.CASCADE, related_name='broadcasts')
    
    # Conteúdo
    name = models.CharField(max_length=255)
    message_type = models.CharField(max_length=20, choices=MessengerMessage.MESSAGE_TYPES, default='TEXT')
    content = models.TextField()
    template_payload = models.JSONField(default=dict, blank=True)
    
    # Segmentação
    target_audience = models.JSONField(default=dict, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    # Métricas
    total_recipients = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    delivered_count = models.IntegerField(default=0)
    read_count = models.IntegerField(default=0)
    
    # Agendamento
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'messenger_broadcasts'
        ordering = ['-created_at']


class MessengerSponsoredMessage(models.Model):
    """Mensagens patrocinadas do Messenger"""
    STATUS_CHOICES = [
        ('DRAFT', 'Rascunho'),
        ('PENDING_REVIEW', 'Em Revisão'),
        ('APPROVED', 'Aprovado'),
        ('REJECTED', 'Rejeitado'),
        ('ACTIVE', 'Ativo'),
        ('PAUSED', 'Pausado'),
        ('COMPLETED', 'Concluído'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(MessengerAccount, on_delete=models.CASCADE, related_name='sponsored_messages')
    
    # Configurações do anúncio
    name = models.CharField(max_length=255)
    ad_account_id = models.CharField(max_length=255)
    
    # Conteúdo
    message_type = models.CharField(max_length=20, default='TEXT')
    content = models.TextField()
    template_payload = models.JSONField(default=dict, blank=True)
    
    # Segmentação e orçamento
    targeting = models.JSONField(default=dict)
    daily_budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    facebook_ad_id = models.CharField(max_length=255, null=True, blank=True)
    
    # Métricas
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    spent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Agendamento
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'messenger_sponsored_messages'
        ordering = ['-created_at']


class MessengerExtension(models.Model):
    """Extensões do Messenger (Chat Extensions, etc)"""
    EXTENSION_TYPES = [
        ('CHAT_EXTENSION', 'Chat Extension'),
        ('GAME', 'Jogo'),
        ('WEBVIEW', 'Webview'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(MessengerAccount, on_delete=models.CASCADE, related_name='extensions')
    
    name = models.CharField(max_length=255)
    extension_type = models.CharField(max_length=20, choices=EXTENSION_TYPES)
    
    # Configurações
    url = models.URLField()
    icon_url = models.URLField(null=True, blank=True)
    
    # Configurações específicas
    webview_height_ratio = models.CharField(
        max_length=20,
        choices=[('compact', 'Compacto'), ('tall', 'Alto'), ('full', 'Cheio')],
        default='tall'
    )
    in_test = models.BooleanField(default=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'messenger_extensions'


class MessengerWebhookLog(models.Model):
    """Logs de webhooks do Messenger"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    object_type = models.CharField(max_length=50)
    payload = models.JSONField()
    
    is_processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'messenger_webhook_logs'
        ordering = ['-created_at']