# Reconciliation migration for the combo refactor.
#
# Context: an earlier, never-committed migration mutated the physical DB
# (removed order_item / selected_variant_ids / selected_variants_data from
# store_order_combo_items, dropped combo_name / unit_price / customizations
# from store_cart_combo_items, and added display_data / group_selections /
# quantity). The committed migration graph never saw those changes, so an
# auto-generated migration both (a) tried to re-add already-present columns
# and (b) failed to restore the dropped ones.
#
# This migration uses AddFieldIfMissing so it is idempotent against ANY of
# those divergent states: it brings every combo-item column in line with the
# current models, skipping the DDL for columns that already exist. Both combo
# tables are empty, so adding NOT NULL columns is safe.
import django.db.models.deletion
from django.db import migrations, models


class AddFieldIfMissing(migrations.AddField):
    """AddField that no-ops at the DB level when the column already exists."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        table_name = model._meta.db_table
        with schema_editor.connection.cursor() as cursor:
            columns = {
                column.name
                for column in schema_editor.connection.introspection.get_table_description(
                    cursor, table_name
                )
            }
        field = model._meta.get_field(self.name)
        if field.column in columns:
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0028_rename_customizations_add_group_selections'),
    ]

    operations = [
        # --- StoreOrderComboItem: restore + add columns to match the model ---
        AddFieldIfMissing(
            model_name='storeordercomboitem',
            name='order_item',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='combo_selections',
                to='stores.storeorderitem',
            ),
        ),
        AddFieldIfMissing(
            model_name='storeordercomboitem',
            name='selected_variant_ids',
            field=models.JSONField(default=list),
        ),
        AddFieldIfMissing(
            model_name='storeordercomboitem',
            name='selected_variants_data',
            field=models.JSONField(blank=True, default=list),
        ),
        AddFieldIfMissing(
            model_name='storeordercomboitem',
            name='group_selections',
            field=models.JSONField(default=dict),
        ),
        AddFieldIfMissing(
            model_name='storeordercomboitem',
            name='display_data',
            field=models.JSONField(blank=True, default=dict),
        ),
        AddFieldIfMissing(
            model_name='storeordercomboitem',
            name='quantity',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name='storeordercomboitem',
            name='combo',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='stores.storecombo',
            ),
        ),
        # --- StoreCartComboItem: restore + add columns to match the model ---
        AddFieldIfMissing(
            model_name='storecartcomboitem',
            name='combo_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        AddFieldIfMissing(
            model_name='storecartcomboitem',
            name='unit_price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        AddFieldIfMissing(
            model_name='storecartcomboitem',
            name='customizations',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='storecartcomboitem',
            name='combo',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cart_items',
                to='stores.storecombo',
            ),
        ),
    ]
