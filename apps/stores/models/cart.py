"""
Store cart models - StoreCart, StoreCartItem, StoreCartComboItem.
"""
import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

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

    def __str__(self):
        if self.user:
            return f"Cart for {self.user.email} at {self.store.name}"
        return f"Anonymous cart at {self.store.name}"

    @property
    def subtotal(self):
        product_total = sum(item.subtotal for item in self.items.all())
        combo_total = sum(item.subtotal for item in self.combo_items.all())
        return product_total + combo_total

    @property
    def item_count(self):
        product_count = sum(item.quantity for item in self.items.all())
        combo_count = sum(item.quantity for item in self.combo_items.all())
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
    """Combo item in a shopping cart.

    Supports both real combos (combo FK set) and virtual combos like
    the salad builder (combo=None, combo_name and unit_price set manually).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(StoreCart, on_delete=models.CASCADE, related_name='combo_items')
    combo = models.ForeignKey(
        'stores.StoreCombo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cart_items'
    )
    # Denormalized name — required for virtual combos (combo=None), optional for real combos
    combo_name = models.CharField(max_length=255, blank=True)
    # Denormalized price — required for virtual combos, optional for real combos (uses combo.price)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    quantity = models.PositiveIntegerField(default=1)
    customizations = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_cart_combo_items'
        verbose_name = 'Cart Combo Item'
        verbose_name_plural = 'Cart Combo Items'

    def __str__(self):
        name = self.combo_name or (self.combo.name if self.combo else 'Combo')
        return f"{self.quantity}x {name}"

    @property
    def effective_name(self):
        return self.combo_name or (self.combo.name if self.combo else 'Combo')

    @property
    def effective_price(self):
        if self.unit_price is not None:
            return self.unit_price
        return self.combo.price if self.combo else 0

    @property
    def subtotal(self):
        from decimal import Decimal
        return Decimal(str(self.effective_price)) * self.quantity
