"""
Store customer model.
"""
import uuid
from decimal import Decimal
from django.db import models
from django.db.models import Q
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel
from .base import Store

User = get_user_model()


class StoreCustomerAddress(BaseModel):
    """
    Relational address for a store customer.
    Replaces the deprecated StoreCustomer.addresses JSONField.
    """
    customer = models.ForeignKey(
        'StoreCustomer',
        on_delete=models.CASCADE,
        related_name='address_list',
    )
    label = models.CharField(max_length=50, blank=True, help_text="Ex: Casa, Trabalho")
    street = models.CharField(max_length=255, blank=True)
    number = models.CharField(max_length=20, blank=True)
    complement = models.CharField(max_length=100, blank=True)
    neighborhood = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)
    reference = models.CharField(max_length=255, blank=True)
    formatted = models.CharField(max_length=500, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = 'store_customer_addresses'
        verbose_name = 'Customer Address'
        verbose_name_plural = 'Customer Addresses'
        ordering = ['-is_default', '-created_at']
        indexes = [
            models.Index(fields=['customer', 'is_default'], name='custaddr_customer_default_idx'),
            models.Index(fields=['zip_code'], name='custaddr_zip_idx'),
        ]

    def __str__(self):
        return self.formatted or f"{self.street}, {self.number} — {self.city}"

    def set_as_default(self):
        """Marks this address as default and clears all others for the same customer."""
        StoreCustomerAddress.objects.filter(
            customer=self.customer, is_default=True
        ).exclude(pk=self.pk).update(is_default=False)
        if not self.is_default:
            self.is_default = True
            self.save(update_fields=['is_default', 'updated_at'])


class StoreCustomer(BaseModel):
    """
    Customer profile specific to a store.

    Identity hierarchy (from source-of-truth to derived):
      unified_user (UnifiedUser) → single identity across all stores
      user (auth.User) → legacy link; kept for backward compat until full migration
    """

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='customers'
    )
    # Universal identity (preferred) — populated by CustomerIdentityService
    unified_user = models.ForeignKey(
        'users.UnifiedUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='store_customers',
        verbose_name='Identidade Universal',
    )
    # Legacy auth.User link (kept for backward compat)
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
        indexes = [
            # Phone lookup in checkout identity and signals
            models.Index(fields=['phone'], name='customer_phone_idx'),
        ]

    def __str__(self):
        return f"{self.store.name} - {self.user.email}"

    def get_default_address(self):
        if self.addresses and len(self.addresses) > self.default_address_index:
            return self.addresses[self.default_address_index]
        return None

    def update_stats(self):
        """Update customer statistics from orders."""
        from django.db.models import Sum, Count
        from apps.core.models import UserProfile
        from apps.core.services.customer_identity import CustomerIdentityService
        from .order import StoreOrder

        phones = set()
        for value in [self.phone, self.whatsapp]:
            phones.update(CustomerIdentityService.phone_candidates(value))

        profile_phone = (
            UserProfile.objects
            .filter(user=self.user)
            .values_list('phone', flat=True)
            .first()
        )
        phones.update(CustomerIdentityService.phone_candidates(profile_phone))

        order_filter = Q(customer=self.user)
        if phones:
            order_filter |= Q(customer_phone__in=phones)

        orders = StoreOrder.objects.filter(store=self.store).filter(order_filter)
        paid_orders = orders.filter(
            Q(payment_status=StoreOrder.PaymentStatus.PAID) |
            Q(status__in=[
                StoreOrder.OrderStatus.PAID,
                StoreOrder.OrderStatus.COMPLETED,
                StoreOrder.OrderStatus.DELIVERED,
            ])
        ).exclude(status__in=[
            StoreOrder.OrderStatus.CANCELLED,
            StoreOrder.OrderStatus.FAILED,
            StoreOrder.OrderStatus.REFUNDED,
        ])

        stats = paid_orders.aggregate(
            total_orders=Count('id'),
            total_spent=Sum('total')
        )

        self.total_orders = stats['total_orders'] or 0
        self.total_spent = stats['total_spent'] or Decimal('0.00')

        last_order = orders.order_by('-created_at').first()

        if last_order:
            self.last_order_at = last_order.created_at

        self.save(update_fields=['total_orders', 'total_spent', 'last_order_at', 'updated_at'])
