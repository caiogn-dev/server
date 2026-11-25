from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0107_ifood_entrega'),
    ]

    operations = [
        migrations.AddField(
            model_name='storecategory',
            name='aviso',
            field=models.CharField(blank=True, default='', max_length=80),
        ),
    ]
