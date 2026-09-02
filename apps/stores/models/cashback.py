"""Cashback por telefone.

Por que TELEFONE e não usuário: o checkout do storefront é guest-first — a
maioria dos pedidos chega sem login. A fidelidade existente (StoreLoyaltyAccount)
é chaveada por `user` e por isso não credita pedido de convidado, que é
justamente o caso comum. Repetir esse erro aqui esvaziaria o programa inteiro.

O saldo é materializado em LOTES (StoreCashbackLot) e não num campo único,
porque cada crédito vence em data própria. Com um saldo só não dá para saber
qual parte expira quando, e o vencimento vira ou perda indevida de saldo novo
ou saldo eterno — os dois errados.
"""
import uuid

from django.db import models


class StoreCashbackLot(models.Model):
    """Um crédito de cashback com data de validade própria.

    Resgate consome lotes por ordem de vencimento (o que vence antes sai
    primeiro), então o cliente nunca perde saldo que poderia ter usado.
    """

    class Origin(models.TextChoices):
        PURCHASE = 'purchase', 'Compra própria'
        REFERRAL = 'referral', 'Indicação'
        ADJUST = 'adjust', 'Ajuste manual'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='cashback_lots')
    # E.164 sem '+', normalizado por apps.core.utils.normalize_phone_number
    phone = models.CharField(max_length=20, db_index=True)
    origin = models.CharField(max_length=12, choices=Origin.choices, default=Origin.PURCHASE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    remaining = models.DecimalField(max_digits=10, decimal_places=2)
    # Pedido que GEROU o crédito. Na indicação é o pedido do amigo, não o de quem indica.
    order = models.ForeignKey(
        'stores.StoreOrder', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cashback_lots',
    )
    coupon_code = models.CharField(max_length=50, blank=True, default='')
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_cashback_lots'
        ordering = ['expires_at', 'created_at']
        indexes = [
            models.Index(fields=['store', 'phone', 'expires_at']),
        ]
        constraints = [
            # Idempotência: um pedido credita no máximo uma vez por origem.
            # Sem isto, webhook do MP reenviado dobra o saldo do cliente.
            models.UniqueConstraint(
                fields=['order', 'origin'],
                name='cashback_unico_por_pedido_e_origem',
                condition=models.Q(order__isnull=False),
            ),
        ]

    def __str__(self):
        return f'{self.store_id}/{self.phone}: {self.remaining} de {self.amount}'


class StoreCashbackRedemption(models.Model):
    """Resgate: quanto de saldo foi abatido de um pedido."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='cashback_redemptions')
    phone = models.CharField(max_length=20, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    order = models.ForeignKey(
        'stores.StoreOrder', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cashback_redemptions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_cashback_redemptions'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['order'],
                name='cashback_resgate_unico_por_pedido',
                condition=models.Q(order__isnull=False),
            ),
        ]

    def __str__(self):
        return f'{self.store_id}/{self.phone}: -{self.amount}'
