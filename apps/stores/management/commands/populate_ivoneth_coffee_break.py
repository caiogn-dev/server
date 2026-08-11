"""
Popula a categoria "Coffee Break" da Ivoneth Congelados (slug ivoneth-banqueteria).

Fonte: card de divulgação da loja (6 opções fechadas, de 15 a 50 pessoas), em
`/home/graco/ftp-data/catalogos/`. São pacotes de preço FIXO — modelados como
produtos simples, não como combo com escolha: o cliente não monta nada, o preço
do card é o preço final.

Aditivo e idempotente: só toca na categoria `coffee-break` e nos 6 SKUs
`IVB-CB-*`. Não mexe no restante do cardápio, que a dona edita pelo painel —
por isso NÃO reaproveita `populate_ivoneth_banqueteria_menu`, que sobrescreveria
tudo com os dados de junho.

A composição de cada pacote vai em dois lugares:
  - `description`  → lista com "- " que o cardápio renderiza como <ul>
                     (cardapidex-web/src/utils/productDescription.js)
  - `attributes['inclui']` → lida pelo agente de WhatsApp para responder
                     "o que vem no coffee break de 30?" sem alucinar

Imagens: `coffee-break-{N}.webp` em MEDIA_ROOT/stores/products/ivoneth-banqueteria/
(foto + selo "COFFEE BREAK / N PESSOAS", geradas a partir do card).

Usage:
    python manage.py populate_ivoneth_coffee_break
"""
import logging
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.stores.models import Store, StoreCategory, StoreProduct

logger = logging.getLogger(__name__)

STORE_SLUG = 'ivoneth-banqueteria'
IMG_PATH = 'stores/products/ivoneth-banqueteria'

CATEGORY = {
    'slug': 'coffee-break',
    'name': 'Coffee Break',
    'description': 'Pacotes fechados de coffee break para eventos, de 15 a 50 pessoas. '
                   'Salgados, bolos, bebidas e descartáveis inclusos.',
    'sort_order': 0,
}

PACOTES = [
    {
        'pessoas': 15,
        'price': Decimal('345.00'),
        'featured': True,
        'inclui': [
            '105 joelhinhos assados',
            '15 folhados',
            '15 pães de queijo',
            '1 bolo vulcão',
            '2 L de suco',
            '1 L de refrigerante',
            '1 pacote de guardanapo',
            '50 copos descartáveis',
        ],
    },
    {
        'pessoas': 20,
        'price': Decimal('455.00'),
        'featured': True,
        'subtitulo': 'Combo Corporativo',
        'inclui': [
            '1 bolo vulcão',
            '1 torta empadão',
            '20 folhados variados',
            '20 joelhinhos assados',
            '20 biscoitinhos de queijo ou pães de queijo',
            '20 pastéis de feira',
            '50 salgadinhos fritos',
            '2 refrigerantes de 2 litros',
            '2 caixas de suco de 1 litro',
            '1 pacote de guardanapo de papel',
            '50 copos descartáveis',
        ],
    },
    {
        'pessoas': 25,
        'price': Decimal('760.00'),
        'featured': False,
        'inclui': [
            '100 salgadinhos fritos',
            '50 joelhinhos assados',
            '25 pães de queijo',
            '600g de antepasto de berinjela',
            '300g de torradas',
            '25 pastéis de feira',
            '25 folhados',
            '1 empadão de 1kg',
            '2 bolos vulcão',
            '5 L de suco',
            '4 L de refrigerante',
            '1 pacote de guardanapo',
            '50 copos descartáveis',
        ],
    },
    {
        'pessoas': 30,
        'price': Decimal('1015.00'),
        'featured': True,
        'inclui': [
            '100 salgadinhos fritos',
            '100 joelhinhos variados',
            '30 folhados',
            '1kg de antepasto de berinjela',
            '30 pães de queijo',
            '3 pacotes de torradas',
            '2 tortas empadão',
            '30 docinhos de brigadeiro e beijinho',
            '30 mini pastéis de feira',
            '25 biscoitinhos de queijo',
            '1 bolo confeitado',
            '1 bolo vulcão',
            '6 L de suco',
            '5 L de refrigerante',
            '1 pacote de guardanapo',
            '50 copos descartáveis',
        ],
    },
    {
        'pessoas': 40,
        'price': Decimal('1400.00'),
        'featured': False,
        'inclui': [
            '100 salgadinhos fritos',
            '30 pastéis de feira',
            '100 joelhinhos assados',
            '40 folhados',
            '40 pães de queijo',
            '1kg de patê de frango',
            '3 pacotes de torradas',
            '40 brigadeiros',
            '3 quiches médias',
            '24 cupcakes',
            '1 bolo confeitado',
            '2 bolos vulcão',
            '1kg de antepasto',
            '6 L de suco de caixinha',
            '6 L de refrigerante (coca e guaraná)',
            '2 pacotes de guardanapo',
            '100 copos descartáveis',
        ],
    },
    {
        'pessoas': 50,
        'price': Decimal('1695.00'),
        'featured': True,
        'inclui': [
            '150 salgadinhos fritos',
            '150 joelhinhos assados',
            '40 pastéis de feira',
            '40 pães de queijo',
            '50 folhados',
            '40 mini pães brioche',
            '1,5kg de patê de frango',
            '1kg de antepasto de berinjela',
            '4 pacotes de torradas',
            '50 docinhos',
            '24 cupcakes',
            '3 tortas salgadas médias',
            '1 bolo confeitado',
            '3 bolos vulcão',
            '8 L de suco',
            '8 L de refrigerante',
            '3 pacotes de guardanapo',
            '100 copos descartáveis',
        ],
    },
]


def monta_descricao(pacote):
    """Primeira linha vira o preview do card; o resto vira <ul> no modal."""
    cabecalho = f"Pacote fechado de coffee break para {pacote['pessoas']} pessoas."
    itens = '\n'.join(f'- {item}' for item in pacote['inclui'])
    return f"{cabecalho}\n{itens}"


class Command(BaseCommand):
    help = 'Cria/atualiza a categoria Coffee Break e os 6 pacotes da Ivoneth Congelados'

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            store = Store.objects.get(slug=STORE_SLUG)
        except Store.DoesNotExist:
            raise CommandError(f'Loja {STORE_SLUG} não encontrada')

        categoria, criada = StoreCategory.objects.update_or_create(
            store=store,
            slug=CATEGORY['slug'],
            defaults={
                'name': CATEGORY['name'],
                'description': CATEGORY['description'],
                'sort_order': CATEGORY['sort_order'],
                'is_active': True,
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f"{'✅ Categoria criada' if criada else '♻️  Categoria atualizada'}: {categoria.name}"
        ))

        for ordem, pacote in enumerate(PACOTES, start=1):
            pessoas = pacote['pessoas']
            nome = f'Coffee Break {pessoas} Pessoas'
            arquivo = f'coffee-break-{pessoas}.webp'
            caminho = Path(settings.MEDIA_ROOT) / IMG_PATH / arquivo
            if caminho.exists():
                image_url = f"{settings.MEDIA_URL.rstrip('/')}/{IMG_PATH}/{arquivo}"
            else:
                image_url = ''
                self.stdout.write(self.style.WARNING(f'  ⚠️  Imagem ausente: {arquivo}'))

            curta = pacote.get('subtitulo') or f'Serve {pessoas} pessoas.'
            produto, criado = StoreProduct.objects.update_or_create(
                store=store,
                slug=f'coffee-break-{pessoas}-pessoas',
                defaults={
                    'category': categoria,
                    'name': nome,
                    'sku': f'IVB-CB-{pessoas}',
                    'short_description': curta,
                    'description': monta_descricao(pacote),
                    'price': pacote['price'],
                    'featured': pacote['featured'],
                    'sort_order': ordem,
                    'main_image_url': image_url,
                    'attributes': {'inclui': pacote['inclui'], 'serve': pessoas},
                    # Sem a tag "coffee break": o modal já mostra o chip da
                    # categoria e as duas viravam duas etiquetas idênticas.
                    'tags': ['evento', 'corporativo', 'festa', f'{pessoas} pessoas'],
                    'track_stock': False,
                    'status': 'active',
                    'is_active': True,
                },
            )
            self.stdout.write(
                f"  {'＋' if criado else '↻'} {produto.name} — R$ {produto.price} "
                f"({len(pacote['inclui'])} itens)"
            )

        self.stdout.write(self.style.SUCCESS(f'\n✅ {len(PACOTES)} pacotes de Coffee Break no ar'))
