# Generated migration for Task 2: Refactor StoreOrderComboItem to track customer variant selections

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0024_combos_builder'),
    ]

    operations = [
        # Drop the old StoreOrderComboItem table and recreate it with new structure
        migrations.DeleteModel(
            name='StoreOrderComboItem',
        ),
        migrations.CreateModel(
            name='StoreOrderComboItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('selected_variant_ids', models.JSONField(default=list)),
                ('selected_variants_data', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('combo', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='stores.storecombo')),
                ('order_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='combo_selections', to='stores.storeorderitem')),
            ],
            options={
                'verbose_name': 'Order Combo Item',
                'verbose_name_plural': 'Order Combo Items',
                'db_table': 'store_order_combo_items',
            },
        ),
    ]
