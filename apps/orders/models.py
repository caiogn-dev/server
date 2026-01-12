"""
Orders models - Order management.
"""
from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel

User = get_user_model()


class Order(BaseModel):
    """Order model."""
    
    class OrderStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        PROCESSING = 'processing', 'Processing'
        AWAITING_PAYMENT = 'awaiting_payment', 'Awaiting Payment'
        PAID = 'paid', 'Paid'
        SHIPPED = 'shipped', 'Shipped'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'
        REFUNDED = 'refunded', 'Refunded'

    account = models.ForeignKey(
        'whatsapp.WhatsAppAccount',
        on_delete=models.CASCADE,
        related_name='orders'
    )
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )
    
    order_number = models.CharField(max_length=50, unique=True, db_index=True)
    
    customer_phone = models.CharField(max_length=20, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True)
    customer_email = models.EmailField(blank=True)
    
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING
    )
    
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    currency = models.CharField(max_length=3, default='BRL')
    
    shipping_address = models.JSONField(default=dict, blank=True)
    billing_address = models.JSONField(default=dict, blank=True)
    
    notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)
    
    confirmed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'orders'
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', 'status', '-created_at']),
            models.Index(fields=['customer_phone', '-created_at']),
        ]

    def __str__(self):
        return f"Order {self.order_number} - {self.status}"

    def calculate_total(self):
        """Calculate order total."""
        self.total = self.subtotal - self.discount + self.shipping_cost + self.tax
        return self.total


class OrderItem(BaseModel):
    """Order item model."""
    
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    
    product_id = models.CharField(max_length=100, blank=True)
    product_name = models.CharField(max_length=255)
    product_sku = models.CharField(max_length=100, blank=True)
    
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'order_items'
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)


class OrderEvent(BaseModel):
    """Order event log."""
    
    class EventType(models.TextChoices):
        CREATED = 'created', 'Created'
        STATUS_CHANGED = 'status_changed', 'Status Changed'
        PAYMENT_RECEIVED = 'payment_received', 'Payment Received'
        SHIPPED = 'shipped', 'Shipped'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'
        NOTE_ADDED = 'note_added', 'Note Added'
        CUSTOMER_NOTIFIED = 'customer_notified', 'Customer Notified'

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='events'
    )
    
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    description = models.TextField(blank=True)
    
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_events'
    )
    
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'order_events'
        verbose_name = 'Order Event'
        verbose_name_plural = 'Order Events'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order.order_number} - {self.event_type}"
