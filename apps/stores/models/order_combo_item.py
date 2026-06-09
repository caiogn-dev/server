"""
Order combo item model - tracks customer's variant selections for a combo in an order.
"""
import uuid
import django.db.models.deletion
from django.db import models


class StoreOrderComboItem(models.Model):
    """Combo selection snapshot attached to an order.

    The sellable order line lives in StoreOrderItem for consistent totals,
    printing, payment, and webhooks. This model keeps the structured combo
    selections used to reconstruct what the customer chose.
    """

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
        null=True,
        blank=True,
    )
    combo = models.ForeignKey(
        'stores.StoreCombo',
        on_delete=django.db.models.deletion.SET_NULL,
        null=True,
        blank=True,
    )

    # Group selections: { "group_id": ["variant_id1", "variant_id2"] }
    group_selections = models.JSONField(default=dict)
    selected_variant_ids = models.JSONField(default=list)
    selected_variants_data = models.JSONField(default=list, blank=True)

    # Enriched display data (snapshot at order time)
    display_data = models.JSONField(default=dict, blank=True)

    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_order_combo_items'
        verbose_name = 'Order Combo Item'
        verbose_name_plural = 'Order Combo Items'

    def __str__(self):
        combo_name = self.combo.name if self.combo else self.display_data.get('combo_name', 'Combo')
        return f"{self.quantity}x {combo_name} in Order {self.order_id}"

    @property
    def subtotal(self):
        if self.order_item:
            return self.order_item.subtotal
        return 0
