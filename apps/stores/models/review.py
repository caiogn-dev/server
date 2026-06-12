"""Avaliação de pedido — 1 review por pedido, criada pelo cliente via access_token."""
import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class StoreReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='reviews')
    order = models.OneToOneField('stores.StoreOrder', on_delete=models.CASCADE, related_name='review')
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
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
