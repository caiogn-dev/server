from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0106_combo_categoria'),
    ]

    operations = [
        migrations.AddField(
            model_name='storeifoodintegration',
            name='frete_pelo_ifood',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='storeifoodintegration',
            name='acrescimo_frete',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=6),
        ),
        migrations.AddField(
            model_name='storeifoodintegration',
            name='chamar_entregador',
            field=models.CharField(
                choices=[('manual', 'Manual'), ('confirmado', 'Ao confirmar o pedido'), ('pronto', 'Quando ficar pronto')],
                default='manual', max_length=12,
            ),
        ),
        migrations.AddField(
            model_name='storeifoodintegration',
            name='tempo_preparo_min',
            field=models.PositiveSmallIntegerField(default=15),
        ),
    ]
