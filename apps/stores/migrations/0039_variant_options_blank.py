from django.db import migrations, models


class Migration(migrations.Migration):
    """options da variante passa a aceitar vazio (blank=True) — variantes simples
    como sabores de molho não precisam preencher o JSON."""

    dependencies = [
        ('stores', '0038_combo_id_nullable'),
    ]

    operations = [
        migrations.AlterField(
            model_name='storeproductvariant',
            name='options',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
