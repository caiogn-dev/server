"""Aplica a tabela de entrega do dono como `fixed_price_zones` nas lojas.

Uso:
    docker exec -i pastita_web python manage.py shell < scripts/configurar_zonas_fixas.py

O `geo_service` avalia as zonas fixas ANTES das faixas de km
(`_match_fixed_price_zone`, prioridade 1), casando as `keywords` contra o
endereço que o cliente escreveu + o reverse geocode do Google. Duas formas:

  fee               → taxa FIXA, ignora a distância
  surcharge_on_km   → soma `surcharge` à taxa por km em vez de substituir

A ordem da lista importa: casa a primeira que bater. Por isso os condomínios
com taxa fixa alta vêm antes das sobretaxas genéricas.
"""
from apps.stores.models import Store

# Lojas que recebem a tabela. Todas hoje ficam na Q.112 Sul (Plano Diretor
# Sul), então as observações por origem da tabela ("das Mils", "da Norte")
# não se aplicam — os valores usados são os da coluna base.
LOJAS = ['Pastita', 'Cê Saladas', 'Kero Kero', 'Ivoneth Banqueteria']

ZONAS = [
    # ── Taxa FIXA por localidade ────────────────────────────────────────────
    {
        'name': 'Mirante do Lago / Caribe / Polinésia',
        'fee': 25.0,
        'keywords': [
            'polinesia', 'caribe', 'mirante do lago',
            'ilhas marquesas', 'ilhas gregas', 'ilhas canarias',
        ],
    },
    {
        'name': 'Setor Água Fria (sentido Polinésia)',
        'fee': 25.0,
        'keywords': ['agua fria'],
    },
    {
        'name': 'Bertha Ville / Irmã Dulce / União Sul',
        'fee': 30.0,
        'keywords': ['bertha ville', 'bertaville', 'irma dulce', 'uniao sul'],
    },
    {
        'name': 'Aurenys / Setor Universitário',
        'fee': 37.0,
        'keywords': [
            'aureny', 'aurenys', 'aureny i', 'aureny ii', 'aureny iii', 'aureny iv',
            'setor universitario',
        ],
    },
    {
        'name': 'Taquaralto e região',
        'fee': 40.0,
        'keywords': [
            'taquaralto', 'lago sul', 'morada do sol', 'santa fe',
            'sol nascente', 'maria rosa', 'sonia regina', 'bela vista',
            'santa barbara', 'santa helena', 'jardim paulista',
            'jardim aeroporto', 'setor janaina', 'vale do sol',
        ],
    },
    {
        'name': 'Taquari / Flamboyant / Jardim Vitória',
        'fee': 45.0,
        'keywords': [
            'taquari', 'flamboyant', 'jardim vitoria',
            'recanto das araras', 'jardim laila',
        ],
    },
    {
        'name': 'Aeroporto',
        'fee': 50.0,
        'keywords': ['aeroporto de palmas', 'brigadeiro lysias'],
    },
    {
        'name': 'Luzimangues',
        'fee': 50.0,
        'keywords': ['luzimangues', 'porto nacional'],
    },

    # ── Sobretaxa SOBRE a taxa por km ───────────────────────────────────────
    {
        'name': 'Condomínio fechado',
        'surcharge_on_km': True,
        'surcharge': 5.0,
        'keywords': [
            'aldeia do sol', 'alphaville', 'aphaville', 'privilege', 'privilége',
            'ecoville', 'ecovile', 'vila militar', 'mangueiras', 'serra do carmo',
        ],
    },
    {
        'name': 'Praia do Prata / Caju',
        'surcharge_on_km': True,
        'surcharge': 5.0,
        'keywords': ['praia do prata', 'praia do caju', 'prata e caju'],
    },
    {
        'name': 'Campus 2 Católica',
        'surcharge_on_km': True,
        'surcharge': 5.0,
        'keywords': ['campus 2', 'catolica do tocantins', 'ulbra'],
    },
    {
        'name': 'Lago Norte',
        'surcharge_on_km': True,
        'surcharge': 2.0,
        'keywords': ['lago norte'],
    },
]


def aplicar(dry_run=True):
    for nome in LOJAS:
        loja = Store.objects.filter(name=nome).first()
        if not loja:
            print(f'  ⚠️  loja não encontrada: {nome}')
            continue
        metadata = dict(loja.metadata or {})
        antes = len(metadata.get('fixed_price_zones') or [])
        metadata['fixed_price_zones'] = ZONAS
        if not dry_run:
            loja.metadata = metadata
            loja.save(update_fields=['metadata'])
        print(f'  {"[dry-run] " if dry_run else "✓ "}{nome}: {antes} → {len(ZONAS)} zonas')


if __name__ == '__main__' or True:
    import sys
    aplicar(dry_run='--apply' not in sys.argv)
