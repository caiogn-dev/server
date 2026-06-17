import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Alinha o banco aos models: combo pode ser nulo (combos virtuais como o
    salad builder). Os models já declaram null=True; faltava a migration."""

    dependencies = [
        ('stores', '0037_storecategory_is_builder_group'),
    ]

    operations = [
        migrations.AlterField(
            model_name='storecartcomboitem',
            name='combo',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cart_items', to='stores.storecombo',
            ),
        ),
        migrations.AlterField(
            model_name='storeordercomboitem',
            name='combo',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='stores.storecombo',
            ),
        ),
    ]
