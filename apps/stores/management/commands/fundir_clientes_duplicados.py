"""Funde cadastros que são a mesma pessoa, antes da trava do banco subir.

A trava `cliente_unico_por_telefone_na_loja` não é criada enquanto existir
duplicata — e existir duplicata é justamente o motivo dela existir. Este
comando limpa o passado; a trava impede o futuro.

QUEM SOBREVIVE: o cadastro com mais pedidos; empate decide pelo mais antigo,
que é o que os relatórios já contam como "cliente desde".

O QUE É SOMADO: total de pedidos e total gasto, porque são contadores da mesma
pessoa que ficaram partidos. Endereços do perdedor migram. `last_order_at` fica
o mais recente dos dois.

SEM `--aplicar` NÃO ESCREVE NADA. Fusão de cadastro apaga uma linha de cliente
com histórico de compra; ver a lista antes é o mínimo.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.utils import normalize_phone_number
from apps.stores.models.customer import StoreCustomer


class Command(BaseCommand):
    help = 'Funde StoreCustomer duplicados por telefone (mesma loja).'

    def add_arguments(self, parser):
        parser.add_argument('--loja', default='', help='slug da loja (vazio = todas)')
        parser.add_argument('--aplicar', action='store_true')

    def handle(self, *args, **opts):
        qs = StoreCustomer.objects.exclude(phone='').select_related('store')
        if opts['loja']:
            qs = qs.filter(store__slug=opts['loja'])

        grupos = defaultdict(list)
        for c in qs:
            grupos[(c.store_id, normalize_phone_number(c.phone) or c.phone)].append(c)
        duplicados = {k: v for k, v in grupos.items() if len(v) > 1}

        self.stdout.write(f'grupos duplicados: {len(duplicados)}')
        planos = []
        for (_, telefone), linhas in duplicados.items():
            # Mais pedidos vence; empate, o mais antigo (é o "cliente desde").
            linhas.sort(key=lambda c: (-(c.total_orders or 0), c.created_at))
            fica, saem = linhas[0], linhas[1:]
            planos.append((telefone, fica, saem))
            self.stdout.write(
                f'  {telefone}: fica #{str(fica.id)[:8]} ({fica.total_orders} ped) '
                f'| some {[f"#{str(c.id)[:8]} ({c.total_orders} ped)" for c in saem]}'
            )

        if not opts['aplicar']:
            self.stdout.write(self.style.WARNING('\nNada gravado. Use --aplicar para valer.'))
            return

        from apps.stores.models.customer import StoreCustomerAddress
        fundidos = 0
        with transaction.atomic():
            for telefone, fica, saem in planos:
                for perdedor in saem:
                    fica.total_orders = (fica.total_orders or 0) + (perdedor.total_orders or 0)
                    fica.total_spent = (fica.total_spent or 0) + (perdedor.total_spent or 0)
                    if perdedor.last_order_at and (
                        not fica.last_order_at or perdedor.last_order_at > fica.last_order_at
                    ):
                        fica.last_order_at = perdedor.last_order_at
                    StoreCustomerAddress.objects.filter(customer=perdedor).update(customer=fica)
                    perdedor.delete()
                    fundidos += 1
                fica.phone = telefone
                fica.save()

        self.stdout.write(self.style.SUCCESS(f'\n{fundidos} cadastros fundidos.'))
