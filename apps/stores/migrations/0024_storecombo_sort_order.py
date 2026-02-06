# Generated migration to add sort_order to StoreCombo
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("stores", "0023_alter_store_whatsapp_account"),
    ]

    operations = [
        migrations.AddField(
            model_name="storecombo",
            name="sort_order",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
