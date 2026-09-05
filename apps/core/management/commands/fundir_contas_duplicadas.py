"""Funde as contas de login que são a mesma pessoa.

O cadastro de cliente já tem trava de banco desde 04/09. Esta é a camada de
baixo — a CONTA — que a trava não cobre: a mesma pessoa entrou pelo WhatsApp
(número sem o nono dígito) e pelo site (com ele) e virou dois logins.

SEM `--aplicar` NÃO ESCREVE NADA. Fusão de conta apaga um login com histórico
de compra e repointa pedido pago; ver a lista antes é o mínimo.
"""
from django.core.management.base import BaseCommand

from apps.core.services.fusao_de_contas import FusaoDeContas


class Command(BaseCommand):
    help = 'Funde contas duplicadas por telefone.'

    def add_arguments(self, parser):
        parser.add_argument('--telefone', action='append', default=[],
                            help='restringe a estes telefones (pode repetir)')
        parser.add_argument('--aplicar', action='store_true')

    def handle(self, *args, **opts):
        planos = FusaoDeContas.planejar(apenas=opts['telefone'] or None)

        self.stdout.write(f'pessoas com conta duplicada: {len(planos)}')
        for plano in planos:
            self.stdout.write(f'  {plano}')
            for u in [plano.fica, *plano.saem]:
                marca = 'FICA ' if u.id == plano.fica.id else 'sai  '
                pagos = FusaoDeContas._pagos(u)
                nome = f'{u.first_name} {u.last_name}'.strip() or '(sem nome)'
                self.stdout.write(
                    f'      {marca} #{u.id:<6} {nome[:24]:26} pagos={pagos} '
                    f'email={(u.email or "")[:34]}'
                )

        if not opts['aplicar']:
            self.stdout.write(self.style.WARNING('\nNada gravado. Use --aplicar para valer.'))
            return

        total = FusaoDeContas.aplicar(planos)
        self.stdout.write(self.style.SUCCESS(f'\n{total} contas fundidas.'))
