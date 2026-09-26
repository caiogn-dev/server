from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0088_printagent_imprime'),
    ]

    operations = [
        migrations.AddField(
            model_name='storeproduct',
            name='metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
