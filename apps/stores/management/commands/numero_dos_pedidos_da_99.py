"""Preenche o "#N" da 99 nos pedidos que entraram sem ele, relendo o aviso guardado.

    python manage.py numero_dos_pedidos_da_99            # só mostra
    python manage.py numero_dos_pedidos_da_99 --gravar
"""
import json

from django.core.management.base import BaseCommand

from apps.stores.models import StoreOrder
from apps.stores.services import pedidos_da_99 as p99
from apps.webhooks.models import WebhookEvent


def _avisos_do_pedido(order_id: str):
    eventos = WebhookEvent.objects.filter(provider=p99.PROVEDOR).order_by('-created_at')[:2000]
    for evento in eventos:
        payload = evento.payload if isinstance(evento.payload, dict) else {}
        if order_id in json.dumps(payload, default=str):
            yield payload


def _numero_no_aviso(payload: dict):
    dados = payload.get('data') if isinstance(payload.get('data'), dict) else payload
    info = dados.get('order_info') if isinstance(dados.get('order_info'), dict) else dados
    return p99.numero_do_pedido(info, dados)


class Command(BaseCommand):
    help = 'Preenche o número curto da 99 nos pedidos que entraram sem ele.'

    def add_arguments(self, parser):
        parser.add_argument('--gravar', action='store_true')

    def handle(self, *args, gravar=False, **opts):
        for pedido in StoreOrder.objects.filter(source=p99.PROVEDOR).order_by('-created_at')[:200]:
            dados = p99.dados_99(pedido)
            if dados.get('numero'):
                continue
            order_id = str(dados.get('order_id') or '')
            numero = next((n for n in map(_numero_no_aviso, _avisos_do_pedido(order_id)) if n), None) \
                if order_id else None
            self.stdout.write(f'{pedido.order_number}: {numero if numero else "sem número no aviso"}')
            if numero and gravar:
                p99._registrar(pedido, numero=numero)
