# Generated manually for marketing app

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('stores', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailTemplate',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('template_type', models.CharField(choices=[('coupon', 'Cupom de Desconto'), ('welcome', 'Boas-vindas'), ('promotion', 'Promoção'), ('abandoned_cart', 'Carrinho Abandonado'), ('order_confirmation', 'Confirmação de Pedido'), ('newsletter', 'Newsletter'), ('custom', 'Personalizado')], default='custom', max_length=30)),
                ('subject', models.CharField(max_length=255)),
                ('html_content', models.TextField()),
                ('text_content', models.TextField(blank=True)),
                ('preview_text', models.CharField(blank=True, max_length=255)),
                ('thumbnail_url', models.URLField(blank=True)),
                ('variables', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_email_templates', to=settings.AUTH_USER_MODEL)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_templates', to='stores.store')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Subscriber',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254)),
                ('name', models.CharField(blank=True, max_length=255)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('status', models.CharField(choices=[('active', 'Ativo'), ('unsubscribed', 'Descadastrado'), ('bounced', 'Bounce'), ('complained', 'Reclamação')], default='active', max_length=20)),
                ('tags', models.JSONField(blank=True, default=list)),
                ('custom_fields', models.JSONField(blank=True, default=dict)),
                ('source', models.CharField(blank=True, max_length=50)),
                ('total_orders', models.IntegerField(default=0)),
                ('total_spent', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('last_order_at', models.DateTimeField(blank=True, null=True)),
                ('accepts_marketing', models.BooleanField(default=True)),
                ('subscribed_at', models.DateTimeField(auto_now_add=True)),
                ('unsubscribed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscribers', to='stores.store')),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('store', 'email')},
            },
        ),
        migrations.CreateModel(
            name='EmailCampaign',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('subject', models.CharField(max_length=255)),
                ('html_content', models.TextField()),
                ('text_content', models.TextField(blank=True)),
                ('from_name', models.CharField(blank=True, max_length=100)),
                ('from_email', models.EmailField(blank=True, max_length=254)),
                ('reply_to', models.EmailField(blank=True, max_length=254)),
                ('audience_type', models.CharField(choices=[('all', 'Todos os clientes'), ('segment', 'Segmento'), ('custom', 'Lista personalizada')], default='all', max_length=20)),
                ('audience_filters', models.JSONField(blank=True, default=dict)),
                ('recipient_list', models.JSONField(blank=True, default=list)),
                ('status', models.CharField(choices=[('draft', 'Rascunho'), ('scheduled', 'Agendada'), ('sending', 'Enviando'), ('sent', 'Enviada'), ('paused', 'Pausada'), ('cancelled', 'Cancelada')], default='draft', max_length=20)),
                ('scheduled_at', models.DateTimeField(blank=True, null=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('total_recipients', models.IntegerField(default=0)),
                ('emails_sent', models.IntegerField(default=0)),
                ('emails_delivered', models.IntegerField(default=0)),
                ('emails_opened', models.IntegerField(default=0)),
                ('emails_clicked', models.IntegerField(default=0)),
                ('emails_bounced', models.IntegerField(default=0)),
                ('emails_unsubscribed', models.IntegerField(default=0)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_email_campaigns', to=settings.AUTH_USER_MODEL)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_campaigns', to='stores.store')),
                ('template', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='campaigns', to='marketing.emailtemplate')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='EmailRecipient',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254)),
                ('name', models.CharField(blank=True, max_length=255)),
                ('status', models.CharField(choices=[('pending', 'Pendente'), ('sent', 'Enviado'), ('delivered', 'Entregue'), ('opened', 'Aberto'), ('clicked', 'Clicado'), ('bounced', 'Bounce'), ('unsubscribed', 'Descadastrado'), ('failed', 'Falhou')], default='pending', max_length=20)),
                ('resend_id', models.CharField(blank=True, max_length=100)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('delivered_at', models.DateTimeField(blank=True, null=True)),
                ('opened_at', models.DateTimeField(blank=True, null=True)),
                ('clicked_at', models.DateTimeField(blank=True, null=True)),
                ('error_code', models.CharField(blank=True, max_length=50)),
                ('error_message', models.TextField(blank=True)),
                ('variables', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recipients', to='marketing.emailcampaign')),
            ],
            options={
                'unique_together': {('campaign', 'email')},
            },
        ),
        migrations.AddIndex(
            model_name='emailtemplate',
            index=models.Index(fields=['store', 'template_type'], name='marketing_e_store_i_028923_idx'),
        ),
        migrations.AddIndex(
            model_name='subscriber',
            index=models.Index(fields=['store', 'status'], name='marketing_s_store_i_75c7bb_idx'),
        ),
        migrations.AddIndex(
            model_name='subscriber',
            index=models.Index(fields=['email'], name='marketing_s_email_7ce228_idx'),
        ),
        migrations.AddIndex(
            model_name='emailcampaign',
            index=models.Index(fields=['store', 'status'], name='marketing_e_store_i_d5b86f_idx'),
        ),
        migrations.AddIndex(
            model_name='emailcampaign',
            index=models.Index(fields=['scheduled_at'], name='marketing_e_schedul_50e7d9_idx'),
        ),
        migrations.AddIndex(
            model_name='emailrecipient',
            index=models.Index(fields=['campaign', 'status'], name='marketing_e_campaig_e4e899_idx'),
        ),
        migrations.AddIndex(
            model_name='emailrecipient',
            index=models.Index(fields=['email'], name='marketing_e_email_a3c536_idx'),
        ),
    ]
