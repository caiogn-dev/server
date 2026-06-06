# Generated migration to add order FK to StoreOrderComboItem

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0026_alter_storeordercomboitem_order_item_and_more'),
    ]

    operations = [
        # Add order FK to StoreOrderComboItem
        migrations.AddField(
            model_name='storeordercomboitem',
            name='order',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='combo_items',
                to='stores.storeorder'
            ),
        ),
        # Populate order from order_item
        migrations.RunPython(
            code=lambda apps, schema_editor: populate_order_fk(apps, schema_editor),
            reverse_code=lambda apps, schema_editor: None,
        ),
        # Make order NOT NULL after populating
        migrations.AlterField(
            model_name='storeordercomboitem',
            name='order',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='combo_items',
                to='stores.storeorder'
            ),
        ),
    ]


def populate_order_fk(apps, schema_editor):
    """Populate order FK from order_item.order."""
    StoreOrderComboItem = apps.get_model('stores', 'StoreOrderComboItem')

    for combo_item in StoreOrderComboItem.objects.filter(order__isnull=True).select_related('order_item'):
        if combo_item.order_item and combo_item.order_item.order:
            combo_item.order = combo_item.order_item.order
            combo_item.save(update_fields=['order'])
