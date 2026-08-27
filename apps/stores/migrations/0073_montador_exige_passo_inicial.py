"""
Tira a configuração de montador de loja que não monta nada.

A 0072 procurou os slugs base/proteina/complemento/molhos em TODA loja para
reproduzir no banco o contrato que estava cravado no storefront. Mas "molhos"
também é categoria comum de quem não monta: a Pastita tem molhos no cardápio e
acabou com um passo configurado, o que faria o montador aparecer lá — com um
passo só.

A regra: sem passo na ordem 0, a loja não tem montador.
"""
from django.db import migrations


def limpar(apps, schema_editor):
    StoreCategory = apps.get_model('stores', 'StoreCategory')

    lojas_com_passo_inicial = set(
        StoreCategory.objects
        .filter(builder_step_order=0)
        .values_list('store_id', flat=True)
    )

    StoreCategory.objects.filter(
        builder_step_order__isnull=False
    ).exclude(store_id__in=lojas_com_passo_inicial).update(
        builder_step_order=None,
        builder_max_selections=1,
        builder_required=False,
        builder_included=False,
        builder_expand_variants=False,
    )


def nao_reverte(apps, schema_editor):
    """Reverter recriaria justamente a configuração errada."""


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0072_montador_configuracao_atual'),
    ]

    operations = [
        migrations.RunPython(limpar, nao_reverte),
    ]
