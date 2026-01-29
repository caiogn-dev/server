# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0012_add_order_access_token'),
        ('automation', '0003_unify_scheduled_messages'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customersession',
            name='order',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name='customer_sessions',
                to='stores.storeorder',
            ),
        ),
    ]
