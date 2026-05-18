import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('instagram', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='InstagramWebhookEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('event_id', models.CharField(db_index=True, max_length=64, unique=True)),
                ('event_type', models.CharField(
                    choices=[
                        ('messages', 'Mensagem'),
                        ('messaging_seen', 'Leitura'),
                        ('messaging_postbacks', 'Postback'),
                        ('messaging_referral', 'Referral'),
                        ('comments', 'Comentário'),
                        ('mentions', 'Menção'),
                        ('other', 'Outro'),
                    ],
                    default='other',
                    max_length=30,
                )),
                ('payload', models.JSONField()),
                ('headers', models.JSONField(blank=True, default=dict)),
                ('processing_status', models.CharField(
                    choices=[
                        ('pending', 'Pendente'),
                        ('completed', 'Concluído'),
                        ('failed', 'Falhou'),
                        ('duplicate', 'Duplicado'),
                    ],
                    db_index=True,
                    default='pending',
                    max_length=20,
                )),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('account', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='webhook_events',
                    to='instagram.instagramaccount',
                )),
                ('related_message', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='webhook_events',
                    to='instagram.instagrammessage',
                )),
            ],
            options={
                'verbose_name': 'Instagram Webhook Event',
                'verbose_name_plural': 'Instagram Webhook Events',
                'db_table': 'instagram_webhook_events',
                'ordering': ['-created_at'],
            },
        ),
    ]
