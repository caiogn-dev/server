"""Importa o extrato de repasse da 99Food e concilia pedido a pedido.

    python manage.py importar_extrato_99 extrato.csv --loja ce-saladas --dry-run
    python manage.py importar_extrato_99 extrato.csv --loja ce-saladas
    python manage.py importar_extrato_99 extrato.csv --loja ce-saladas --data 2026-11-06

CSV com cabeçalho: pedido (#N do dia ou id da 99), data (opcional; sem ela use
--data), venda (opcional) e recebido. Reimportar o mesmo extrato não muda nada.
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.stores.models import Store
from apps.stores.services import repasse_99


class Command(BaseCommand):
    help = 'Concilia o extrato de repasse da 99Food com os pedidos (recebido e comissão).'

    def add_arguments(self, parser):
        parser.add_argument('arquivo')
        parser.add_argument('--loja', required=True, help='slug da loja')
        parser.add_argument('--data', help='AAAA-MM-DD, para linhas sem data')
        parser.add_argument('--dry-run', action='store_true', help='só mostra, não grava')

    def handle(self, *args, arquivo, loja, data=None, dry_run=False, **opts):
        store = Store.objects.filter(slug=loja).first()
        if store is None:
            raise CommandError(f'Loja {loja!r} não existe.')
        try:
            with open(arquivo, encoding='utf-8-sig') as f:
                texto = f.read()
            linhas = repasse_99.ler_extrato(texto, data_padrao=date.fromisoformat(data) if data else None)
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        resultado = repasse_99.conciliar(store, linhas, gravar=not dry_run)
        for linha, pedido in resultado['conciliados']:
            fin = (pedido.metadata or {}).get('99food', {}).get('financeiro') or {}
            self.stdout.write(
                f'#{linha.pedido} → {pedido.order_number}: venda {fin.get("venda_cardapio") or linha.venda} '
                f'recebido {linha.recebido}')
        for linha, pedido, venda in resultado['divergentes']:
            self.stdout.write(self.style.WARNING(
                f'linha {linha.numero_da_linha}: venda no extrato {linha.venda} ≠ cardápio {venda} ({pedido.order_number})'))
        for linha in resultado['sem_pedido']:
            self.stdout.write(self.style.WARNING(f'linha {linha.numero_da_linha}: pedido {linha.pedido} não encontrado'))
        venda = sum((l.venda or 0 for l, _ in resultado['conciliados']), 0)
        recebido = sum((l.recebido for l, _ in resultado['conciliados']), 0)
        self.stdout.write(
            f'{len(resultado["conciliados"])} conciliados, {len(resultado["sem_pedido"])} sem pedido, '
            f'{len(resultado["divergentes"])} com venda divergente · venda {venda} · recebido {recebido}'
            + (' (simulação, nada gravado)' if dry_run else ''))
