"""Caixa de PDV: sessão de caixa com fundo de troco, sangria/reforço e conferência."""
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


class StoreCashSession(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Aberto'
        CLOSED = 'closed', 'Fechado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='cash_sessions')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    opening_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='cash_sessions_opened',
    )
    opened_at = models.DateTimeField(auto_now_add=True)

    counted_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    expected_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    difference = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='cash_sessions_closed',
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'store_cash_sessions'
        ordering = ['-opened_at']
        constraints = [
            # No máximo 1 caixa aberto por loja
            models.UniqueConstraint(
                fields=['store'],
                condition=models.Q(status='open'),
                name='cash_unique_open_session_per_store',
            ),
        ]

    def expected_cash(self) -> Decimal:
        """Fundo de troco + vendas em dinheiro da sessão + reforços - sangrias.

        Vendas em dinheiro = pedidos payment_method='cash' pagos dentro da
        janela da sessão (paid_at, com fallback em created_at para pedidos
        antigos sem o timestamp). Antes elas eram ignoradas e a "quebra" no
        fechamento saía sempre errada em dia de movimento no balcão.
        """
        from django.db.models import Q, Sum
        from django.utils import timezone as dj_tz

        total = Decimal(self.opening_amount)
        for mv in self.movements.all():
            if mv.kind == StoreCashMovement.Kind.REINFORCEMENT:
                total += Decimal(mv.amount)
            else:
                total -= Decimal(mv.amount)

        from .order import StoreOrder
        window_end = self.closed_at or dj_tz.now()
        paid_window = (
            Q(paid_at__gte=self.opened_at, paid_at__lte=window_end)
            | (Q(paid_at__isnull=True) & Q(created_at__gte=self.opened_at, created_at__lte=window_end))
        )
        # Só venda que virou dinheiro na gaveta: cancelada não entra (senão a
        # "quebra" do fechamento acusa falta que não existe) e pedido de teste
        # do dono também não.
        from apps.stores.metrics import apenas_receita

        cash_sales = apenas_receita(
            StoreOrder.objects.filter(store=self.store, payment_method='cash')
        ).filter(paid_window).aggregate(total=Sum('total'))['total'] or Decimal('0')

        return total + Decimal(cash_sales)

    def __str__(self):
        return f"Caixa {self.store.slug} {self.opened_at:%d/%m %H:%M} ({self.status})"


class StoreCashMovement(models.Model):
    class Kind(models.TextChoices):
        WITHDRAWAL = 'sangria', 'Sangria'
        REINFORCEMENT = 'reforco', 'Reforço'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(StoreCashSession, on_delete=models.CASCADE, related_name='movements')
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_cash_movements'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.kind} R${self.amount} ({self.session_id})"
