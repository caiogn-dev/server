"""Liquida vendas entregues em dinheiro que nunca viraram receita.

O conserto em `OrderService.update_status` vale de agora em diante; este
comando resolve o passivo. Medido em 14/08: R$ 306,00 em dois pedidos
(CE-2607316642 e KER2608076764) entregues, dinheiro recebido em mãos e
`payment_status=pending`.

⚠️ `paid_at` recebe `delivered_at`, nunca `now()`: marcar hoje uma venda de
31/07 tiraria o furo do lugar em vez de fechá-lo.

⚠️ Só toca `payment_status=PENDING`. Estornado (`refunded`) não é "ainda não
liquidou" — é "liquidou e foi devolvido". Promover um estorno de volta a PAID
inventaria receita que já foi revertida.

    python manage.py liquidar_entregas_em_dinheiro --dry-run
    python manage.py liquidar_entregas_em_dinheiro --loja ce-saladas
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

#: Espelha `OFFLINE_PAYMENT_METHODS` em `apps/stores/models/order.py`. Pago em
#: mãos na entrega — o único caso em que entregar é a prova do pagamento.
METODOS_OFFLINE = {'cash'}


class Command(BaseCommand):
    help = 'Marca como pagas as entregas em dinheiro que nunca liquidaram.'

    def add_arguments(self, parser):
        parser.add_argument('--loja', help='slug da loja; padrão é todas')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='lista o que seria liquidado, sem gravar',
        )

    def handle(self, *args, **opts):
        from apps.stores.models import StoreOrder

        pendentes = (
            StoreOrder.objects
            .filter(
                status__in=[
                    StoreOrder.OrderStatus.DELIVERED,
                    StoreOrder.OrderStatus.COMPLETED,
                ],
                payment_method__in=METODOS_OFFLINE,
                delivered_at__isnull=False,
            )
            # PENDING, não `.exclude(payment_status=PAID)`: PaymentStatus tem
            # também FAILED/REFUNDED/PARTIALLY_REFUNDED/CANCELLED. Um pedido em
            # dinheiro entregue e depois estornado passaria no exclude e seria
            # promovido a PAID de volta — inventando receita já revertida.
            .filter(payment_status=StoreOrder.PaymentStatus.PENDING)
            .select_related('store')
            .order_by('delivered_at')
        )
        if opts.get('loja'):
            pendentes = pendentes.filter(store__slug=opts['loja'])

        total = 0
        # Conta na mão, junto com o total: não dependa de `pendentes.count()`
        # depois do laço. Hoje ele só bate porque `for pedido in pendentes`
        # preenche o `_result_cache` do queryset e `count()` reaproveita esse
        # cache. Se o laço virar `.iterator()` (otimização óbvia num comando
        # de lote), `count()` dispara query nova dentro da MESMA transação,
        # enxerga as próprias escritas (`payment_status` já não é mais
        # PENDING) e devolve 0 — relatando "0 pedidos" enquanto grava tudo
        # certo, justo no output que decide se roda sem --dry-run.
        contagem = 0
        with transaction.atomic():
            for pedido in pendentes:
                self.stdout.write(
                    f'  {pedido.store.slug:12} {pedido.order_number:16} '
                    f'entregue {timezone.localtime(pedido.delivered_at):%d/%m %H:%M}'
                    f'  R$ {pedido.total}'
                )
                total += pedido.total
                contagem += 1
                StoreOrder.objects.filter(id=pedido.id).update(
                    payment_status=StoreOrder.PaymentStatus.PAID,
                    paid_at=pedido.delivered_at,
                )

            if opts.get('dry_run'):
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING(
                    f'[dry-run] {contagem} pedidos, R$ {total} — nada gravado'
                ))
                return

        self.stdout.write(self.style.SUCCESS(
            f'{contagem} pedidos liquidados, R$ {total} de volta ao faturamento.'
        ))
