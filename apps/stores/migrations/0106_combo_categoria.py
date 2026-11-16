import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0105_uber_cotacao'),
    ]

    operations = [
        migrations.AddField(
            model_name='storecombo',
            name='category',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='combos',
                to='stores.storecategory',
            ),
        ),
    ]
