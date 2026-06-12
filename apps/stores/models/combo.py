"""
Store combo model - StoreCombo.
Grupos de seleção ficam em combo_group.py (ComboProductGroup).
"""
import uuid
from decimal import Decimal
from django.db import models
from apps.core.utils import build_absolute_media_url


class StoreCombo(models.Model):
    """Combo/bundle of products for a store."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='combos'
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    image = models.ImageField(upload_to='stores/combos/', blank=True, null=True)
    image_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    track_stock = models.BooleanField(default=False)
    stock_quantity = models.IntegerField(default=0)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_combos'
        verbose_name = 'Store Combo'
        verbose_name_plural = 'Store Combos'
        unique_together = ['store', 'slug']
        ordering = ['store', 'sort_order', 'name']

    def __str__(self):
        return f"{self.store.name} - {self.name}"

    def get_image_url(self):
        if self.image:
            return build_absolute_media_url(self.image.url)
        return build_absolute_media_url(self.image_url or '')

    @property
    def savings(self):
        if self.compare_at_price:
            return self.compare_at_price - self.price
        return Decimal('0.00')

    @property
    def savings_percentage(self):
        if self.compare_at_price and self.compare_at_price > 0:
            return int(((self.compare_at_price - self.price) / self.compare_at_price) * 100)
        return 0


