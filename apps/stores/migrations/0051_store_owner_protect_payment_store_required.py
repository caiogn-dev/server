"""Integridade de dados (P0):
- Store.owner CASCADE -> PROTECT (deletar User não pode evaporar a loja).
- StorePayment.store NULL-able -> NOT NULL (invariante saía do save() para o banco).

O backfill infere store a partir do order antes de aplicar o NOT NULL. Pela
regra do save(), toda cobrança sem store necessariamente tinha order (avulso
exige store explícito), logo o backfill cobre todas as linhas criadas via ORM.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_payment_store(apps, schema_editor):
    StorePayment = apps.get_model('stores', 'StorePayment')
    qs = StorePayment.objects.filter(store__isnull=True, order__isnull=False)
    for pay in qs.iterator():
        pay.store_id = pay.order.store_id
        pay.save(update_fields=['store'])


def noop(apps, schema_editor):
    # Reversão do NOT NULL não precisa restaurar NULLs.
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('stores', '0050_merge_20260630_2242'),
    ]

    operations = [
        migrations.RunPython(backfill_payment_store, noop),
        migrations.AlterField(
            model_name='store',
            name='owner',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='owned_stores',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='storepayment',
            name='store',
            field=models.ForeignKey(
                blank=True,
                help_text='Loja dona da cobrança (obrigatório; inferido do pedido quando há order)',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='store_payments',
                to='stores.store',
            ),
        ),
    ]
