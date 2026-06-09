"""
Store cart models - StoreCart, StoreCartItem, StoreCartComboItem.
"""
import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import django.db.models.deletion

User = get_user_model()


class StoreCart(models.Model):
    """Shopping cart for a store."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='carts'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='store_carts',
        null=True,
        blank=True
    )
    session_key = models.CharField(max_length=255, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'store_carts'
        verbose_name = 'Store Cart'
        verbose_name_plural = 'Store Carts'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['store', 'user']),
            models.Index(fields=['store', 'session_key']),
            # Includes is_active for the common "get active cart" query
            models.Index(fields=['user', 'store', 'is_active'], name='cart_user_store_active_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'store'],
                condition=models.Q(is_active=True, user__isnull=False),
                name='unique_active_cart_per_user_store',
            ),
        ]

    def __str__(self):
        if self.user:
            return f"Cart for {self.user.email} at {self.store.name}"
        return f"Anonymous cart at {self.store.name}"

    @property
    def subtotal(self):
        from decimal import Decimal
        from django.db.models import Sum, F, Case, When, DecimalField

        product_total = self.items.aggregate(
            total=Sum(
                Case(
                    When(
                        variant__isnull=False,
                        variant__price__isnull=False,
                        variant__price__gt=0,
                        then=F('variant__price') * F('quantity'),
                    ),
                    default=F('product__price') * F('quantity'),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        )['total'] or Decimal('0.00')

        combo_total = self.combo_items.aggregate(
            total=Sum(
                Case(
                    When(unit_price__isnull=False, then=F('unit_price') * F('quantity')),
                    When(
                        combo__isnull=False,
                        combo__price__isnull=False,
                        then=F('combo__price') * F('quantity'),
                    ),
                    default=Decimal('0.00'),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        )['total'] or Decimal('0.00')

        return product_total + combo_total

    @property
    def item_count(self):
        from django.db.models import Sum
        product_count = self.items.aggregate(total=Sum('quantity'))['total'] or 0
        combo_count = self.combo_items.aggregate(total=Sum('quantity'))['total'] or 0
        return product_count + combo_count

    @property
    def is_empty(self):
        return not self.items.exists() and not self.combo_items.exists()

    def clear(self):
        self.items.all().delete()
        self.combo_items.all().delete()

    def merge_with(self, other_cart):
        for item in other_cart.items.all():
            existing = self.items.filter(product=item.product, variant=item.variant).first()
            if existing:
                existing.quantity += item.quantity
                existing.save()
            else:
                item.cart = self
                item.save()
        other_cart.delete()

    @classmethod
    def get_or_create_for_user(cls, store, user):
        cart, created = cls.objects.get_or_create(
            store=store, user=user, is_active=True, defaults={'metadata': {}}
        )
        return cart

    @classmethod
    def get_or_create_for_session(cls, store, session_key):
        cart, created = cls.objects.get_or_create(
            store=store, session_key=session_key, user__isnull=True, is_active=True,
            defaults={'metadata': {}}
        )
        return cart


class StoreCartItem(models.Model):
    """Individual item in a shopping cart."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(StoreCart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        'stores.StoreProduct',
        on_delete=models.CASCADE,
        related_name='cart_items'
    )
    variant = models.ForeignKey(
        'stores.StoreProductVariant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cart_items'
    )
    quantity = models.PositiveIntegerField(default=1)
    options = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_cart_items'
        verbose_name = 'Cart Item'
        verbose_name_plural = 'Cart Items'
        unique_together = ['cart', 'product', 'variant']

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"

    @property
    def unit_price(self):
        if self.variant and self.variant.price:
            return self.variant.price
        return self.product.price

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        StoreCart.objects.filter(id=self.cart_id).update(updated_at=timezone.now())


class StoreCartComboItem(models.Model):
    """Combo/bundle line in a shopping cart.

    Products and variants are handled by StoreCartItem. This model is only for
    true bundles/promotions, and for legacy virtual items such as the salad
    builder. We keep name/price snapshots so cart totals are stable if the
    catalog changes after the customer adds the item.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(StoreCart, on_delete=models.CASCADE, related_name='combo_items')
    combo = models.ForeignKey(
        'stores.StoreCombo',
        on_delete=django.db.models.deletion.SET_NULL,
        null=True,
        blank=True,
        related_name='cart_items',
    )

    combo_name = models.CharField(max_length=255, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Group selections: { "group_id": ["variant_id1", "variant_id2"] }
    group_selections = models.JSONField(default=dict, blank=True)
    customizations = models.JSONField(default=dict, blank=True)

    quantity = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_cart_combo_items'
        verbose_name = 'Cart Combo Item'
        verbose_name_plural = 'Cart Combo Items'

    def __str__(self):
        return f"{self.quantity}x {self.effective_name}"

    @property
    def effective_name(self):
        if self.combo_name:
            return self.combo_name
        if self.combo:
            return self.combo.name
        return 'Combo'

    @property
    def effective_price(self):
        if self.unit_price is not None:
            return self.unit_price
        if self.combo:
            return self.combo.price
        return Decimal('0.00')

    @property
    def subtotal(self):
        return Decimal(str(self.effective_price)) * self.quantity

    def save(self, *args, **kwargs):
        if self.combo and not self.combo_name:
            self.combo_name = self.combo.name
        if self.combo and self.unit_price is None:
            self.unit_price = self.combo.price
        super().save(*args, **kwargs)
        StoreCart.objects.filter(id=self.cart_id).update(updated_at=timezone.now())
