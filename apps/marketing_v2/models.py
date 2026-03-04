"""
Marketing v2 - Models completos e independentes.
"""
import uuid
from django.db import models
from apps.core_v2.models import BaseModel
from apps.commerce.models import Store


class Campaign(BaseModel):
    """Campanha de marketing."""
    class Channel(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        EMAIL = 'email', 'Email'
        SMS = 'sms', 'SMS'
    
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Rascunho'
        SCHEDULED = 'scheduled', 'Agendada'
        SENDING = 'sending', 'Enviando'
        COMPLETED = 'completed', 'Concluída'
        CANCELLED = 'cancelled', 'Cancelada'
    
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='campaigns')
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.WHATSAPP)
    
    # Conteúdo
    subject = models.CharField(max_length=255, blank=True)
    content = models.JSONField(default=dict)
    
    # Audience
    audience_type = models.CharField(max_length=50, default='all')
    audience_filters = models.JSONField(default=dict, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    
    # Stats
    total_recipients = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    delivered_count = models.IntegerField(default=0)
    read_count = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']


class Template(BaseModel):
    """Template de mensagem."""
    class Channel(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        EMAIL = 'email', 'Email'
    
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='templates')
    
    name = models.CharField(max_length=255)
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.WHATSAPP)
    
    # Conteúdo
    content = models.JSONField(default=dict)
    variables = models.JSONField(default=list, blank=True)
    
    # Para WhatsApp
    whatsapp_template_name = models.CharField(max_length=255, blank=True)
    whatsapp_status = models.CharField(max_length=20, default='pending')
    
    class Meta:
        ordering = ['name']


class Automation(BaseModel):
    """Automação/Fluxo."""
    class Trigger(models.TextChoices):
        ORDER_PLACED = 'order_placed', 'Pedido Realizado'
        PAYMENT_CONFIRMED = 'payment_confirmed', 'Pagamento Confirmado'
        CART_ABANDONED = 'cart_abandoned', 'Carrinho Abandonado'
        WELCOME = 'welcome', 'Boas-vindas'
    
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='automations')
    
    name = models.CharField(max_length=255)
    trigger = models.CharField(max_length=50, choices=Trigger.choices)
    
    # Ações
    actions = models.JSONField(default=list)
    
    # Condições
    conditions = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['name']


class ScheduledMessage(BaseModel):
    """Mensagem agendada."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        SENT = 'sent', 'Enviada'
        FAILED = 'failed', 'Falhou'
        CANCELLED = 'cancelled', 'Cancelada'
    
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='scheduled_messages')
    
    recipient = models.CharField(max_length=255)
    channel = models.CharField(max_length=20, default='whatsapp')
    content = models.JSONField(default=dict)
    
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        ordering = ['scheduled_at']
