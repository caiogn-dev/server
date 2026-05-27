import uuid

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class Flow(models.Model):
    """
    WhatsApp Flow — formulários nativos do WhatsApp.
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Rascunho'
        PUBLISHED = 'published', 'Publicado'
        ARCHIVED = 'archived', 'Arquivado'
        DEPRECATED = 'deprecated', 'Descontinuado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, verbose_name='Nome')
    description = models.TextField(blank=True, verbose_name='Descrição')

    json_definition = models.JSONField(
        default=dict,
        verbose_name='Definição JSON',
        help_text='Estrutura do flow conforme documentação do Meta',
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name='Status',
    )

    flow_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Flow ID (Meta)',
    )

    account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='flows',
        verbose_name='Conta WhatsApp',
    )

    category = models.CharField(max_length=100, blank=True, verbose_name='Categoria')
    version = models.CharField(max_length=20, default='1.0', verbose_name='Versão')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')
    published_at = models.DateTimeField(null=True, blank=True, verbose_name='Publicado em')

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_flows',
        verbose_name='Criado por',
    )

    class Meta:
        app_label = 'whatsapp'
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
        return self.status == self.Status.PUBLISHED and self.flow_id is not None


class FlowResponse(models.Model):
    """Respostas de flows enviados aos usuários."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        COMPLETED = 'completed', 'Completo'
        EXPIRED = 'expired', 'Expirado'
        ERROR = 'error', 'Erro'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    flow = models.ForeignKey(
        'whatsapp.Flow',
        on_delete=models.CASCADE,
        related_name='responses',
        verbose_name='Flow',
    )

    from_number = models.CharField(max_length=20, verbose_name='Número do remetente')

    flow_message_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='ID da Mensagem',
    )

    response_data = models.JSONField(default=dict, verbose_name='Dados da Resposta')
    raw_webhook_data = models.JSONField(default=dict, verbose_name='Dados Brutos do Webhook')

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='Status',
    )

    final_screen = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Screen Final',
    )

    sent_at = models.DateTimeField(auto_now_add=True, verbose_name='Enviado em')
    responded_at = models.DateTimeField(null=True, blank=True, verbose_name='Respondido em')

    class Meta:
        app_label = 'whatsapp'
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
