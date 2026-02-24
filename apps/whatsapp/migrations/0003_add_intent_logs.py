# Generated manually - Intent Log Models

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0001_initial'),
        ('whatsapp', '0002_advancedtemplate_whatsappanalyticsreport_and_more'),
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
                ('method', models.CharField(choices=[('regex', 'Regex'), ('llm', 'LLM'), ('none', 'None')], db_index=True, default='regex', max_length=10)),
                ('confidence', models.FloatField(default=1.0)),
                ('handler_used', models.CharField(blank=True, max_length=100)),
                ('response_text', models.TextField(blank=True)),
                ('response_type', models.CharField(choices=[('text', 'Text'), ('buttons', 'Buttons'), ('list', 'List'), ('interactive', 'Interactive'), ('template', 'Template')], default='text', max_length=20)),
                ('processing_time_ms', models.IntegerField(default=0)),
                ('context', models.JSONField(blank=True, default=dict)),
                ('entities', models.JSONField(blank=True, default=dict)),
                ('account', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='intent_logs', to='whatsapp.whatsappaccount')),
                ('conversation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='intent_logs', to='conversations.conversation')),
                ('message', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='intent_logs', to='whatsapp.message')),
            ],
            options={
                'verbose_name': 'Intent Log',
                'verbose_name_plural': 'Intent Logs',
                'db_table': 'whatsapp_intent_logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='IntentDailyStats',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(db_index=True)),
                ('total_detected', models.IntegerField(default=0)),
                ('regex_count', models.IntegerField(default=0)),
                ('llm_count', models.IntegerField(default=0)),
                ('by_type', models.JSONField(default=dict)),
                ('avg_response_time_ms', models.IntegerField(default=0)),
                ('total_response_time_ms', models.IntegerField(default=0)),
                ('top_intents', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('account', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='intent_daily_stats', to='whatsapp.whatsappaccount')),
            ],
            options={
                'verbose_name': 'Intent Daily Stats',
                'verbose_name_plural': 'Intent Daily Stats',
                'db_table': 'whatsapp_intent_daily_stats',
                'ordering': ['-date'],
            },
        ),
        migrations.AddIndex(
            model_name='intentlog',
            index=models.Index(fields=['account', '-created_at'], name='whatsapp_in_account__bd0cf3_idx'),
        ),
        migrations.AddIndex(
            model_name='intentlog',
            index=models.Index(fields=['intent_type', '-created_at'], name='whatsapp_in_intent__3f4f9c_idx'),
        ),
        migrations.AddIndex(
            model_name='intentlog',
            index=models.Index(fields=['method', '-created_at'], name='whatsapp_in_method_8c5f9c_idx'),
        ),
        migrations.AddIndex(
            model_name='intentlog',
            index=models.Index(fields=['phone_number', '-created_at'], name='whatsapp_in_phone_n_8a5f9c_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='intentdailystats',
            unique_together={('date', 'account')},
        ),
    ]
