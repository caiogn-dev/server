from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel

User = get_user_model()


class ReportSchedule(BaseModel):
    """
    Scheduled automated reports.
    """

    class Frequency(models.TextChoices):
        DAILY = 'daily', 'Diário'
        WEEKLY = 'weekly', 'Semanal'
        MONTHLY = 'monthly', 'Mensal'

    class ReportType(models.TextChoices):
        MESSAGES = 'messages', 'Mensagens'
        ORDERS = 'orders', 'Pedidos'
        CONVERSATIONS = 'conversations', 'Conversas'
        AUTOMATION = 'automation', 'Automação'
        PAYMENTS = 'payments', 'Pagamentos'
        FULL = 'full', 'Completo'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Ativo'
        PAUSED = 'paused', 'Pausado'
        DISABLED = 'disabled', 'Desativado'

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    report_type = models.CharField(
        max_length=20,
        choices=ReportType.choices,
        default=ReportType.FULL
    )

    account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='report_schedules',
        help_text="Filter by account (optional)"
    )
    company = models.ForeignKey(
        'automation.CompanyProfile',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='report_schedules',
        help_text="Filter by company (optional)"
    )

    frequency = models.CharField(
        max_length=20,
        choices=Frequency.choices,
        default=Frequency.WEEKLY
    )
    day_of_week = models.PositiveSmallIntegerField(
        default=1,
        help_text="Day of week for weekly reports (1=Monday, 7=Sunday)"
    )
    day_of_month = models.PositiveSmallIntegerField(
        default=1,
        help_text="Day of month for monthly reports"
    )
    hour = models.PositiveSmallIntegerField(
        default=8,
        help_text="Hour to send report (0-23)"
    )
    timezone = models.CharField(max_length=50, default='America/Sao_Paulo')

    recipients = models.JSONField(
        default=list,
        help_text="List of email addresses to send report to"
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    run_count = models.PositiveIntegerField(default=0)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='report_schedules'
    )

    include_charts = models.BooleanField(default=True)
    export_format = models.CharField(
        max_length=10,
        default='xlsx',
        choices=[('csv', 'CSV'), ('xlsx', 'Excel')]
    )
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = 'automation'
        db_table = 'report_schedules'
        verbose_name = 'Report Schedule'
        verbose_name_plural = 'Report Schedules'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()})"

    def calculate_next_run(self):
        """Calculate the next run time based on frequency."""
        from django.utils import timezone as tz
        from datetime import timedelta
        import pytz

        local_tz = pytz.timezone(self.timezone)
        now = tz.now().astimezone(local_tz)

        if self.frequency == self.Frequency.DAILY:
            next_run = now.replace(hour=self.hour, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)

        elif self.frequency == self.Frequency.WEEKLY:
            days_ahead = self.day_of_week - now.isoweekday()
            if days_ahead < 0 or (days_ahead == 0 and now.hour >= self.hour):
                days_ahead += 7
            next_run = now.replace(hour=self.hour, minute=0, second=0, microsecond=0)
            next_run += timedelta(days=days_ahead)

        elif self.frequency == self.Frequency.MONTHLY:
            next_run = now.replace(day=self.day_of_month, hour=self.hour, minute=0, second=0, microsecond=0)
            if next_run <= now:
                if now.month == 12:
                    next_run = next_run.replace(year=now.year + 1, month=1)
                else:
                    next_run = next_run.replace(month=now.month + 1)

        self.next_run_at = next_run.astimezone(pytz.UTC)
        return self.next_run_at


class GeneratedReport(BaseModel):
    """
    Generated report files.
    """

    class Status(models.TextChoices):
        GENERATING = 'generating', 'Gerando'
        COMPLETED = 'completed', 'Concluído'
        FAILED = 'failed', 'Falhou'

    schedule = models.ForeignKey(
        'automation.ReportSchedule',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='generated_reports'
    )

    name = models.CharField(max_length=255)
    report_type = models.CharField(max_length=20)

    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.GENERATING
    )

    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    file_format = models.CharField(max_length=10, default='xlsx')

    records_count = models.PositiveIntegerField(default=0)
    generation_time_ms = models.PositiveIntegerField(default=0)

    error_message = models.TextField(blank=True)

    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_recipients = models.JSONField(default=list, blank=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_reports'
    )

    class Meta:
        app_label = 'automation'
        db_table = 'generated_reports'
        verbose_name = 'Generated Report'
        verbose_name_plural = 'Generated Reports'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.created_at.strftime('%Y-%m-%d')})"
