# Migration to expand EventType choices in AutoMessage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0002_intentlog'),
    ]

    operations = [
        migrations.AlterField(
            model_name='automessage',
            name='event_type',
            field=models.CharField(
                max_length=30,
                choices=[
                    ('welcome', 'Boas-vindas'),
                    ('menu', 'Cardápio/Catálogo'),
                    ('business_hours', 'Horário de Funcionamento'),
                    ('out_of_hours', 'Fora do Horário'),
                    ('faq', 'Perguntas Frequentes'),
                    ('cart_created', 'Carrinho Criado'),
                    ('cart_abandoned', 'Carrinho Abandonado'),
                    ('cart_reminder', 'Lembrete de Carrinho'),
                    ('cart_reminder_30', 'Lembrete Carrinho (30min)'),
                    ('cart_reminder_2h', 'Lembrete Carrinho (2h)'),
                    ('cart_reminder_24h', 'Lembrete Carrinho (24h)'),
                    ('pix_generated', 'PIX Gerado'),
                    ('pix_reminder', 'Lembrete de PIX'),
                    ('pix_expired', 'PIX Expirado'),
                    ('payment_confirmed', 'Pagamento Confirmado'),
                    ('payment_failed', 'Pagamento Falhou'),
                    ('payment_reminder_1', 'Lembrete Pagamento (30min)'),
                    ('payment_reminder_2', 'Lembrete Pagamento (2h)'),
                    ('order_received', 'Pedido Recebido'),
                    ('order_confirmed', 'Pedido Confirmado'),
                    ('order_preparing', 'Pedido em Preparo'),
                    ('order_ready', 'Pedido Pronto'),
                    ('order_shipped', 'Pedido Enviado'),
                    ('order_out_for_delivery', 'Saiu para Entrega'),
                    ('order_delivered', 'Pedido Entregue'),
                    ('order_cancelled', 'Pedido Cancelado'),
                    ('feedback_request', 'Solicitar Avaliação'),
                    ('feedback_received', 'Avaliação Recebida'),
                    ('human_handoff', 'Transferido para Humano'),
                    ('human_assigned', 'Atendente Atribuído'),
                    ('custom', 'Personalizado'),
                ],
            ),
        ),
    ]
