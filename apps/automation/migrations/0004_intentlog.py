# Generated migration for IntentLog model
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0001_initial'),
        ('whatsapp', '0001_initial'),
        ('automation', '0003_alter_automessage_event_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='IntentLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('phone_number', models.CharField(db_index=True, max_length=20)),
                ('message_text', models.TextField()),
                ('intent_type', models.CharField(db_index=True, max_length=50)),
                ('method', models.CharField(choices=[('regex', 'Regex'), ('llm', 'LLM'), ('none', 'Nenhum')], default='regex', max_length=10)),
                ('confidence', models.FloatField(default=0)),
                ('handler_used', models.CharField(blank=True, max_length=100)),
                ('response_text', models.TextField(blank=True)),
                ('response_type', models.CharField(choices=[('text', 'Texto'), ('buttons', 'Botões'), ('list', 'Lista'), ('interactive', 'Interativo')], default='text', max_length=20)),
                ('processing_time_ms', models.IntegerField(default=0)),
                ('entities', models.JSONField(blank=True, default=dict)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='intent_logs', to='automation.companyprofile')),
                ('conversation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='intent_logs', to='conversations.conversation')),
                ('message', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='intent_logs', to='whatsapp.message')),
            ],
            options={
                'verbose_name': 'Intent Log',
                'verbose_name_plural': 'Intent Logs',
                'db_table': 'intent_logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='intentlog',
            index=models.Index(fields=['company', '-created_at'], name='intent_logs_compa_f1f692_idx'),
        ),
        migrations.AddIndex(
            model_name='intentlog',
            index=models.Index(fields=['intent_type', '-created_at'], name='intent_logs_inten_029f4c_idx'),
        ),
        migrations.AddIndex(
            model_name='intentlog',
            index=models.Index(fields=['method', '-created_at'], name='intent_logs_metho_5e2e61_idx'),
        ),
        migrations.AddIndex(
            model_name='intentlog',
            index=models.Index(fields=['phone_number', '-created_at'], name='intent_logs_phone_8593b5_idx'),
        ),
    ]
