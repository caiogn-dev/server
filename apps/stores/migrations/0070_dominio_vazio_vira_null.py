"""
Loja sem domínio próprio gravada com '' em vez de NULL.

`custom_domain` é unique. NULL não colide com NULL no Postgres, mas '' colide
com '' — e o painel manda '' sempre que o campo está em branco. Bastou UMA loja
com '' no banco para que toda outra loja sem domínio próprio quebrasse com
IntegrityError ao salvar qualquer campo (template, cor, tagline).

O `Store.save()` passou a normalizar '' para NULL; esta migration limpa o que
já estava gravado — sem ela o registro sujo continua bloqueando as demais até
alguém salvar aquela loja específica.
"""
from django.db import migrations


def vazio_vira_null(apps, schema_editor):
    Store = apps.get_model('stores', 'Store')
    Store.objects.filter(custom_domain='').update(custom_domain=None)


def reverter(apps, schema_editor):
    # Voltar NULL para '' recriaria a colisão. Nada a desfazer.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0069_promocao_semanal'),
    ]

    operations = [
        migrations.RunPython(vazio_vira_null, reverter),
    ]
