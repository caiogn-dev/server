from django.db import migrations, models


class Migration(migrations.Migration):
    """Acréscimo cobrado do cliente quando ele paga com vale.

    Coluna própria em vez de `metadata`: é dinheiro que relatório soma, e
    número de dinheiro dentro de JSON não entra em `aggregate`.
    """

    dependencies = [('stores', '0079_voucher_pagarme')]

    operations = [
        migrations.AddField(
            model_name='storeorder',
            name='voucher_fee',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
