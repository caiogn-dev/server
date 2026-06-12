"""Fidelidade persistida.

Substitui o cálculo on-the-fly do CheckoutService (que varria todos os pedidos
do cliente a cada request e guardava resgates em metadata JSON) por saldo
materializado + trilha de transações auditável.
"""
import uuid

from django.conf import settings
from django.db import models


class StoreLoyaltyAccount(models.Model):
    """Saldo de fidelidade por cliente por loja (materializado)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='loyalty_accounts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='loyalty_accounts')
    qualified_count = models.PositiveIntegerField(default=0)
    redeemed_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_loyalty_accounts'
        unique_together = ['store', 'user']
        indexes = [models.Index(fields=['store', 'user'])]

    def __str__(self):
        return f"{self.store.slug}/{self.user_id}: {self.qualified_count} qual., {self.redeemed_count} resg."


class StoreLoyaltyTransaction(models.Model):
    """Trilha de auditoria: cada crédito/resgate vira uma linha imutável."""

    class Kind(models.TextChoices):
        EARN = 'earn', 'Crédito'
        REDEEM = 'redeem', 'Resgate'
        ADJUST = 'adjust', 'Ajuste manual'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(StoreLoyaltyAccount, on_delete=models.CASCADE, related_name='transactions')
    order = models.ForeignKey('stores.StoreOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='loyalty_transactions')
    kind = models.CharField(max_length=10, choices=Kind.choices)
    quantity = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_loyalty_transactions'
        ordering = ['-created_at']
        constraints = [
            # Idempotência: 1 crédito por pedido (resgates idem)
            models.UniqueConstraint(
                fields=['order', 'kind'],
                name='loyalty_unique_order_kind',
                condition=models.Q(order__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{self.kind} {self.quantity} ({self.account_id})"
