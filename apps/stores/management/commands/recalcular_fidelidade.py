"""Recalcula em lote os selos de fidelidade de pedidos já creditados.

Serve pro caso "ajustei o loyalty_units depois de já ter vendido": o crédito
de cada pedido é uma fotografia tirada na entrega e não retroage sozinho.

    # ver o que mudaria (não grava nada)
    python manage.py recalcular_fidelidade --loja ce-saladas --dry-run

    # só os pedidos que contêm um produto/combo específico
    python manage.py recalcular_fidelidade --produto <uuid>
    python manage.py recalcular_fidelidade --combo <uuid>
"""
from django.core.management.base import BaseCommand, CommandError

from apps.stores.models import Store, StoreOrder
from apps.stores.services.loyalty_service import LoyaltyService


class Command(BaseCommand):
    help = 'Recalcula os selos de fidelidade de pedidos pelas regras atuais da loja.'

    def add_arguments(self, parser):
        parser.add_argument('--loja', help='slug da loja')
        parser.add_argument('--produto', help='id do StoreProduct — só pedidos que o contêm')
        parser.add_argument('--combo', help='id do StoreCombo — só pedidos que o contêm')
        parser.add_argument('--pedido', help='order_number de um pedido específico')
        parser.add_argument('--dry-run', action='store_true', help='só mostra, não grava')

    def handle(self, *args, **options):
        qs = StoreOrder.objects.filter(customer__isnull=False).select_related('store', 'customer')

        if options['loja']:
            try:
                store = Store.objects.get(slug=options['loja'])
            except Store.DoesNotExist:
                raise CommandError(f"Loja '{options['loja']}' não existe.")
            qs = qs.filter(store=store)
        if options['produto']:
            qs = qs.filter(items__product_id=options['produto'])
        if options['combo']:
            qs = qs.filter(combo_items__combo_id=options['combo'])
        if options['pedido']:
            qs = qs.filter(order_number=options['pedido'])

        if not any(options[k] for k in ('loja', 'produto', 'combo', 'pedido')):
            raise CommandError(
                'Informe pelo menos um filtro (--loja, --produto, --combo ou --pedido). '
                'Rodar sobre a base inteira mexeria no saldo de todos os clientes.'
            )

        qs = qs.distinct().order_by('created_at')
        total = qs.count()
        self.stdout.write(f'{total} pedido(s) no recorte.')

        mudados = 0
        saldo_delta = 0
        for order in qs.iterator():
            # Mesma função nos dois modos: prévia que diverge da execução é
            # pior que não ter prévia.
            resultado = LoyaltyService.recalculate_order_credit(
                order, apply=not options['dry_run'],
            )

            if not resultado['changed']:
                continue
            mudados += 1
            saldo_delta += resultado['delta']
            cliente = order.customer.get_full_name() or order.customer.username
            self.stdout.write(
                f"  {order.order_number}  {cliente}: "
                f"{resultado['before']} → {resultado['after']} "
                f"({resultado['delta']:+d})"
            )

        prefixo = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefixo}{mudados} pedido(s) alterado(s), {saldo_delta:+d} selos no total.'
        ))
