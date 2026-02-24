"""
Intent Detection Models - Modelos para logs de detecção de intenções.
"""
from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel

User = get_user_model()


class IntentLog(BaseModel):
    """
    Log de detecção de intenção.
    
    Armazena cada detecção de intenção para análise e métricas.
    """
    
    class DetectionMethod(models.TextChoices):
        REGEX = 'regex', 'Regex'
        LLM = 'llm', 'LLM'
        NONE = 'none', 'None'
    
    class ResponseType(models.TextChoices):
        TEXT = 'text', 'Text'
        BUTTONS = 'buttons', 'Buttons'
        LIST = 'list', 'List'
        INTERACTIVE = 'interactive', 'Interactive'
        TEMPLATE = 'template', 'Template'
    
    # Relacionamentos
    account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='whatsapp_intent_logs',
        null=True,
        blank=True
    )
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.SET_NULL,
        related_name='whatsapp_intent_logs',
        null=True,
        blank=True
    )
    message = models.ForeignKey(
        'whatsapp.Message',
        on_delete=models.SET_NULL,
        related_name='whatsapp_intent_logs',
        null=True,
        blank=True
    )
    
    # Identificação
    phone_number = models.CharField(max_length=20, db_index=True)
    message_text = models.TextField()
    
    # Detecção
    intent_type = models.CharField(max_length=50, db_index=True)
    method = models.CharField(
        max_length=10,
        choices=DetectionMethod.choices,
        default=DetectionMethod.REGEX,
        db_index=True
    )
    confidence = models.FloatField(default=1.0)
    
    # Handler/Resposta
    handler_used = models.CharField(max_length=100, blank=True)
    response_text = models.TextField(blank=True)
    response_type = models.CharField(
        max_length=20,
        choices=ResponseType.choices,
        default=ResponseType.TEXT
    )
    
    # Performance
    processing_time_ms = models.IntegerField(default=0)
    
    # Contexto adicional
    context = models.JSONField(default=dict, blank=True)
    entities = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'whatsapp_intent_logs'
        verbose_name = 'Intent Log'
        verbose_name_plural = 'Intent Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', '-created_at']),
            models.Index(fields=['intent_type', '-created_at']),
            models.Index(fields=['method', '-created_at']),
            models.Index(fields=['phone_number', '-created_at']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.intent_type} ({self.method}) - {self.phone_number}"


class IntentDailyStats(models.Model):
    """
    Estatísticas diárias de intenções.
    
    Agrega dados por dia para performance em dashboards.
    """
    
    date = models.DateField(db_index=True)
    account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='intent_daily_stats',
        null=True,
        blank=True
    )
    
    # Contagens
    total_detected = models.IntegerField(default=0)
    regex_count = models.IntegerField(default=0)
    llm_count = models.IntegerField(default=0)
    
    # Por tipo de intenção (JSON para flexibilidade)
    by_type = models.JSONField(default=dict)
    
    # Performance
    avg_response_time_ms = models.IntegerField(default=0)
    total_response_time_ms = models.IntegerField(default=0)
    
    # Top intenções do dia
    top_intents = models.JSONField(default=list)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'whatsapp_intent_daily_stats'
        verbose_name = 'Intent Daily Stats'
        verbose_name_plural = 'Intent Daily Stats'
        unique_together = ['date', 'account']
        ordering = ['-date']

    def __str__(self):
        return f"{self.date} - {self.total_detected} intenções"
