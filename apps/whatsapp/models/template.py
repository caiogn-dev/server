import uuid

from django.db import models


class MessageTemplate(models.Model):
    """WhatsApp message template."""

    class TemplateStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    class TemplateCategory(models.TextChoices):
        MARKETING = 'marketing', 'Marketing'
        UTILITY = 'utility', 'Utility'
        AUTHENTICATION = 'authentication', 'Authentication'

    class TemplateClass(models.TextChoices):
        BASIC = 'basic', 'Basic'
        ADVANCED = 'advanced', 'Advanced'

    account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='templates',
    )

    template_id = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=255)
    language = models.CharField(max_length=10, default='pt_BR')
    category = models.CharField(max_length=20, choices=TemplateCategory.choices)
    status = models.CharField(
        max_length=20,
        choices=TemplateStatus.choices,
        default=TemplateStatus.PENDING,
    )

    components = models.JSONField(default=list)
    template_class = models.CharField(
        max_length=20,
        choices=TemplateClass.choices,
        default=TemplateClass.BASIC,
    )

    class Meta:
        app_label = 'whatsapp'
        db_table = 'whatsapp_templates'
        verbose_name = 'Message Template'
        verbose_name_plural = 'Message Templates'
        unique_together = ['account', 'name', 'language']

    def __str__(self):
        return f"{self.name} ({self.language}) - {self.status}"


class AdvancedTemplate(models.Model):
    """
    Templates avançados do WhatsApp.

    Suporta Carousel, Limited Time Offer, Authentication, Order Details.
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
        verbose_name='Tipo de Template',
    )

    config = models.JSONField(default=dict, verbose_name='Configuração')
    components = models.JSONField(default=list, verbose_name='Componentes')

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name='Status',
    )

    meta_template_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID no Meta',
    )

    account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='advanced_templates',
        verbose_name='Conta WhatsApp',
    )

    language = models.CharField(max_length=10, default='pt_BR', verbose_name='Idioma')
    category = models.CharField(max_length=20, default='MARKETING', verbose_name='Categoria')
    version = models.CharField(max_length=10, default='1.0', verbose_name='Versão')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name='Submetido em')
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='Aprovado em')

    rejection_reason = models.TextField(blank=True, verbose_name='Motivo da Rejeição')

    class Meta:
        app_label = 'whatsapp'
        db_table = 'whatsapp_advanced_templates'
        verbose_name = 'Template Avançado'
        verbose_name_plural = 'Templates Avançados'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['template_type', 'status'], name='wh_advtemp_type_status_idx'),
            models.Index(fields=['account', 'status'], name='wh_advtemp_account_status_idx'),
            models.Index(fields=['meta_template_id'], name='wh_advtemp_meta_id_idx'),
        ]

    def __str__(self):
        return "%s (%s)" % (self.name, self.get_template_type_display())

    def is_approved(self):
        return self.status == self.Status.APPROVED

    def is_rejected(self):
        return self.status == self.Status.REJECTED


class AdvancedTemplateLog(models.Model):
    """Log de envios de templates avançados."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        SENT = 'sent', 'Enviado'
        DELIVERED = 'delivered', 'Entregue'
        READ = 'read', 'Lido'
        FAILED = 'failed', 'Falhou'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    template = models.ForeignKey(
        'whatsapp.AdvancedTemplate',
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name='Template',
    )

    to_number = models.CharField(max_length=20, verbose_name='Número')

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='Status',
    )

    whatsapp_message_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID da Mensagem',
    )

    sent_data = models.JSONField(default=dict, verbose_name='Dados Enviados')
    error_message = models.TextField(blank=True, verbose_name='Erro')

    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='Enviado em')
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name='Entregue em')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='Lido em')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')

    class Meta:
        app_label = 'whatsapp'
        db_table = 'whatsapp_advanced_template_logs'
        verbose_name = 'Log de Template Avançado'
        verbose_name_plural = 'Logs de Templates Avançados'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['template', 'status'], name='wh_atlog_tpl_status_idx'),
            models.Index(fields=['to_number', 'status'], name='wh_atlog_to_status_idx'),
            models.Index(fields=['whatsapp_message_id'], name='wh_atlog_msg_id_idx'),
        ]

    def __str__(self):
        return "Log %s - %s" % (self.template.name, self.status)
