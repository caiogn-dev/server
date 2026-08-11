"""
Popula a linha B2B "Catálogo de Pratos" da Ivoneth Congelados.

Fonte: os 3 PNGs de "CATÁLOGO DE PRATOS — soluções gastronômicas para
restaurantes e hotéis" em `/home/graco/ftp-data/catalogos/`. São 23 pratos
prontos, público diferente do resto da loja (não é o cliente final de festa,
é restaurante/hotel comprando prato pronto para servir).

🚨 NÃO RODAR ANTES DE PREENCHER `PRECOS`. O catálogo de origem não traz
   valor nenhum — nem preço, nem unidade de venda (porção? quilo? cuba?).
   Enquanto `PRECOS` tiver `None`, o comando recusa e lista o que falta,
   em vez de publicar prato com preço inventado.

Segue o mesmo desenho do [[populate_ivoneth_coffee_break]]: aditivo,
idempotente por slug, sem encostar no resto do cardápio que a dona edita
pelo painel.

Usage:
    python manage.py populate_ivoneth_pratos --dry-run   # confere sem gravar
    python manage.py populate_ivoneth_pratos
"""
import logging
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.stores.models import Store, StoreCategory, StoreProduct

logger = logging.getLogger(__name__)

STORE_SLUG = 'ivoneth-banqueteria'

CATEGORY = {
    'slug': 'pratos-prontos',
    'name': 'Pratos Prontos — Restaurantes e Hotéis',
    'description': 'Linha B2B: pratos prontos congelados para operações que buscam '
                   'praticidade, padronização e apresentação. Risotos, filé mignon, '
                   'peixes, regionais, massas e molhos.',
    'sort_order': 10,
}

# ⬇️⬇️ PREENCHER. Chave = SKU, valor = preço de venda na plataforma.
# Deixe `None` no que ainda não tem preço definido — o comando aponta os
# pendentes e não grava nada.
PRECOS = {
    'IVP-RIS-PARMESAO': None,
    'IVP-RIS-SICILIANO': None,
    'IVP-RIS-FUNGHI': None,
    'IVP-RIS-COSTELA': None,
    'IVP-FM-TORNEDOR-VINHO': None,
    'IVP-FM-ISCAS-4QUEIJOS': None,
    'IVP-FM-TORNEDOR-ROTH': None,
    'IVP-FM-STROGONOFF': None,
    'IVP-FRANGO-STROGONOFF': None,
    'IVP-PX-TILAPIA-GRELHADA': None,
    'IVP-PX-PIRARUCU': None,
    'IVP-PX-MOQUECA-TILAPIA': None,
    'IVP-VEG-MOQUECA-BANANA': None,
    'IVP-REG-CHAMBARIL': None,
    'IVP-REG-RABADA': None,
    'IVP-MAS-FETT-4QUEIJOS': None,
    'IVP-MAS-FETT-FILE-VINHO': None,
    'IVP-MAS-ESPAGUETE-ABOBRINHA': None,
    'IVP-MAS-RONDELLI-BACALHAU': None,
    'IVP-MAS-CONCHIGLIONE-CAMARAO': None,
    'IVP-MAS-CONCHIGLIONE-FRANGO': None,
    'IVP-MOL-TOMATE': None,
    'IVP-MOL-BOLONHESA': None,
}

# `linha` agrupa dentro da categoria (vira a primeira etiqueta e ajuda o
# agente de WhatsApp a responder "quais risotos vocês têm?").
# `acompanha` é o que o catálogo descreve como acompanhamento do prato.
PRATOS = [
    # --- Risotos ---
    {'sku': 'IVP-RIS-PARMESAO', 'linha': 'Risotos', 'name': 'Risoto de Parmesão'},
    {'sku': 'IVP-RIS-SICILIANO', 'linha': 'Risotos', 'name': 'Risoto Siciliano com Bacon'},
    {'sku': 'IVP-RIS-FUNGHI', 'linha': 'Risotos', 'name': 'Risoto de Filé e Funghi'},
    {'sku': 'IVP-RIS-COSTELA', 'linha': 'Risotos', 'name': 'Risoto de Costela'},

    # --- Filé Mignon ---
    {'sku': 'IVP-FM-TORNEDOR-VINHO', 'linha': 'Filé Mignon', 'name': 'Tornedor de Filé Mignon ao Vinho',
     'acompanha': 'risoto de parmesão'},
    {'sku': 'IVP-FM-ISCAS-4QUEIJOS', 'linha': 'Filé Mignon', 'name': 'Iscas de Filé Mignon ao Molho 4 Queijos',
     'acompanha': 'fettuccine artesanal'},
    {'sku': 'IVP-FM-TORNEDOR-ROTH', 'linha': 'Filé Mignon', 'name': 'Tornedor de Filé Mignon ao Molho Roth',
     'acompanha': 'arroz, brócolis e legumes salteados'},
    {'sku': 'IVP-FM-STROGONOFF', 'linha': 'Filé Mignon', 'name': 'Strogonoff de Filé Mignon',
     'acompanha': 'arroz e brócolis'},
    {'sku': 'IVP-FRANGO-STROGONOFF', 'linha': 'Filé Mignon', 'name': 'Strogonoff de Frango',
     'acompanha': 'arroz e brócolis'},

    # --- Peixes ---
    {'sku': 'IVP-PX-TILAPIA-GRELHADA', 'linha': 'Peixes', 'name': 'Tilápia Grelhada',
     'acompanha': 'purê de batata e legumes salteados'},
    {'sku': 'IVP-PX-PIRARUCU', 'linha': 'Peixes', 'name': 'Pirarucu Confitado',
     'acompanha': 'purê de banana da terra e farofinha de castanhas brasileira'},
    {'sku': 'IVP-PX-MOQUECA-TILAPIA', 'linha': 'Peixes', 'name': 'Moqueca de Tilápia',
     'acompanha': 'arroz e legumes grelhados'},

    # --- Vegetariano ---
    {'sku': 'IVP-VEG-MOQUECA-BANANA', 'linha': 'Vegetariano', 'name': 'Moqueca Vegetariana de Banana',
     'vegetariano': True},

    # --- Regionais ---
    {'sku': 'IVP-REG-CHAMBARIL', 'linha': 'Regionais', 'name': 'Chambaril',
     'acompanha': 'mandioca e arroz branco'},
    {'sku': 'IVP-REG-RABADA', 'linha': 'Regionais', 'name': 'Rabada',
     'acompanha': 'polenta cremosa e agrião'},

    # --- Massas ---
    {'sku': 'IVP-MAS-FETT-4QUEIJOS', 'linha': 'Massas', 'name': 'Fettuccine Artesanal com Iscas ao Molho 4 Queijos'},
    {'sku': 'IVP-MAS-FETT-FILE-VINHO', 'linha': 'Massas', 'name': 'Fettuccine Artesanal com Filé ao Vinho'},
    {'sku': 'IVP-MAS-ESPAGUETE-ABOBRINHA', 'linha': 'Massas', 'name': 'Espaguete de Abobrinha com Molho Rústico de Tomate',
     'vegetariano': True},
    {'sku': 'IVP-MAS-RONDELLI-BACALHAU', 'linha': 'Massas', 'name': 'Rondelli de Bacalhau'},
    {'sku': 'IVP-MAS-CONCHIGLIONE-CAMARAO', 'linha': 'Massas', 'name': 'Conchiglione de Camarão'},
    {'sku': 'IVP-MAS-CONCHIGLIONE-FRANGO', 'linha': 'Massas', 'name': 'Conchiglione de Frango'},

    # --- Molhos ---
    {'sku': 'IVP-MOL-TOMATE', 'linha': 'Molhos', 'name': 'Molho Rústico de Tomate', 'vegetariano': True},
    {'sku': 'IVP-MOL-BOLONHESA', 'linha': 'Molhos', 'name': 'Molho Bolonhesa'},
]


def monta_textos(prato):
    """Retorna (short_description, description)."""
    partes = [prato['linha']]
    if prato.get('vegetariano'):
        partes.append('vegetariano')
    curta = ' · '.join(partes)

    linhas = [f"{prato['linha']} — linha de pratos prontos para restaurantes e hotéis."]
    if prato.get('acompanha'):
        linhas.append(f"Acompanha: {prato['acompanha']}.")
    if prato.get('vegetariano'):
        linhas.append('Opção vegetariana.')
    return curta, '\n'.join(linhas)


class Command(BaseCommand):
    help = 'Cria/atualiza a linha B2B de pratos prontos da Ivoneth Congelados'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Mostra o que seria criado, sem gravar')

    @transaction.atomic
    def handle(self, *args, **options):
        faltando = [sku for sku, preco in PRECOS.items() if preco is None]
        if faltando:
            self.stdout.write(self.style.ERROR(
                f'❌ {len(faltando)} de {len(PRECOS)} pratos sem preço definido. '
                'Preencha PRECOS no topo do arquivo antes de rodar.'))
            for sku in faltando:
                nome = next((p['name'] for p in PRATOS if p['sku'] == sku), sku)
                self.stdout.write(f'   • {sku} — {nome}')
            raise CommandError('PRECOS incompleto — nada foi gravado.')

        try:
            store = Store.objects.get(slug=STORE_SLUG)
        except Store.DoesNotExist:
            raise CommandError(f'Loja {STORE_SLUG} não encontrada')

        if options['dry_run']:
            for prato in PRATOS:
                curta, desc = monta_textos(prato)
                self.stdout.write(f"{prato['name']} — R$ {PRECOS[prato['sku']]} — {curta}")
            raise CommandError('--dry-run: nada gravado.')

        categoria, criada = StoreCategory.objects.update_or_create(
            store=store, slug=CATEGORY['slug'],
            defaults={'name': CATEGORY['name'], 'description': CATEGORY['description'],
                      'sort_order': CATEGORY['sort_order'], 'is_active': True},
        )
        self.stdout.write(self.style.SUCCESS(
            f"{'✅ Categoria criada' if criada else '♻️  Categoria atualizada'}: {categoria.name}"))

        for ordem, prato in enumerate(PRATOS, start=1):
            curta, desc = monta_textos(prato)
            produto, criado = StoreProduct.objects.update_or_create(
                store=store,
                slug=f"prato-{prato['sku'].lower().replace('ivp-', '')}",
                defaults={
                    'category': categoria,
                    'name': prato['name'],
                    'sku': prato['sku'],
                    'short_description': curta,
                    'description': desc,
                    'price': Decimal(str(PRECOS[prato['sku']])),
                    'featured': False,
                    'sort_order': ordem,
                    'attributes': {'linha': prato['linha'],
                                   'vegetariano': bool(prato.get('vegetariano'))},
                    'tags': ['prato pronto', 'b2b', prato['linha'].lower()],
                    'track_stock': False,
                    'status': 'active',
                    'is_active': True,
                },
            )
            self.stdout.write(f"  {'＋' if criado else '↻'} {produto.name} — R$ {produto.price}")

        self.stdout.write(self.style.SUCCESS(f'\n✅ {len(PRATOS)} pratos no ar'))
