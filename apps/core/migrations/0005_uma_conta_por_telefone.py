"""Uma pessoa, uma conta — garantido pelo banco.

Fundir as 9 contas duplicadas resolveu o passado. Sem trava o futuro se repete:
vários caminhos criam usuário (OTP do WhatsApp, checkout, painel, importação) e
basta um esquecer de procurar antes de criar — foi assim nas quatro vezes
anteriores em que "normalizamos o telefone" e o problema voltou.

A canonização roda ANTES da trava, na mesma migração, porque a trava não sobe
com duplicata no banco. Não é atômica pelo mesmo motivo da 0077: o Postgres
recusa criar índice na mesma transação que alterou linhas da tabela.
"""
from django.conf import settings
from django.db import migrations, models


def _canonizar_telefones(apps, schema_editor):
    from apps.core.utils import normalize_phone_number

    UserProfile = apps.get_model('core', 'UserProfile')
    vistos = {}
    for perfil in UserProfile.objects.exclude(phone='').order_by('id'):
        try:
            canonico = normalize_phone_number(perfil.phone) or perfil.phone
        except Exception:
            canonico = perfil.phone

        if canonico in vistos:
            # Duplicata que sobrou: o telefone sai do perfil mais NOVO, em vez
            # de apagar a conta. Apagar usuário dentro de uma migração é
            # destruir histórico de compra sem ninguém olhando — a fusão é um
            # comando separado, com modo seco, feito por quem vê a lista.
            perfil.phone = ''
            perfil.save()
            continue

        vistos[canonico] = perfil.id
        if perfil.phone != canonico:
            perfil.phone = canonico
            perfil.save()


def _so_tira_a_trava(apps, schema_editor):
    """Reversível na trava; a canonização não tem volta."""


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('core', '0004_preferencias_do_cliente'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(_canonizar_telefones, _so_tira_a_trava),
        migrations.AddConstraint(
            model_name='userprofile',
            constraint=models.UniqueConstraint(
                fields=('phone',),
                condition=models.Q(('phone', ''), _negated=True),
                name='uma_conta_por_telefone',
            ),
        ),
    ]
