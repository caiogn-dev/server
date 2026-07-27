"""
Store coupon model.
"""
import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone


class StoreCoupon(models.Model):
    """Discount coupons for a store."""

    class DiscountType(models.TextChoices):
        PERCENTAGE = 'percentage', 'Percentage'
        FIXED = 'fixed', 'Fixed Amount'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='coupons'
    )
    code = models.CharField(max_length=50, db_index=True)
    description = models.TextField(blank=True)
    discount_type = models.CharField(
        max_length=20,
        choices=DiscountType.choices,
        default=DiscountType.PERCENTAGE
    )
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_purchase = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    usage_limit_per_user = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    first_order_only = models.BooleanField(default=False)
    applicable_categories = models.JSONField(default=list, blank=True)
    applicable_products = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_coupons'
        verbose_name = 'Store Coupon'
        verbose_name_plural = 'Store Coupons'
        unique_together = ['store', 'code']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.store.name} - {self.code}"

    def _identity_filter(self, user=None, customer_phone=None):
        """Filtro de pedidos do mesmo cliente (logado OU guest por telefone)."""
        from django.db.models import Q
        q = Q()
        if user is not None and getattr(user, 'is_authenticated', False):
            q |= Q(customer=user)
        if customer_phone:
            q |= Q(customer_phone=customer_phone)
        return q

    def is_valid(self, subtotal=None, user=None, customer_phone=None):
        """Check if coupon is valid for use.

        `customer_phone` identifica o guest — o checkout do storefront é
        guest-first, então limites por cliente precisam funcionar sem login.
        """
        from django.db.models import Q
        now = timezone.now()

        if not self.is_active:
            return False, "Cupom inativo"
        if now < self.valid_from:
            return False, "Cupom ainda não está válido"
        if now > self.valid_until:
            return False, "Cupom expirado"
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False, "Limite de uso atingido"
        if subtotal and subtotal < self.min_purchase:
            return False, f"Valor mínimo de R$ {self.min_purchase:.2f}"

        identity = self._identity_filter(user=user, customer_phone=customer_phone)
        if identity:
            from .order import StoreOrder
            # Pedido "de verdade": pago, ou já andou no funil — pending
            # abandonado e cancelado não contam contra o cliente.
            real_orders = StoreOrder.objects.filter(identity, store=self.store).filter(
                Q(payment_status='paid') | ~Q(status__in=['pending', 'cancelled'])
            )
            if self.first_order_only and real_orders.exists():
                return False, "Cupom válido apenas para primeira compra"
            if self.usage_limit_per_user:
                uses = real_orders.filter(coupon_code__iexact=self.code).count()
                if uses >= self.usage_limit_per_user:
                    return False, "Você já usou este cupom o máximo de vezes"

        return True, None

    def _eligible_subtotal(self, subtotal, items=None):
        """Base do desconto respeitando applicable_products/applicable_categories.

        `items`: [{'product_id', 'category_id', 'total'}]. Sem escopo definido
        (ou sem items pra avaliar), a base é o subtotal inteiro.
        """
        product_ids = {str(p) for p in (self.applicable_products or [])}
        category_ids = {str(c) for c in (self.applicable_categories or [])}
        if not product_ids and not category_ids:
            return subtotal
        if items is None:
            return subtotal
        eligible = Decimal('0')
        for item in items:
            pid = str(item.get('product_id') or '')
            cid = str(item.get('category_id') or '')
            if (pid and pid in product_ids) or (cid and cid in category_ids):
                eligible += Decimal(str(item.get('total') or 0))
        return eligible

    def calculate_discount(self, subtotal, items=None):
        """Calculate discount amount for a given subtotal."""
        valid, _ = self.is_valid(subtotal)
        if not valid:
            return Decimal('0.00')

        base = self._eligible_subtotal(subtotal, items=items)
        if base <= 0:
            return Decimal('0.00')

        if self.discount_type == self.DiscountType.PERCENTAGE:
            discount = base * (self.discount_value / 100)
        else:
            discount = min(self.discount_value, base)

        if self.max_discount:
            discount = min(discount, self.max_discount)

        return min(discount, subtotal)

    def increment_usage(self) -> bool:
        """Atomically increment usage count."""
        from django.db.models import F

        if self.usage_limit:
            updated = StoreCoupon.objects.filter(
                id=self.id, used_count__lt=self.usage_limit
            ).update(used_count=F('used_count') + 1, updated_at=timezone.now())
            return updated > 0
        else:
            StoreCoupon.objects.filter(id=self.id).update(
                used_count=F('used_count') + 1, updated_at=timezone.now()
            )
            return True
