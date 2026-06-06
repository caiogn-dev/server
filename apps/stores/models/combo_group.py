"""
Combo product group models - ComboProductGroup, ComboProductGroupVariantLimit.
"""
import uuid
from decimal import Decimal
from django.db import models
from django.core.exceptions import ValidationError


class ComboProductGroup(models.Model):
    """Product group within a combo with selection rules."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    combo = models.ForeignKey(
        'stores.StoreCombo',
        on_delete=models.CASCADE,
        related_name='groups'
    )
    # Product must belong to same store as combo (enforced in save())
    product = models.ForeignKey(
        'stores.StoreProduct',
        on_delete=models.CASCADE
    )

    # Selection rules
    is_required = models.BooleanField(default=True)
    min_selections = models.PositiveIntegerField(default=1)
    max_selections = models.PositiveIntegerField(default=1)
    allow_duplicate_variants = models.BooleanField(default=False)

    # Metadata
    position = models.PositiveIntegerField(default=0)  # For ordering
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'combo_product_groups'
        verbose_name = 'Combo Product Group'
        verbose_name_plural = 'Combo Product Groups'
        unique_together = ['combo', 'product']
        ordering = ['position']

    def __str__(self):
        return f"{self.combo.name} - {self.product.name}"

    def save(self, *args, **kwargs):
        """Ensure product belongs to same store as combo."""
        if self.product.store_id != self.combo.store_id:
            raise ValidationError(
                "Product must belong to the same store as the combo"
            )
        super().save(*args, **kwargs)


class ComboProductGroupVariantLimit(models.Model):
    """Defines stock/selection limits per variant within a group."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(
        ComboProductGroup,
        on_delete=models.CASCADE,
        related_name='variant_limits'
    )
    variant = models.ForeignKey(
        'stores.StoreProductVariant',
        on_delete=models.CASCADE
    )

    # Limit for this variant in this combo group
    max_selections = models.PositiveIntegerField(default=1)

    # Optional: price override (if variant costs different in combo)
    price_override = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'combo_product_group_variant_limits'
        verbose_name = 'Combo Variant Limit'
        verbose_name_plural = 'Combo Variant Limits'
        unique_together = ['group', 'variant']

    def __str__(self):
        return f"{self.group.product.name} - {self.variant.name}: max {self.max_selections}"
