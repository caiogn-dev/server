"""Preenche o financeiro dos pedidos da 99 que entraram antes de 06/11, relendo o aviso guardado.

    python manage.py financeiro_dos_pedidos_da_99 --dry-run   # só mostra
    python manage.py financeiro_dos_pedidos_da_99 [--loja ce-saladas]

Grava `metadata['99food']['financeiro']` e `platform_discount` (desconto pago
pela 99, que volta para a receita). Idempotente; não apaga o recebido que veio
do extrato.
"""
from django.core.management.base import BaseCommand

from apps.stores.models import StoreOrder
from apps.stores.services import pedidos_da_99 as p99
from apps.webhooks.models import WebhookEvent

_DO_EXTRATO = ('recebido', 'comissao_taxas', 'fonte_recebido', 'venda_extrato')


def _precos_dos_avisos():
    """order_id → bloco price do orderNew mais antigo guardado."""
    precos = {}
    eventos = WebhookEvent.objects.filter(provider=p99.PROVEDOR, event_type='orderNew').order_by('created_at')
    for evento in eventos.iterator():
        payload = evento.payload if isinstance(evento.payload, dict) else {}
        dados = payload.get('data') if isinstance(payload.get('data'), dict) else {}
        info = dados.get('order_info') if isinstance(dados.get('order_info'), dict) else dados
        order_id = str(info.get('order_id') or dados.get('order_id') or '')
        if order_id and isinstance(info.get('price'), dict):
            precos.setdefault(order_id, info['price'])
    return precos


class Command(BaseCommand):
    help = 'Preenche venda de cardápio, descontos e desconto da 99 nos pedidos antigos da 99Food.'

    def add_arguments(self, parser):
        parser.add_argument('--loja', help='slug da loja (padrão: todas)')
        parser.add_argument('--dry-run', action='store_true', help='só mostra, não grava')

    def handle(self, *args, loja=None, dry_run=False, **opts):
        precos = _precos_dos_avisos()
        pedidos = StoreOrder.objects.filter(source=p99.PROVEDOR).order_by('created_at')
        if loja:
            pedidos = pedidos.filter(store__slug=loja)
        atualizados = sem_aviso = 0
        for pedido in pedidos:
            dados = p99.dados_99(pedido)
            preco = precos.get(str(dados.get('order_id') or ''))
            if preco is None:
                sem_aviso += 1
                self.stdout.write(f'{pedido.order_number}: sem aviso orderNew guardado')
                continue
            antigo = dados.get('financeiro') if isinstance(dados.get('financeiro'), dict) else {}
            novo = p99.financeiro_do_preco(preco)
            for chave in _DO_EXTRATO:  # conciliação do extrato vale mais que o aviso
                if antigo.get(chave) is not None:
                    novo[chave] = antigo[chave]
            subsidio = min(p99.desconto_da_plataforma(novo), pedido.discount or 0)
            if novo == antigo and pedido.platform_discount == subsidio:
                continue
            atualizados += 1
            self.stdout.write(
                f'{pedido.order_number}: venda {novo["venda_cardapio"]} · pago pela 99 {subsidio} '
                f'(antes {pedido.platform_discount}) · total {pedido.total} (não muda)')
            if dry_run:
                continue
            p99._registrar(pedido, financeiro=novo)
            StoreOrder.objects.filter(pk=pedido.pk).update(platform_discount=subsidio)
        self.stdout.write(
            f'{atualizados} atualizados, {sem_aviso} sem aviso' + (' (simulação, nada gravado)' if dry_run else ''))
