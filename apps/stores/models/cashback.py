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
        PREPAID = 'prepaid', 'Carteira pré-paga'

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
    # Idempotência de crédito SEM pedido (compra de saldo da carteira). A trava
    # de cima é por `order`, e a compra de pacote não gera pedido nenhum — sem
    # este campo o webhook reenviado do Mercado Pago dá um pacote de graça.
    # Guarda a referência da cobrança que originou o crédito, ex.: 'mp:12345'.
    source_ref = models.CharField(max_length=100, blank=True, default='', db_index=True)
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
            # Uma cobrança credita uma vez, por loja. Vazio fica de fora: a
            # imensa maioria dos lotes vem de pedido e não tem referência.
            models.UniqueConstraint(
                fields=['store', 'source_ref'],
                name='cashback_unico_por_cobranca',
                condition=~models.Q(source_ref=''),
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


class StoreDeliveryCoupon(models.Model):
    """Entregas grátis compradas junto com um pacote da carteira.

    POR QUE CONTADO E NÃO ILIMITADO: o frete é repasse (a loja cobra R$ 10,72 e
    paga R$ 10,72 ao entregador), então cada entrega grátis sai inteira da
    margem. No pacote Família — R$ 395 por 12 saladas, R$ 155 de margem — doze
    viagens de salada única custariam R$ 128,64 e deixariam R$ 26.

    E ilimitado inverte o incentivo: se a entrega é sempre grátis, o cliente não
    tem motivo para juntar duas saladas na mesma viagem, que é justamente onde a
    loja ganha (2 saladas numa viagem rendem R$ 25,28 contra R$ 18,00 de uma
    salada com frete pago). Com um número fixo, o teto de custo é conhecido e
    consolidar continua valendo a pena para os dois lados.

    Chaveado por TELEFONE pelo mesmo motivo do saldo: o checkout é guest-first.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='delivery_coupons')
    # E.164 sem '+', normalizado por apps.core.utils.normalize_phone_number
    phone = models.CharField(max_length=20, db_index=True)
    remaining = models.PositiveIntegerField()
    granted = models.PositiveIntegerField()
    expires_at = models.DateTimeField()
    # Cobrança que originou o benefício — mesma referência do lote de saldo.
    source_ref = models.CharField(max_length=100, blank=True, default='', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_delivery_coupons'
        ordering = ['expires_at', 'created_at']
        indexes = [models.Index(fields=['store', 'phone', 'expires_at'])]
        constraints = [
            # Uma cobrança concede o benefício uma vez. Mesma razão do saldo:
            # o Mercado Pago reentrega webhook.
            models.UniqueConstraint(
                fields=['store', 'source_ref'],
                name='cupom_entrega_unico_por_cobranca',
                condition=~models.Q(source_ref=''),
            ),
        ]

    def __str__(self):
        return f'{self.store_id}/{self.phone}: {self.remaining} de {self.granted} entregas'


class StoreDeliveryCouponUse(models.Model):
    """Uma entrega grátis consumida por um pedido.

    Existe para tornar o consumo IDEMPOTENTE por pedido: sem isto, um retry do
    checkout ou um recálculo de totais gastaria duas entregas do cliente pelo
    mesmo pedido.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cupom = models.ForeignKey(StoreDeliveryCoupon, on_delete=models.CASCADE, related_name='uses')
    order = models.ForeignKey('stores.StoreOrder', on_delete=models.CASCADE, related_name='delivery_coupon_uses')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_delivery_coupon_uses'
        constraints = [
            models.UniqueConstraint(fields=['order'], name='cupom_entrega_uso_unico_por_pedido'),
        ]
