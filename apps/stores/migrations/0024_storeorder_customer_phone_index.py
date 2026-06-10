from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0023_rename_stores_stor_deliver_a12b3c_store_order_deliver_f8add8_idx_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='storeorder',
            name='customer_phone',
            field=models.CharField(db_index=True, max_length=20),
        ),
    ]
