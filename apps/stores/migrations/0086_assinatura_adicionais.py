from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0085_caixa_esperado_ao_vivo'),
    ]

    operations = [
        migrations.AddField(
            model_name='storesubscription',
            name='adicionais',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
