"""Uma pessoa, um cadastro por loja — garantido pelo banco.

Normalizar telefone é convenção: depende de cada caminho que cria cliente
lembrar da regra, e já falhou quatro vezes neste projeto. A trava não depende
de ninguém lembrar.

A canonização roda ANTES da trava, dentro da mesma migração, porque a trava não
sobe com duplicata no banco — e duplicata no banco é justamente o motivo dela
existir. Separar os dois passos faria o deploy quebrar em qualquer ambiente que
já tenha o problema, que é todo ambiente.
"""
from collections import defaultdict

from django.conf import settings
from django.db import migrations, models


def _canonizar_e_fundir(apps, schema_editor):
    from django.db import transaction

    from apps.core.utils import normalize_phone_number

    StoreCustomer = apps.get_model('stores', 'StoreCustomer')
    StoreCustomerAddress = apps.get_model('stores', 'StoreCustomerAddress')

    grupos = defaultdict(list)
    for cadastro in StoreCustomer.objects.exclude(phone=''):
        try:
            canonico = normalize_phone_number(cadastro.phone) or cadastro.phone
        except Exception:
            canonico = cadastro.phone
        grupos[(cadastro.store_id, canonico)].append(cadastro)

    # Transação própria: a migração não é atômica (ver a classe abaixo), então
    # a fusão precisa garantir sozinha que não fica pela metade.
    with transaction.atomic():
        for (_, canonico), linhas in grupos.items():
            # Mais pedidos vence; empate, o mais antigo — é o "cliente desde"
            # que os relatórios já contam.
            linhas.sort(key=lambda c: (-(c.total_orders or 0), c.created_at))
            fica, saem = linhas[0], linhas[1:]

            for perdedor in saem:
                # Contadores da MESMA pessoa que ficaram partidos ao meio.
                fica.total_orders = (fica.total_orders or 0) + (perdedor.total_orders or 0)
                fica.total_spent = (fica.total_spent or 0) + (perdedor.total_spent or 0)
                if perdedor.last_order_at and (
                    not fica.last_order_at or perdedor.last_order_at > fica.last_order_at
                ):
                    fica.last_order_at = perdedor.last_order_at
                StoreCustomerAddress.objects.filter(customer=perdedor).update(customer=fica)
                perdedor.delete()

            if saem or fica.phone != canonico:
                fica.phone = canonico
                fica.save()


def _so_tira_a_trava(apps, schema_editor):
    """A fusão não tem volta: não se sabe qual formato torto era de quem.

    Existe para a migração ser reversível — a trava sai — sem fingir que
    desfazer a fusão é possível.
    """


class Migration(migrations.Migration):

    # NÃO atômica de propósito. O Postgres recusa criar índice na mesma
    # transação que apagou linhas da tabela ("pending trigger events"), e a
    # fusão apaga cadastros logo antes da trava subir. Sem isto a migração
    # falha em qualquer banco que já tenha duplicata — ou seja, em todos.
    atomic = False

    dependencies = [
        ('stores', '0076_cupons_de_entrega'),
        ('users', '0004_useraddress_complement'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(_canonizar_e_fundir, _so_tira_a_trava),
        migrations.AddConstraint(
            model_name='storecustomer',
            constraint=models.UniqueConstraint(
                fields=('store', 'phone'),
                condition=models.Q(('phone', ''), _negated=True),
                name='cliente_unico_por_telefone_na_loja',
            ),
        ),
    ]
