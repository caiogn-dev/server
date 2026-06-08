"""
Migration: Replace customizations with group_selections in StoreCartComboItem.

Changes:
- Remove customizations field (was unused)
- Add group_selections field to store variant selections per group
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0027_add_order_fk_to_storeordercomboitem'),
    ]

    operations = [
        # Remove the old customizations field
        migrations.RemoveField(
            model_name='storecartcomboitem',
            name='customizations',
        ),
        # Add group_selections to store group → variant selections
        migrations.AddField(
            model_name='storecartcomboitem',
            name='group_selections',
            field=models.JSONField(blank=True, default=dict),
        ),
        # Ensure combo FK is properly set to null with no default
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
