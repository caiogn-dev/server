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
    # Âncora opcional: grupos baseados em VARIANTES têm um produto-âncora.
    # Grupos baseados em PRODUTOS (escolha entre vários produtos) deixam null
    # e usam `title` + product_options.
    product = models.ForeignKey(
        'stores.StoreProduct',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    # Rótulo do grupo quando não há produto-âncora (ex: "Escolha suas 5 saladas").
    title = models.CharField(max_length=255, blank=True)

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
        # product agora é nullable; NULLs não colidem no Postgres, então grupos
        # de produtos (sem âncora) coexistem no mesmo combo.
        unique_together = ['combo', 'product']
        ordering = ['position']

    def __str__(self):
        label = self.product.name if self.product else (self.title or 'grupo')
        return f"{self.combo.name} - {label}"

    def save(self, *args, **kwargs):
        """Ensure product (quando há âncora) pertence à mesma loja do combo."""
        if self.product_id and self.product.store_id != self.combo.store_id:
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
        anchor = self.group.product.name if self.group.product_id else (self.group.title or 'grupo')
        return f"{anchor} - {self.variant.name}: max {self.max_selections}"


class ComboProductGroupProductOption(models.Model):
    """Opção de PRODUTO dentro de um grupo de combo.

    Permite "escolha N entre vários produtos" (ex: 5 saladas), complementando
    o ComboProductGroupVariantLimit (que é por variante). Um grupo pode usar
    variantes OU produtos como opções.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(
        ComboProductGroup,
        on_delete=models.CASCADE,
        related_name='product_options'
    )
    product = models.ForeignKey(
        'stores.StoreProduct',
        on_delete=models.CASCADE
    )

    # Limite desta opção no grupo (quantas vezes pode ser escolhida)
    max_selections = models.PositiveIntegerField(default=1)

    # Preço por opção (se diferente do preço do produto dentro do combo)
    price_override = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'combo_product_group_product_options'
        verbose_name = 'Combo Product Option'
        verbose_name_plural = 'Combo Product Options'
        unique_together = ['group', 'product']
        ordering = ['position']

    def __str__(self):
        return f"{self.group} - opção {self.product.name}"
