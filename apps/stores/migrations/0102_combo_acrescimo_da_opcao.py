from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    """Acréscimo por opção em combo de preço fechado ("Tilápia +R$ 3,00").
    Coluna com default 0: nenhum combo existente muda de preço."""

    dependencies = [
        ('stores', '0101_ligar_clientes_orfaos'),
    ]

    operations = [
        migrations.AddField(
            model_name='comboproductgroupvariantlimit',
            name='acrescimo',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10),
        ),
        migrations.AddField(
            model_name='comboproductgroupproductoption',
            name='acrescimo',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10),
        ),
    ]
