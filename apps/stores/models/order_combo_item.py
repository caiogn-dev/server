"""
Order combo item model - tracks customer's variant selections for a combo in an order.
"""
import uuid
from django.db import models


class StoreOrderComboItem(models.Model):
    """Tracks a combo item in an order, including customer's selected variants."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        'stores.StoreOrder',
        on_delete=models.CASCADE,
        related_name='combo_items'
    )
    order_item = models.ForeignKey(
        'stores.StoreOrderItem',
        on_delete=models.CASCADE,
        related_name='combo_selections',
        null=True
    )
    combo = models.ForeignKey(
        'stores.StoreCombo',
        on_delete=models.SET_NULL,
        null=True
    )
    # List of selected variant IDs: ["variant-id-1", "variant-id-2", "variant-id-3", "variant-id-4"]
    selected_variant_ids = models.JSONField(default=list)
    # Enriched data for display (populated at order creation):
    # [{"variant_id": "xxx", "variant_name": "Frango", "product_name": "Rondelli"}, ...]
    selected_variants_data = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_order_combo_items'
        verbose_name = 'Order Combo Item'
        verbose_name_plural = 'Order Combo Items'

    def __str__(self):
        return f"Combo in Order {self.order_item.order.id}: {self.combo.name if self.combo else 'Unknown'}"
