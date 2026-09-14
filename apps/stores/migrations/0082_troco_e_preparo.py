from django.db import migrations, models


class Migration(migrations.Migration):
    """Troco do pagamento em dinheiro + tempo de preparo (loja e pedido)."""

    dependencies = [('stores', '0081_banners_do_cardapio')]

    operations = [
        migrations.AddField(
            model_name='storeorder',
            name='change_for',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='storeorder',
            name='prep_minutes',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='store',
            name='default_prep_minutes',
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
