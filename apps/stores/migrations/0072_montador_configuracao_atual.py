"""
Traduz para o banco o montador que estava cravado no código do storefront.

Até aqui `SaladBuilder.jsx` trazia os quatro passos fixos:

    base        max 1   obrigatório
    proteina    max 3   opcional
    complemento max 20  opcional
    molho       max 1   obrigatório, incluso, expande variantes (4 sabores)

Esta migration escreve exatamente essa configuração para toda loja que já
tenha as categorias correspondentes, de modo que o comportamento observado
hoje continue idêntico depois que o storefront passar a ler do banco. Lojas
sem essas categorias ficam sem montador — que também é o comportamento atual.
"""
from django.db import migrations


# Espelho fiel do STEPS que vivia no frontend.
CONFIG_ATUAL = {
    'base':        dict(ordem=0, maximo=1,  obrigatorio=True,  incluso=False, variantes=False),
    'proteina':    dict(ordem=1, maximo=3,  obrigatorio=False, incluso=False, variantes=False),
    'complemento': dict(ordem=2, maximo=20, obrigatorio=False, incluso=False, variantes=False),
    'molhos':      dict(ordem=3, maximo=1,  obrigatorio=True,  incluso=True,  variantes=True),
}


def aplicar(apps, schema_editor):
    StoreCategory = apps.get_model('stores', 'StoreCategory')

    for slug, cfg in CONFIG_ATUAL.items():
        StoreCategory.objects.filter(slug=slug).update(
            builder_step_order=cfg['ordem'],
            builder_max_selections=cfg['maximo'],
            builder_required=cfg['obrigatorio'],
            builder_included=cfg['incluso'],
            builder_expand_variants=cfg['variantes'],
        )


def reverter(apps, schema_editor):
    StoreCategory = apps.get_model('stores', 'StoreCategory')
    StoreCategory.objects.filter(slug__in=CONFIG_ATUAL).update(
        builder_step_order=None,
        builder_max_selections=1,
        builder_required=False,
        builder_included=False,
        builder_expand_variants=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0071_montador_por_categoria'),
    ]

    operations = [
        migrations.RunPython(aplicar, reverter),
    ]
