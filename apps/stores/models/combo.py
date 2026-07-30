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
    # Preço dinâmico: total = price (base) + soma dos itens selecionados
    # (price_override do item, ou preço normal do produto/variante se sem override).
    # Quando False, o total é o price fixo. Ver compute_unit_price().
    dynamic_pricing = models.BooleanField(default=False)
    # Config livre por combo (ex.: loyalty_units — quantos selos de fidelidade
    # o combo vale por unidade; mesma convenção do StoreProduct.attributes).
    metadata = models.JSONField(default=dict, blank=True)
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

    def compute_unit_price(self, selections):
        """Preço unitário do combo dado as seleções do cliente.

        selections = {group_id: [id, ...]} onde id é variant_id OU product_id.
        - dynamic_pricing False → preço fixo (self.price).
        - dynamic_pricing True  → self.price (base) + Σ por item selecionado de
          (price_override do item, ou preço normal do produto/variante).
        """
        base = self.price or Decimal('0.00')
        if not self.dynamic_pricing:
            return base

        total = Decimal(str(base))
        groups = {str(g.id): g for g in self.groups.all().prefetch_related(
            'variant_limits__variant', 'product_options__product'
        )}
        for group_id, selected_ids in (selections or {}).items():
            group = groups.get(str(group_id))
            if not group:
                continue
            variant_price = {}
            for limit in group.variant_limits.all():
                v = limit.variant
                variant_price[str(v.id)] = (
                    limit.price_override if limit.price_override is not None
                    else (v.price if v.price is not None else (group.product.price if group.product_id else Decimal('0.00')))
                )
            option_price = {}
            for opt in group.product_options.all():
                option_price[str(opt.product_id)] = (
                    opt.price_override if opt.price_override is not None else opt.product.price
                )
            for sel_id in (selected_ids or []):
                key = str(sel_id)
                if key in option_price:
                    total += Decimal(str(option_price[key]))
                elif key in variant_price:
                    total += Decimal(str(variant_price[key]))
        return total

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


