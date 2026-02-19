# Generated migration for WebhookDeadLetter and WebhookOutbox models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0001_initial'),  # Adjust as needed
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('webhooks', '0001_initial'),  # Adjust based on actual initial migration
    ]

    operations = [
        # Create WebhookDeadLetter model
        migrations.CreateModel(
            name='WebhookDeadLetter',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('provider', models.CharField(max_length=20, choices=[
                    ('whatsapp', 'WhatsApp'),
                    ('instagram', 'Instagram'),
                    ('mercadopago', 'Mercado Pago'),
                    ('automation', 'Automation'),
                    ('custom', 'Custom'),
                ])),
                ('event_type', models.CharField(max_length=100, db_index=True)),
                ('event_id', models.CharField(max_length=255, blank=True, db_index=True)),
                ('payload', models.JSONField()),
                ('headers', models.JSONField(default=dict)),
                ('query_params', models.JSONField(default=dict)),
                ('status', models.CharField(max_length=20, default='failed', choices=[
                    ('failed', 'Failed'),
                    ('reprocessing', 'Reprocessing'),
                    ('resolved', 'Resolved'),
                    ('discarded', 'Discarded'),
                ])),
                ('failure_reason', models.CharField(max_length=30, default='unknown', choices=[
                    ('processing_error', 'Processing Error'),
                    ('timeout', 'Timeout'),
                    ('validation_error', 'Validation Error'),
                    ('external_service_error', 'External Service Error'),
                    ('network_error', 'Network Error'),
                    ('unknown', 'Unknown'),
                ])),
                ('error_message', models.TextField()),
                ('error_traceback', models.TextField(blank=True)),
                ('retry_count', models.PositiveIntegerField(default=0)),
                ('max_retries_reached', models.BooleanField(default=False)),
                ('last_retry_at', models.DateTimeField(null=True, blank=True)),
                ('reprocessed_at', models.DateTimeField(null=True, blank=True)),
                ('reprocessing_result', models.JSONField(default=dict, blank=True)),
                ('failure_signature', models.CharField(max_length=255, blank=True, db_index=True, help_text='Hash of error type + message for grouping similar failures')),
                ('original_event', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dead_letter_entries', to='webhooks.webhookevent')),
                ('reprocessed_by', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reprocessed_webhooks', to=settings.AUTH_USER_MODEL)),
                ('store', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dead_letter_webhooks', to='stores.store')),
            ],
            options={
                'db_table': 'webhook_dead_letter',
                'verbose_name': 'Webhook Dead Letter',
                'verbose_name_plural': 'Webhook Dead Letters',
                'ordering': ['-created_at'],
            },
        ),
        # Create WebhookOutbox model
        migrations.CreateModel(
            name='WebhookOutbox',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('event_type', models.CharField(max_length=100, db_index=True)),
                ('payload', models.JSONField()),
                ('endpoint_url', models.URLField()),
                ('headers', models.JSONField(default=dict)),
                ('secret', models.CharField(max_length=255, blank=True, help_text='Secret for HMAC signature')),
                ('status', models.CharField(max_length=20, default='pending', choices=[
                    ('pending', 'Pending'),
                    ('processing', 'Processing'),
                    ('sent', 'Sent'),
                    ('failed', 'Failed'),
                    ('scheduled', 'Scheduled'),
                ])),
                ('priority', models.IntegerField(default=5, choices=[
                    (1, 'Low'),
                    (5, 'Normal'),
                    (10, 'High'),
                    (20, 'Critical'),
                ])),
                ('scheduled_at', models.DateTimeField(null=True, blank=True)),
                ('processed_at', models.DateTimeField(null=True, blank=True)),
                ('processing_started_at', models.DateTimeField(null=True, blank=True)),
                ('retry_count', models.PositiveIntegerField(default=0)),
                ('max_retries', models.PositiveIntegerField(default=3)),
                ('next_retry_at', models.DateTimeField(null=True, blank=True)),
                ('http_status', models.PositiveIntegerField(null=True, blank=True)),
                ('response_body', models.TextField(blank=True)),
                ('error_message', models.TextField(blank=True)),
                ('source_model', models.CharField(max_length=100, blank=True, help_text="Model that triggered the webhook (e.g., 'stores.StoreOrder')")),
                ('source_id', models.CharField(max_length=255, blank=True, help_text='ID of the source record')),
                ('idempotency_key', models.CharField(max_length=255, blank=True, db_index=True, help_text='Unique key to prevent duplicate processing')),
                ('store', models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.CASCADE, related_name='webhook_outbox', to='stores.store')),
            ],
            options={
                'db_table': 'webhook_outbox',
                'verbose_name': 'Webhook Outbox',
                'verbose_name_plural': 'Webhook Outbox',
                'ordering': ['-priority', 'created_at'],
            },
        ),
        # Add indexes for WebhookDeadLetter
        migrations.AddIndex(
            model_name='webhookdeadletter',
            index=models.Index(fields=['status', 'failure_reason'], name='webhook_dlq_status_reason_idx'),
        ),
        migrations.AddIndex(
            model_name='webhookdeadletter',
            index=models.Index(fields=['provider', 'status'], name='webhook_dlq_provider_status_idx'),
        ),
        migrations.AddIndex(
            model_name='webhookdeadletter',
            index=models.Index(fields=['failure_signature'], name='webhook_dlq_signature_idx'),
        ),
        migrations.AddIndex(
            model_name='webhookdeadletter',
            index=models.Index(fields=['event_id'], name='webhook_dlq_event_id_idx'),
        ),
        # Add indexes for WebhookOutbox
        migrations.AddIndex(
            model_name='webhookoutbox',
            index=models.Index(fields=['status', 'priority', 'created_at'], name='webhook_outbox_status_priority_idx'),
        ),
        migrations.AddIndex(
            model_name='webhookoutbox',
            index=models.Index(fields=['status', 'next_retry_at'], name='webhook_outbox_status_retry_idx'),
        ),
        migrations.AddIndex(
            model_name='webhookoutbox',
            index=models.Index(fields=['idempotency_key'], name='webhook_outbox_idempotency_idx'),
        ),
        migrations.AddIndex(
            model_name='webhookoutbox',
            index=models.Index(fields=['store', 'status'], name='webhook_outbox_store_status_idx'),
        ),
        migrations.AddIndex(
            model_name='webhookoutbox',
            index=models.Index(fields=['event_type', 'status'], name='webhook_outbox_event_status_idx'),
        ),
    ]
