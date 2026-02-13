from django.db import models
from django.conf import settings
import uuid


class InstagramAccount(models.Model):
    """Conta do Instagram conectada via Graph API"""
    PLATFORM_CHOICES = [
        ('instagram', 'Instagram'),
        ('facebook', 'Facebook'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='instagram_accounts')
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default='instagram')
    
    # Identificadores da API
    instagram_business_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    facebook_page_id = models.CharField(max_length=255, null=True, blank=True)
    username = models.CharField(max_length=255)
    
    # Tokens de acesso
    access_token = models.TextField()
    token_expires_at = models.DateTimeField(null=True, blank=True)
    
    # Metadados
    followers_count = models.IntegerField(default=0)
    follows_count = models.IntegerField(default=0)
    media_count = models.IntegerField(default=0)
    profile_picture_url = models.URLField(null=True, blank=True)
    biography = models.TextField(blank=True)
    website = models.URLField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'instagram_accounts'
        ordering = ['-created_at']
        verbose_name = 'Instagram Account'
        verbose_name_plural = 'Instagram Accounts'
    
    def __str__(self):
        return f"@{self.username}"


class InstagramMedia(models.Model):
    """Posts, Stories e Reels do Instagram"""
    MEDIA_TYPES = [
        ('IMAGE', 'Imagem'),
        ('VIDEO', 'Vídeo'),
        ('CAROUSEL_ALBUM', 'Carrossel'),
        ('REELS', 'Reels'),
        ('STORY', 'Story'),
        ('LIVE', 'Live'),
    ]
    
    STATUS_CHOICES = [
        ('PUBLISHED', 'Publicado'),
        ('SCHEDULED', 'Agendado'),
        ('DRAFT', 'Rascunho'),
        ('PROCESSING', 'Processando'),
        ('FAILED', 'Falhou'),
        ('ARCHIVED', 'Arquivado'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(InstagramAccount, on_delete=models.CASCADE, related_name='media')
    
    # Identificadores da API
    instagram_media_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    shortcode = models.CharField(max_length=255, null=True, blank=True)
    permalink = models.URLField(null=True, blank=True)
    
    # Conteúdo
    media_type = models.CharField(max_length=20, choices=MEDIA_TYPES)
    caption = models.TextField(blank=True)
    media_url = models.URLField(null=True, blank=True)
    thumbnail_url = models.URLField(null=True, blank=True)
    
    # Métricas
    likes_count = models.IntegerField(default=0)
    comments_count = models.IntegerField(default=0)
    shares_count = models.IntegerField(default=0)
    saves_count = models.IntegerField(default=0)
    reach = models.IntegerField(default=0)
    impressions = models.IntegerField(default=0)
    
    # Agendamento
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    scheduled_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    # Shopping tags
    has_product_tags = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'instagram_media'
        ordering = ['-created_at']
        verbose_name = 'Instagram Media'
        verbose_name_plural = 'Instagram Media'
    
    def __str__(self):
        return f"{self.media_type} - {self.caption[:50] if self.caption else 'Sem legenda'}"


class InstagramMediaItem(models.Model):
    """Itens individuais de um carrossel/album"""
    media = models.ForeignKey(InstagramMedia, on_delete=models.CASCADE, related_name='items')
    instagram_media_id = models.CharField(max_length=255)
    media_type = models.CharField(max_length=20, choices=[('IMAGE', 'Imagem'), ('VIDEO', 'Vídeo')])
    media_url = models.URLField()
    thumbnail_url = models.URLField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'instagram_media_items'
        ordering = ['order']


class InstagramProductTag(models.Model):
    """Tags de produtos em mídias (Shopping)"""
    media = models.ForeignKey(InstagramMedia, on_delete=models.CASCADE, related_name='product_tags')
    product_id = models.CharField(max_length=255)
    product_name = models.CharField(max_length=255)
    position_x = models.FloatField()  # 0.0 a 1.0
    position_y = models.FloatField()  # 0.0 a 1.0
    
    class Meta:
        db_table = 'instagram_product_tags'


class InstagramCatalog(models.Model):
    """Catálogo de produtos do Instagram Shopping"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(InstagramAccount, on_delete=models.CASCADE, related_name='catalogs')
    
    # Identificadores
    catalog_id = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'instagram_catalogs'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class InstagramProduct(models.Model):
    """Produtos do catálogo"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catalog = models.ForeignKey(InstagramCatalog, on_delete=models.CASCADE, related_name='products')
    
    # Identificadores
    product_id = models.CharField(max_length=255, unique=True)
    retailer_id = models.CharField(max_length=255, null=True, blank=True)
    
    # Informações do produto
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='BRL')
    availability = models.CharField(max_length=20, default='in stock')
    condition = models.CharField(max_length=20, default='new')
    
    # Mídia
    image_url = models.URLField()
    additional_image_urls = models.JSONField(default=list, blank=True)
    
    # Links
    url = models.URLField()
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'instagram_products'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class InstagramLive(models.Model):
    """Transmissões ao vivo do Instagram"""
    STATUS_CHOICES = [
        ('SCHEDULED', 'Agendada'),
        ('LIVE', 'Ao vivo'),
        ('ENDED', 'Finalizada'),
        ('CANCELLED', 'Cancelada'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(InstagramAccount, on_delete=models.CASCADE, related_name='lives')
    
    # Identificadores
    live_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    stream_url = models.URLField(null=True, blank=True)
    stream_key = models.CharField(max_length=255, null=True, blank=True)
    
    # Informações
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Métricas
    viewers_count = models.IntegerField(default=0)
    max_viewers = models.IntegerField(default=0)
    comments_count = models.IntegerField(default=0)
    
    # Agendamento
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SCHEDULED')
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'instagram_lives'
        ordering = ['-created_at']
        verbose_name = 'Instagram Live'
        verbose_name_plural = 'Instagram Lives'
    
    def __str__(self):
        return self.title


class InstagramLiveComment(models.Model):
    """Comentários de lives"""
    live = models.ForeignKey(InstagramLive, on_delete=models.CASCADE, related_name='comments')
    comment_id = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    text = models.TextField()
    created_at = models.DateTimeField()
    
    class Meta:
        db_table = 'instagram_live_comments'
        ordering = ['-created_at']


class InstagramConversation(models.Model):
    """Conversas do Instagram Direct"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(InstagramAccount, on_delete=models.CASCADE, related_name='conversations')
    
    # Identificadores
    instagram_conversation_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    
    # Participantes
    participant_id = models.CharField(max_length=255)  # ID do usuário no Instagram
    participant_username = models.CharField(max_length=255)
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
        db_table = 'instagram_conversations'
        ordering = ['-last_message_at', '-created_at']
        verbose_name = 'Instagram Conversation'
        verbose_name_plural = 'Instagram Conversations'
    
    def __str__(self):
        return f"Chat com {self.participant_username}"


class InstagramMessage(models.Model):
    """Mensagens do Instagram Direct"""
    MESSAGE_TYPES = [
        ('TEXT', 'Texto'),
        ('IMAGE', 'Imagem'),
        ('VIDEO', 'Vídeo'),
        ('AUDIO', 'Áudio/Voz'),
        ('FILE', 'Arquivo'),
        ('STICKER', 'Sticker'),
        ('REACTION', 'Reação'),
        ('SHARE', 'Compartilhamento'),
        ('STORY_REPLY', 'Resposta a Story'),
        ('POST_SHARE', 'Compartilhamento de Post'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(InstagramConversation, on_delete=models.CASCADE, related_name='messages')
    
    # Identificadores
    instagram_message_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    
    # Conteúdo
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='TEXT')
    content = models.TextField(blank=True)
    media_url = models.URLField(null=True, blank=True)
    
    # Reações e respostas
    reply_to_message = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    reaction_type = models.CharField(max_length=50, null=True, blank=True)  # ❤️, 👍, 😂, etc
    
    # Remoção
    is_unsent = models.BooleanField(default=False)
    unsent_at = models.DateTimeField(null=True, blank=True)
    
    # Direção
    is_from_business = models.BooleanField(default=False)  # True = enviada pela empresa
    
    # Status
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'instagram_messages'
        ordering = ['created_at']
        verbose_name = 'Instagram Message'
        verbose_name_plural = 'Instagram Messages'
    
    def __str__(self):
        return f"{self.message_type}: {self.content[:50] if self.content else '(sem texto)'}"


class InstagramWebhookLog(models.Model):
    """Logs de webhooks do Instagram"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Dados do webhook
    object_type = models.CharField(max_length=50)  # instagram, page, etc
    field = models.CharField(max_length=50)  # messages, mentions, etc
    payload = models.JSONField()
    
    # Status de processamento
    is_processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'instagram_webhook_logs'
        ordering = ['-created_at']


class InstagramScheduledPost(models.Model):
    """Posts agendados do Instagram"""
    MEDIA_TYPES = [
        ('IMAGE', 'Imagem'),
        ('VIDEO', 'Vídeo'),
        ('CAROUSEL', 'Carrossel'),
        ('REELS', 'Reels'),
        ('STORY', 'Story'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pendente'),
        ('PROCESSING', 'Processando'),
        ('PUBLISHED', 'Publicado'),
        ('FAILED', 'Falhou'),
        ('CANCELLED', 'Cancelado'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(InstagramAccount, on_delete=models.CASCADE, related_name='scheduled_posts')
    
    # Conteúdo
    media_type = models.CharField(max_length=20, choices=MEDIA_TYPES)
    caption = models.TextField(blank=True)
    media_files = models.JSONField(default=list)  # Lista de URLs/arquivos
    
    # Configurações
    schedule_time = models.DateTimeField()
    timezone = models.CharField(max_length=50, default='America/Sao_Paulo')
    
    # Shopping
    product_tags = models.JSONField(default=list, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    instagram_media_id = models.CharField(max_length=255, null=True, blank=True)
    
    # Resultado
    error_message = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'instagram_scheduled_posts'
        ordering = ['schedule_time']


class InstagramInsight(models.Model):
    """Métricas e insights do Instagram"""
    account = models.ForeignKey(InstagramAccount, on_delete=models.CASCADE, related_name='insights')
    media = models.ForeignKey(InstagramMedia, on_delete=models.CASCADE, related_name='insights', null=True, blank=True)
    
    # Período
    date = models.DateField()
    
    # Métricas da conta
    impressions = models.IntegerField(default=0)
    reach = models.IntegerField(default=0)
    profile_views = models.IntegerField(default=0)
    website_clicks = models.IntegerField(default=0)
    
    # Métricas de seguidores
    follower_count = models.IntegerField(default=0)
    followers_gained = models.IntegerField(default=0)
    followers_lost = models.IntegerField(default=0)
    
    # Métricas de engajamento
    engagement = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'instagram_insights'
        ordering = ['-date']
        unique_together = ['account', 'media', 'date']