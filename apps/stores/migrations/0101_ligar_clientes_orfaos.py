"""Liga à identidade (UnifiedUser) todo cliente da loja que ficou sem ela.

Usa os modelos reais de propósito: a regra de resolução (telefone, login,
e-mail) mora em UnifiedUser.resolve e não deve ser copiada aqui.
"""
from django.db import migrations


def ligar(apps, schema_editor):
    from apps.stores.services.identidade_do_cliente import ligar_orfaos
    ligar_orfaos()


class Migration(migrations.Migration):
    dependencies = [
        ('stores', '0100_cliente_pf_pj'),
        ('users', '0004_useraddress_complement'),
    ]
    operations = [migrations.RunPython(ligar, migrations.RunPython.noop)]
