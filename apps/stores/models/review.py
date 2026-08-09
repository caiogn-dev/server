"""Avaliação de pedido — 1 review por pedido, criada pelo cliente via access_token."""
import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


# Configuração comum dos pilares. Fora da classe: dentro dela viraria atributo
# do modelo, e atributo que não é Field no meio dos campos confunde quem lê.
_PILAR = dict(
    null=True, blank=True,
    validators=[MinValueValidator(1), MaxValueValidator(5)],
)


class StoreReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='reviews')
    order = models.OneToOneField('stores.StoreOrder', on_delete=models.CASCADE, related_name='review')
    # Nota geral. Continua sendo a fonte de verdade da média da loja — quando
    # o cliente responde só os pilares, ela é derivada deles (ver
    # StoreReviewSerializer), senão a loja teria duas médias diferentes na
    # mesma tela.
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )

    # ── Pilares ───────────────────────────────────────────────────────────
    # "Nota 4,6" não diz o que consertar: a comida pode estar impecável e a
    # entrega atrasando, e a decisão é oposta em cada caso — contratar
    # entregador ou revisar a cozinha.
    #
    # Todos OPCIONAIS: a avaliação já funcionava com uma nota só, e exigir três
    # derruba a taxa de resposta, que numa loja com poucas avaliações é o
    # recurso mais escasso.
    rating_comida = models.PositiveSmallIntegerField('Qualidade da comida', **_PILAR)
    # Só existe para pedido entregue: quem retira no balcão não tem o que
    # avaliar aqui, e nota inventada estraga um pilar que orienta decisão.
    rating_entrega = models.PositiveSmallIntegerField('Tempo de entrega', **_PILAR)
    rating_atendimento = models.PositiveSmallIntegerField('Atendimento', **_PILAR)

    comment = models.TextField(blank=True)
    customer_name = models.CharField(max_length=255, blank=True)
    # Moderação: lojista pode ocultar avaliações abusivas sem apagar
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_reviews'
        verbose_name = 'Store Review'
        verbose_name_plural = 'Store Reviews'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store', '-created_at']),
            models.Index(fields=['store', 'rating']),
        ]

    def __str__(self):
        return f"{self.store.name} - pedido {self.order_id} - {self.rating}★"


class StoreProductReview(models.Model):
    """Nota por produto dentro de uma avaliação de pedido (1 nota por produto/review)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(StoreReview, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        'stores.StoreProduct', on_delete=models.CASCADE, related_name='review_items',
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_product_reviews'
        verbose_name = 'Store Product Review'
        verbose_name_plural = 'Store Product Reviews'
        constraints = [
            models.UniqueConstraint(fields=['review', 'product'], name='uniq_review_product'),
        ]
        indexes = [
            models.Index(fields=['product', 'rating']),
        ]

    def __str__(self):
        return f"{self.product_id} - {self.rating}★"
