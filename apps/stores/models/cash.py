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
        """Fundo de troco + reforços - sangrias (vendas em dinheiro entram via relatório)."""
        total = Decimal(self.opening_amount)
        for mv in self.movements.all():
            if mv.kind == StoreCashMovement.Kind.REINFORCEMENT:
                total += Decimal(mv.amount)
            else:
                total -= Decimal(mv.amount)
        return total

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
