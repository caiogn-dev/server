"""Avisos de status passam a usar o texto do painel (19/10/2026).

Só troca o texto padrão antigo; mensagem que o dono editou fica como está.
Os textos estão copiados aqui (e não importados) para a migração não mudar
de comportamento se `textos_de_aviso` mudar depois.
"""
from django.db import migrations

ANTIGOS = {
    'order_confirmed': (
        "🎉 Pedido confirmado!\n\n"
        "Pedido #{order_number} está confirmado e já entrou na fila."
    ),
    'order_preparing': (
        "👨‍🍳 Estamos preparando seu pedido #{order_number}.\n\n"
        "Em breve estará a caminho!"
    ),
    'order_out_for_delivery': (
        "📍 Pedido #{order_number} está a caminho!\n\n"
        "Fique atento ao entregador."
    ),
    'order_delivered': (
        "🍽️ Pedido #{order_number} entregue!\n\n"
        "Esperamos que aproveite e conte com a gente sempre."
    ),
}

NOVOS = {
    'order_confirmed': (
        "✅ *Pedido Confirmado!*\n\n"
        "Olá {primeiro_nome}, recebemos seu pedido #{order_number}.\n\n"
        "💰 *Total:* R$ {total}\n"
        "⏱️ *Tempo:* {tempo} min\n\n"
        "Vamos preparar com carinho!"
    ),
    'order_preparing': (
        "👨‍🍳 *Seu pedido está sendo preparado!*\n\n"
        "Olá {primeiro_nome},\n\n"
        "Pedido #{order_number} em preparação.\n"
        "⏱️ Falta aproximadamente {tempo} minutos!"
    ),
    'order_out_for_delivery': (
        "🛵 *Seu pedido saiu para entrega!*\n\n"
        "Olá {primeiro_nome},\n\n"
        "Pedido #{order_number} a caminho!\n"
        "📍 {endereco}"
    ),
    'order_delivered': (
        "✨ *Pedido {entregue_ou_retirado}!*\n\n"
        "Olá {primeiro_nome},\n\n"
        "Seu pedido #{order_number} foi {entregue_ou_retirado}! 🎉\n\n"
        "Esperamos que aproveite!"
    ),
}


def trocar(apps, schema_editor):
    AutoMessage = apps.get_model('automation', 'AutoMessage')
    for evento, antigo in ANTIGOS.items():
        AutoMessage.objects.filter(event_type=evento, message_text=antigo).update(
            message_text=NOVOS[evento],
        )


def desfazer(apps, schema_editor):
    AutoMessage = apps.get_model('automation', 'AutoMessage')
    for evento, novo in NOVOS.items():
        AutoMessage.objects.filter(event_type=evento, message_text=novo).update(
            message_text=ANTIGOS[evento],
        )


class Migration(migrations.Migration):
    dependencies = [('automation', '0017_customersession_delivery_address_and_more')]
    operations = [migrations.RunPython(trocar, desfazer)]
