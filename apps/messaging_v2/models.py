"""
Messaging v2 - Models completos e independentes.
"""
import uuid
from django.db import models
from apps.core_v2.models import BaseModel
from apps.commerce.models import Store


class PlatformAccount(BaseModel):
    """Conta de plataforma (WhatsApp, Instagram, etc)."""
    class Platform(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        INSTAGRAM = 'instagram', 'Instagram'
        MESSENGER = 'messenger', 'Messenger'
    
    platform = models.CharField(max_length=20, choices=Platform.choices)
    name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, blank=True)
    access_token = models.TextField(blank=True)
    
    # Status
    is_verified = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']


class Conversation(BaseModel):
    """Conversa com cliente."""
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='conversations')
    
    # Identificação do cliente
    customer_phone = models.CharField(max_length=20, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True)
    
    # Plataforma
    platform = models.CharField(max_length=20, default='whatsapp')
    
    # Status
    is_open = models.BooleanField(default=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-last_message_at', '-created_at']


class UnifiedMessage(BaseModel):
    """Mensagem unificada."""
    class Direction(models.TextChoices):
        INBOUND = 'inbound', 'Recebida'
        OUTBOUND = 'outbound', 'Enviada'
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        SENT = 'sent', 'Enviada'
        DELIVERED = 'delivered', 'Entregue'
        READ = 'read', 'Lida'
        FAILED = 'failed', 'Falhou'
    
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    
    direction = models.CharField(max_length=10, choices=Direction.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # Conteúdo
    text = models.TextField()
    media_url = models.URLField(blank=True)
    
    # IDs externos
    external_id = models.CharField(max_length=255, blank=True)
    
    # Timestamps de status
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']


class MessageTemplate(BaseModel):
    """Template de mensagem."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        APPROVED = 'approved', 'Aprovado'
        REJECTED = 'rejected', 'Rejeitado'
    
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=50, default='UTILITY')
    language = models.CharField(max_length=10, default='pt_BR')
    
    # Conteúdo
    header = models.JSONField(default=dict, blank=True)
    body = models.TextField()
    footer = models.TextField(blank=True)
    buttons = models.JSONField(default=list, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    external_id = models.CharField(max_length=255, blank=True)
    
    class Meta:
        ordering = ['name']
