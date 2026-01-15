# Generated manually for email automation models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('stores', '0001_initial'),
        ('marketing', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailAutomation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('trigger_type', models.CharField(choices=[
                    ('new_user', 'Novo Usuário'),
                    ('welcome', 'Boas-vindas'),
                    ('order_confirmed', 'Pedido Confirmado'),
                    ('order_preparing', 'Pedido em Preparo'),
                    ('order_shipped', 'Pedido Enviado'),
                    ('order_delivered', 'Pedido Entregue'),
                    ('order_cancelled', 'Pedido Cancelado'),
                    ('payment_confirmed', 'Pagamento Confirmado'),
                    ('payment_failed', 'Pagamento Falhou'),
                    ('cart_abandoned', 'Carrinho Abandonado'),
                    ('coupon_sent', 'Cupom Enviado'),
                    ('birthday', 'Aniversário'),
                    ('review_request', 'Solicitar Avaliação'),
                ], max_length=30)),
                ('subject', models.CharField(max_length=255)),
                ('html_content', models.TextField()),
                ('delay_minutes', models.PositiveIntegerField(default=0, help_text='Minutes to wait before sending (0 = immediate)')),
                ('is_active', models.BooleanField(default=True)),
                ('conditions', models.JSONField(blank=True, default=dict, help_text='Additional conditions for triggering')),
                ('total_sent', models.PositiveIntegerField(default=0)),
                ('total_opened', models.PositiveIntegerField(default=0)),
                ('total_clicked', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_automations', to='stores.store')),
                ('template', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='automations', to='marketing.emailtemplate')),
            ],
            options={
                'ordering': ['trigger_type', 'name'],
            },
        ),
        migrations.CreateModel(
            name='EmailAutomationLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('recipient_email', models.EmailField(max_length=254)),
                ('recipient_name', models.CharField(blank=True, max_length=255)),
                ('status', models.CharField(choices=[
                    ('pending', 'Pendente'),
                    ('sent', 'Enviado'),
                    ('failed', 'Falhou'),
                    ('opened', 'Aberto'),
                    ('clicked', 'Clicado'),
                ], default='pending', max_length=20)),
                ('trigger_data', models.JSONField(blank=True, default=dict)),
                ('resend_id', models.CharField(blank=True, max_length=100)),
                ('scheduled_at', models.DateTimeField(blank=True, null=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('opened_at', models.DateTimeField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('automation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='marketing.emailautomation')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='emailautomation',
            index=models.Index(fields=['store', 'trigger_type', 'is_active'], name='marketing_e_store_i_idx'),
        ),
        migrations.AddIndex(
            model_name='emailautomationlog',
            index=models.Index(fields=['automation', 'status'], name='marketing_e_automat_idx'),
        ),
        migrations.AddIndex(
            model_name='emailautomationlog',
            index=models.Index(fields=['recipient_email'], name='marketing_e_recipie_idx'),
        ),
    ]
