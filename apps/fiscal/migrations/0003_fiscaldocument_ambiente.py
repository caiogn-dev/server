from django.db import migrations, models


class Migration(migrations.Migration):
    """Até 19/set nenhuma loja emitiu em produção: o default preenche toda nota
    existente como homologação, que é o que ela é."""

    dependencies = [
        ('fiscal', '0002_fiscaldocument_modelo'),
    ]

    operations = [
        migrations.AddField(
            model_name='fiscaldocument',
            name='ambiente',
            field=models.CharField(default='homologacao', max_length=12),
        ),
    ]
