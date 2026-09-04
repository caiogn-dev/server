"""Põe os pedidos antigos no mesmo formato de telefone dos novos.

O `save()` do pedido passou a normalizar, mas só vale daqui pra frente. Os 121
pedidos da Cê que já estavam gravados sem o DDI continuariam partindo sete
clientes em duas pessoas cada na lista, no RFM e em toda contagem por cliente.

SEM `--aplicar` NÃO ESCREVE NADA. Este comando reescreve identidade de cliente
em pedido pago; ver a lista antes é o mínimo, e o padrão é olhar.

`update_fields` de propósito: um `save()` cheio aqui dispararia os signals de
pedido — notificação de status, webhook, crédito de fidelidade — em 121 pedidos
antigos de uma vez. O cliente receberia no WhatsApp o aviso de um pedido que
recebeu semanas atrás.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.stores.models import Store, StoreOrder
from apps.stores.models.order import _telefone_do_pedido


class Command(BaseCommand):
    help = 'Normaliza customer_phone dos pedidos já gravados.'

    def add_arguments(self, parser):
        parser.add_argument('--loja', default='', help='slug da loja (vazio = todas)')
        parser.add_argument('--aplicar', action='store_true', help='grava (padrão é só mostrar)')

    def handle(self, *args, **opts):
        qs = StoreOrder.objects.exclude(customer_phone='')
        if opts['loja']:
            qs = qs.filter(store__slug=opts['loja'])

        mudam = []
        for pedido in qs.only('id', 'order_number', 'customer_name', 'customer_phone'):
            novo = _telefone_do_pedido(pedido.customer_phone)
            if novo and novo != pedido.customer_phone:
                mudam.append((pedido, novo))

        self.stdout.write(f'pedidos que mudam: {len(mudam)} de {qs.count()}')
        for pedido, novo in mudam[:15]:
            nome = (pedido.customer_name or '?')[:24]
            self.stdout.write(f'   {pedido.order_number}  {nome:26} {pedido.customer_phone:16} -> {novo}')
        if len(mudam) > 15:
            self.stdout.write(f'   ... e mais {len(mudam) - 15}')

        # Quantas pessoas param de aparecer em duplicidade.
        antes = set(qs.values_list('customer_phone', flat=True))
        depois = {_telefone_do_pedido(t) or t for t in antes}
        self.stdout.write(
            f'telefones distintos: {len(antes)} -> {len(depois)} '
            f'({len(antes) - len(depois)} duplicatas somem)'
        )

        if not opts['aplicar']:
            self.stdout.write(self.style.WARNING('\nNada gravado. Use --aplicar para valer.'))
            return

        for pedido, novo in mudam:
            pedido.customer_phone = novo
            # update_fields: sem isto os signals de pedido disparariam e o
            # cliente receberia hoje o aviso de um pedido de semanas atrás.
            pedido.save(update_fields=['customer_phone'])

        self.stdout.write(self.style.SUCCESS(f'\n{len(mudam)} pedidos atualizados.'))
