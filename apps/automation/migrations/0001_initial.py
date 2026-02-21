# Generated initial migration
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('whatsapp', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CompanyProfile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_name', models.CharField(max_length=255)),
                ('whatsapp_number', models.CharField(blank=True, max_length=20)),
                ('address', models.TextField(blank=True)),
                ('business_hours', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='AutoMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('event_type', models.CharField(choices=[('greeting', 'Saudação Inicial'), ('menu_request', 'Pedido de Cardápio'), ('price_inquiry', 'Consulta de Preço'), ('hours_inquiry', 'Consulta de Horário'), ('location_inquiry', 'Consulta de Localização'), ('order_status', 'Status do Pedido'), ('payment_info', 'Informações de Pagamento'), ('human_handover', 'Encaminhar para Humano'), ('fallback', 'Mensagem Padrão'), ('order_confirmation', 'Confirmação de Pedido'), ('cart_abandoned', 'Carrinho Abandonado'), ('payment_pending', 'Pagamento Pendente'), ('payment_confirmed', 'Pagamento Confirmado'), ('order_ready', 'Pedido Pronto'), ('order_delivered', 'Pedido Entregue'), ('custom', 'Evento Personalizado')], max_length=50)),
                ('message_text', models.TextField()),
                ('is_active', models.BooleanField(default=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='automessages', to='automation.companyprofile')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
