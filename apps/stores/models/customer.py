"""
Store customer model.
"""
import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel
from .base import Store

User = get_user_model()


class StoreCustomer(BaseModel):
    """
    Customer profile specific to a store.
    Links to User but stores store-specific data.
    """

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='customers'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='store_profiles'
    )

    # Contact info
    phone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)

    # Social links
    instagram = models.CharField(max_length=100, blank=True)
    twitter = models.CharField(max_length=100, blank=True)
    facebook = models.CharField(max_length=100, blank=True)

    # Addresses
    addresses = models.JSONField(default=list, blank=True)
    default_address_index = models.PositiveIntegerField(default=0)

    # Stats
    total_orders = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    last_order_at = models.DateTimeField(null=True, blank=True)

    # Tags and notes
    tags = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)

    # Marketing
    accepts_marketing = models.BooleanField(default=False)
    marketing_opt_in_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'store_customers'
        verbose_name = 'Store Customer'
        verbose_name_plural = 'Store Customers'
        unique_together = ['store', 'user']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.store.name} - {self.user.email}"

    def get_default_address(self):
        if self.addresses and len(self.addresses) > self.default_address_index:
            return self.addresses[self.default_address_index]
        return None

    def update_stats(self):
        """Update customer statistics from orders."""
        from django.db.models import Sum, Count
        from .order import StoreOrder

        stats = StoreOrder.objects.filter(
            store=self.store,
            customer=self.user,
            status__in=['paid', 'completed', 'delivered']
        ).aggregate(
            total_orders=Count('id'),
            total_spent=Sum('total')
        )

        self.total_orders = stats['total_orders'] or 0
        self.total_spent = stats['total_spent'] or Decimal('0.00')

        last_order = StoreOrder.objects.filter(
            store=self.store,
            customer=self.user
        ).order_by('-created_at').first()

        if last_order:
            self.last_order_at = last_order.created_at

        self.save(update_fields=['total_orders', 'total_spent', 'last_order_at', 'updated_at'])
