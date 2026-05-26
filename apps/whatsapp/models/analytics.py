import uuid

from django.db import models


class WhatsAppAnalytics(models.Model):
    """Métricas diárias de analytics do WhatsApp."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='analytics',
        verbose_name='Conta WhatsApp',
    )

    date = models.DateField(verbose_name='Data')

    total_conversations = models.PositiveIntegerField(default=0, verbose_name='Total Conversações')
    user_initiated = models.PositiveIntegerField(default=0, verbose_name='Iniciadas pelo Usuário')
    business_initiated = models.PositiveIntegerField(default=0, verbose_name='Iniciadas pelo Negócio')

    marketing_conversations = models.PositiveIntegerField(default=0, verbose_name='Marketing')
    utility_conversations = models.PositiveIntegerField(default=0, verbose_name='Utilidade')
    authentication_conversations = models.PositiveIntegerField(default=0, verbose_name='Autenticação')
    service_conversations = models.PositiveIntegerField(default=0, verbose_name='Serviço')

    messages_sent = models.PositiveIntegerField(default=0, verbose_name='Mensagens Enviadas')
    messages_delivered = models.PositiveIntegerField(default=0, verbose_name='Mensagens Entregues')
    messages_read = models.PositiveIntegerField(default=0, verbose_name='Mensagens Lidas')

    delivery_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Taxa de Entrega %')
    read_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Taxa de Leitura %')

    total_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name='Custo Total')
    marketing_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name='Custo Marketing')
    utility_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name='Custo Utilidade')
    authentication_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name='Custo Autenticação')
    service_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0, verbose_name='Custo Serviço')

    quality_rating = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Qualidade',
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    class Meta:
        app_label = 'whatsapp'
        db_table = 'whatsapp_analytics'
        verbose_name = 'Analytics do WhatsApp'
        verbose_name_plural = 'Analytics do WhatsApp'
        ordering = ['-date']
        unique_together = ['account', 'date']
        indexes = [
            models.Index(fields=['account', 'date'], name='wh_analytics_account_date_idx'),
            models.Index(fields=['date'], name='wh_analytics_date_idx'),
            models.Index(fields=['quality_rating'], name='wh_analytics_quality_idx'),
        ]

    def __str__(self):
        return "Analytics %s - %s" % (self.account.name, self.date)

    def calculate_rates(self):
        if self.messages_sent > 0:
            self.delivery_rate = (self.messages_delivered / self.messages_sent) * 100
            self.read_rate = (self.messages_read / self.messages_sent) * 100
            self.save()


class WhatsAppAnalyticsReport(models.Model):
    """Relatórios agendados de analytics."""

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
        verbose_name='Tipo de Relatório',
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name='Status',
    )

    accounts = models.ManyToManyField(
        'whatsapp.WhatsAppAccount',
        related_name='analytics_reports',
        verbose_name='Contas',
    )

    include_conversations = models.BooleanField(default=True, verbose_name='Incluir Conversações')
    include_messages = models.BooleanField(default=True, verbose_name='Incluir Mensagens')
    include_costs = models.BooleanField(default=True, verbose_name='Incluir Custos')
    include_quality = models.BooleanField(default=True, verbose_name='Incluir Qualidade')

    recipients = models.JSONField(default=list, verbose_name='Destinatários')

    schedule_day = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Dia do Agendamento',
    )

    schedule_time = models.TimeField(default='08:00', verbose_name='Horário')

    last_run_at = models.DateTimeField(null=True, blank=True, verbose_name='Última Execução')
    last_run_status = models.CharField(max_length=20, blank=True, verbose_name='Status da Última Execução')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    class Meta:
        app_label = 'whatsapp'
        db_table = 'whatsapp_analytics_reports'
        verbose_name = 'Relatório de Analytics'
        verbose_name_plural = 'Relatórios de Analytics'
        ordering = ['-created_at']

    def __str__(self):
        return self.name
