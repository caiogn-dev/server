# Generated migration for ComboBuilder feature

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0023_rename_stores_stor_deliver_a12b3c_store_order_deliver_f8add8_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='storecomboitem',
            name='selection_rule',
            field=models.JSONField(blank=True, default=dict, help_text="Rules for variant selection: {'required': true, 'min_selections': 4, 'max_selections': 4}"),
        ),
    ]
