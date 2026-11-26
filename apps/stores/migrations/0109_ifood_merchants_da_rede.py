from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0108_storecategory_aviso'),
    ]

    operations = [
        migrations.AddField(
            model_name='storeifoodintegration',
            name='merchants_da_rede',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
