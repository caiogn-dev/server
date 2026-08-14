"""Preenche o caderno de endereços com o que já está nos pedidos antigos.

O conserto em `apps/users/signals.py` só vale de agora em diante. Este comando
resolve o passivo: clientes que já pediram com entrega e continuam aparecendo
sem endereço no PDV.

Medido na Cê Saladas em 14/ago, antes de rodar: 45 clientes com pedido de
entrega, 7 com endereço salvo.

Idempotente — `guardar_endereco_do_pedido` reaproveita o endereço que já
existe. Rodar duas vezes não duplica nada.

    python manage.py preencher_caderno_de_enderecos --dry-run
    python manage.py preencher_caderno_de_enderecos --loja ce-saladas
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.users.services.caderno_de_enderecos import guardar_endereco_do_pedido


class Command(BaseCommand):
    help = 'Salva no caderno do cliente os endereços que só existiam nos pedidos.'

    def add_arguments(self, parser):
        parser.add_argument('--loja', help='slug da loja; padrão é todas')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='conta quantos endereços nasceriam, sem gravar nada',
        )

    def handle(self, *args, **opts):
        from apps.stores.models import StoreOrder
        from apps.users.models import UserAddress

        pedidos = (
            StoreOrder.objects
            .exclude(delivery_address={})
            .exclude(customer_phone='')
            .select_related('store')
            .order_by('created_at')  # o mais antigo primeiro: o mais novo completa
        )
        if opts.get('loja'):
            pedidos = pedidos.filter(store__slug=opts['loja'])

        antes = UserAddress.objects.count()
        total = pedidos.count()
        self.stdout.write(f'{total} pedidos com endereço para processar')

        with transaction.atomic():
            salvos = sum(1 for p in pedidos.iterator() if guardar_endereco_do_pedido(p))
            depois = UserAddress.objects.count()
            novos = depois - antes

            if opts.get('dry_run'):
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING(
                    f'[dry-run] nasceriam {novos} endereços novos '
                    f'({salvos} pedidos aproveitados de {total}) — nada gravado',
                ))
                return

        self.stdout.write(self.style.SUCCESS(
            f'{novos} endereços novos ({salvos} pedidos aproveitados de {total}). '
            f'Caderno foi de {antes} para {depois}.',
        ))
