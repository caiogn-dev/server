"""
Migration: Allow virtual combo items in cart (salad builder support).

Changes to StoreCartComboItem:
- combo FK: CASCADE → SET_NULL, null=True, blank=True
- combo_name: new CharField (stores name for virtual combos)
- unit_price: new DecimalField (stores price for virtual combos)
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0002_add_status_timestamps'),
    ]

    operations = [
        # 1. Make combo FK nullable + change on_delete to SET_NULL
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
        # 2. Add combo_name field
        migrations.AddField(
            model_name='storecartcomboitem',
            name='combo_name',
            field=models.CharField(blank=True, max_length=255, default=''),
            preserve_default=False,
        ),
        # 3. Add unit_price field
        migrations.AddField(
            model_name='storecartcomboitem',
            name='unit_price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
    ]
