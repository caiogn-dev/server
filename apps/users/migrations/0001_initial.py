import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='UnifiedUser',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(blank=True, null=True, unique=True, verbose_name='Email')),
                ('phone_number', models.CharField(db_index=True, max_length=20, unique=True, verbose_name='Telefone')),
                ('google_id', models.CharField(blank=True, max_length=100, null=True, unique=True, verbose_name='Google ID')),
                ('name', models.CharField(max_length=255, verbose_name='Nome')),
                ('profile_picture', models.URLField(blank=True, verbose_name='Foto de Perfil')),
                ('total_orders', models.PositiveIntegerField(default=0, verbose_name='Total de Pedidos')),
                ('total_spent', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Total Gasto')),
                ('last_order_at', models.DateTimeField(blank=True, null=True, verbose_name='Último Pedido em')),
                ('has_abandoned_cart', models.BooleanField(default=False, verbose_name='Tem Carrinho Abandonado')),
                ('abandoned_cart_value', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Valor do Carrinho')),
                ('abandoned_cart_items', models.JSONField(blank=True, default=list, verbose_name='Itens do Carrinho')),
                ('abandoned_cart_since', models.DateTimeField(blank=True, null=True, verbose_name='Carrinho Abandonado desde')),
                ('first_seen_at', models.DateTimeField(auto_now_add=True, verbose_name='Visto primeiro em')),
                ('last_seen_at', models.DateTimeField(auto_now=True, verbose_name='Visto última vez em')),
                ('is_active', models.BooleanField(default=True, verbose_name='Ativo')),
            ],
            options={
                'verbose_name': 'Usuário Unificado',
                'verbose_name_plural': 'Usuários Unificados',
                'db_table': 'unified_users',
                'ordering': ['-last_seen_at'],
            },
        ),
        migrations.CreateModel(
            name='UnifiedUserActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('activity_type', models.CharField(
                    choices=[
                        ('whatsapp_message', 'Mensagem WhatsApp'),
                        ('site_login', 'Login no Site'),
                        ('site_order', 'Pedido no Site'),
                        ('cart_updated', 'Carrinho Atualizado'),
                        ('profile_updated', 'Perfil Atualizado'),
                    ],
                    max_length=50,
                    verbose_name='Tipo',
                )),
                ('description', models.TextField(blank=True, verbose_name='Descrição')),
                ('metadata', models.JSONField(blank=True, default=dict, verbose_name='Metadados')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='activities',
                    to='users.unifieduser',
                    verbose_name='Usuário',
                )),
            ],
            options={
                'verbose_name': 'Atividade',
                'verbose_name_plural': 'Atividades',
                'db_table': 'unified_user_activities',
                'ordering': ['-created_at'],
            },
        ),
    ]
