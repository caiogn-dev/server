"""
Management command to populate the Ivoneth Banqueteria (Casa do Coffee Break) menu.

Cardápio de encomendas: terrines, tábuas de frios, salgados de festa, kits e bebidas.
Fonte: menu-encomenda.pdf (Casa do Coffee Break Palmas — @casadocoffeebreakpalmas).

A loja é criada pelo painel (self-service). Este comando NÃO sobrescreve a
identidade definida no painel (name/phone/owner/endereço); apenas ajusta campos
de apoio ao catálogo (tipo, marca, horário) e popula categorias e produtos.

Usage:
    python manage.py populate_ivoneth_banqueteria_menu
    python manage.py populate_ivoneth_banqueteria_menu --force
"""
import logging
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.db import transaction

from apps.stores.models import (
    Store, StoreCategory, StoreProduct, StoreProductType, StoreProductVariant,
    StoreCombo, ComboProductGroup, ComboProductGroupProductOption,
)
from apps.stores.utils.image_optimizer import ImageOptimizer

logger = logging.getLogger(__name__)
User = get_user_model()

STORE_SLUG = 'ivoneth-banqueteria'
IMG_PATH = 'stores/products/ivoneth-banqueteria'

# SKU -> arquivo de imagem (recortado do PDF do cardápio). As 6 tábuas
# compartilham a mesma foto. Arquivos ficam em MEDIA_ROOT/IMG_PATH/.
IMAGES = {
    'IVB-CAIXA-ANTEPASTO': 'caixa-antepasto.jpg', 'IVB-KIT-LANCHE': 'kit-lanche.jpg', 'IVB-KIT-FESTA': 'kit-festa.jpg',
    'IVB-TABUA-2': 'tabua-frios.jpg', 'IVB-TABUA-4': 'tabua-frios.jpg', 'IVB-TABUA-6': 'tabua-frios.jpg',
    'IVB-TABUA-8': 'tabua-frios.jpg', 'IVB-TABUA-10': 'tabua-frios.jpg', 'IVB-TABUA-20': 'tabua-frios.jpg',
    'IVB-TERRINE-PERAS': 'terrine-peras.jpg', 'IVB-TERRINE-DAMASCO': 'terrine-damasco.jpg', 'IVB-PASTA-FRANGO': 'pasta-frango.png',
    'IVB-QUEIJO-CREMOSO': 'queijo-cremoso.png', 'IVB-PASTA-PALMITO': 'pasta-palmito.png', 'IVB-QUEIJO-BRIE': 'queijo-brie.png',
    'IVB-TORTA-LOMBO': 'torta-lombo.png', 'IVB-TORTA-FRANGO': 'torta-frango.png', 'IVB-LAGARTO': 'lagarto.png',
    'IVB-BACALHAU': 'bacalhau.png', 'IVB-QUIBE': 'quibe.png', 'IVB-BERINGELA': 'beringela.png',
    'IVB-PASTEL': 'pastel.png', 'IVB-QUICHES': 'quiches.png', 'IVB-FOLHADOS': 'folhados.png',
    'IVB-MINI-HAMBURGUER': 'mini-hamburguer.png', 'IVB-MINI-SANDUICHE': 'mini-sanduiche.png', 'IVB-MINI-BRIOCHE': 'mini-brioche.png',
    'IVB-SALGADINHOS-FRITOS': 'salgadinhos-fritos.jpg', 'IVB-MINI-CROISSANT': 'mini-croissant.jpg', 'IVB-CANAPES': 'canapes.jpg',
    'IVB-BOLO-CHOCOLATE': 'bolo-chocolate.jpg', 'IVB-MINI-BOLO': 'mini-bolo.jpg', 'IVB-CESTO-PAES': 'cesto-paes.jpg',
    'IVB-GUARANA-2L': 'guarana-2l.jpg', 'IVB-SUCO-POLPA': 'suco-polpa.jpg', 'IVB-COCA-2L': 'coca-2l.jpg',
}

# Encomendas só são aceitas e pagas até as 13h, de segunda a sábado.
OPERATING_HOURS = {
    "monday": {"open": "08:00", "close": "13:00"},
    "tuesday": {"open": "08:00", "close": "13:00"},
    "wednesday": {"open": "08:00", "close": "13:00"},
    "thursday": {"open": "08:00", "close": "13:00"},
    "friday": {"open": "08:00", "close": "13:00"},
    "saturday": {"open": "08:00", "close": "13:00"},
    "sunday": {"open": "00:00", "close": "00:00"},
}

CATEGORIES = [
    {'slug': 'caixas-e-kits', 'name': 'Caixas e Kits', 'description': 'Caixas de antepastos e kits completos para festas e lanches.', 'sort_order': 1},
    {'slug': 'tabuas-de-frios', 'name': 'Tábuas de Frios', 'description': 'Tábuas de frios e queijos montadas conforme o número de pessoas.', 'sort_order': 2},
    {'slug': 'terrines-e-pastas', 'name': 'Terrines e Pastas', 'description': 'Terrines, pastas e queijos especiais por encomenda (a partir de 1kg).', 'sort_order': 3},
    {'slug': 'tortas-e-pratos', 'name': 'Tortas e Pratos', 'description': 'Tortas, carnes e antepastos por encomenda (a partir de 1kg).', 'sort_order': 4},
    {'slug': 'salgados-de-festa', 'name': 'Salgados de Festa', 'description': 'Salgados fritos, folhados, mini sanduíches e canapés.', 'sort_order': 5},
    {'slug': 'doces-e-paes', 'name': 'Doces e Pães', 'description': 'Bolos, mini bolos e cestos de pães.', 'sort_order': 6},
    {'slug': 'bebidas', 'name': 'Bebidas', 'description': 'Refrigerantes e sucos de polpa para acompanhar.', 'sort_order': 7},
]

# Preços conforme o PDF. `price` é o valor de venda na plataforma.
# Detalhes de unidade/pedido mínimo ficam em short_description.
PRODUCTS = [
    # --- Caixas e Kits ---
    {'sku': 'IVB-CAIXA-ANTEPASTO', 'category_slug': 'caixas-e-kits', 'name': 'Caixa de Antepastos', 'price': Decimal('399.00'), 'featured': True, 'sort_order': 1,
     'short_description': 'Serve até 5 pessoas.',
     'description': 'Caixa com 200g de cada: terrine de gorgonzola e damasco, pasta de frango e cream cheese, queijo cremoso e tomate confit, carne louca, antepasto de berinjela, bacalhau marinado, e 600g de cesto de pães. Serve até 5 pessoas. Extra: Queijo Brie por R$ 299,00 (peça média de 1,5kg) — pedido mínimo 400g se junto com a caixa: R$ 179,90.',
     'tags': ['caixa', 'antepasto', 'festa']},
    {'sku': 'IVB-KIT-LANCHE', 'category_slug': 'caixas-e-kits', 'name': 'Kit Lanche', 'price': Decimal('95.00'), 'featured': True, 'sort_order': 2,
     'short_description': '50 salgados fritos + refri 2L + bolo simples.',
     'description': '50 salgados fritos + 1 refrigerante 2 litros + 1 bolo simples.',
     'tags': ['kit', 'lanche', 'festa']},
    {'sku': 'IVB-KIT-FESTA', 'category_slug': 'caixas-e-kits', 'name': 'Kit Festa', 'price': Decimal('189.00'), 'featured': True, 'sort_order': 3,
     'short_description': 'Bolo 1kg + 25 folhados + 25 brigadeiros + 50 fritos.',
     'description': '1 bolo simples de 1kg, 25 folhados, 25 brigadeiros e 50 salgadinhos fritos. Disponível de segunda a sábado.',
     'tags': ['kit', 'festa', 'completo']},

    # --- Tábuas de Frios ---
    {'sku': 'IVB-TABUA-2', 'category_slug': 'tabuas-de-frios', 'name': 'Tábua de Frios — 2 Pessoas', 'price': Decimal('139.99'), 'featured': True, 'sort_order': 1,
     'short_description': 'Serve 2 pessoas.', 'description': 'Provolone, parmesão, gorgonzola, mussarela, lombo canadense, salaminho, presunto, azeitonas, tomate seco e snacks. Serve 2 pessoas.', 'tags': ['tabua', 'frios', 'queijos']},
    {'sku': 'IVB-TABUA-4', 'category_slug': 'tabuas-de-frios', 'name': 'Tábua de Frios — 4 Pessoas', 'price': Decimal('169.99'), 'featured': False, 'sort_order': 2,
     'short_description': 'Serve 4 pessoas.', 'description': 'Provolone, parmesão, gorgonzola, mussarela, lombo canadense, salaminho, presunto, azeitonas, tomate seco e snacks. Serve 4 pessoas.', 'tags': ['tabua', 'frios', 'queijos']},
    {'sku': 'IVB-TABUA-6', 'category_slug': 'tabuas-de-frios', 'name': 'Tábua de Frios — 6 Pessoas', 'price': Decimal('199.99'), 'featured': False, 'sort_order': 3,
     'short_description': 'Serve 6 pessoas.', 'description': 'Provolone, parmesão, gorgonzola, mussarela, lombo canadense, salaminho, presunto, azeitonas, tomate seco e snacks. Serve 6 pessoas.', 'tags': ['tabua', 'frios', 'queijos']},
    {'sku': 'IVB-TABUA-8', 'category_slug': 'tabuas-de-frios', 'name': 'Tábua de Frios — 8 Pessoas', 'price': Decimal('239.99'), 'featured': False, 'sort_order': 4,
     'short_description': 'Serve 8 pessoas.', 'description': 'Provolone, parmesão, gorgonzola, mussarela, lombo canadense, salaminho, presunto, azeitonas, tomate seco e snacks. Serve 8 pessoas.', 'tags': ['tabua', 'frios', 'queijos']},
    {'sku': 'IVB-TABUA-10', 'category_slug': 'tabuas-de-frios', 'name': 'Tábua de Frios — 10 Pessoas', 'price': Decimal('299.99'), 'featured': False, 'sort_order': 5,
     'short_description': 'Serve 10 pessoas.', 'description': 'Provolone, parmesão, gorgonzola, mussarela, lombo canadense, salaminho, presunto, azeitonas, tomate seco e snacks. Serve 10 pessoas.', 'tags': ['tabua', 'frios', 'queijos']},
    {'sku': 'IVB-TABUA-20', 'category_slug': 'tabuas-de-frios', 'name': 'Tábua de Frios — 20 Pessoas', 'price': Decimal('519.99'), 'featured': False, 'sort_order': 6,
     'short_description': 'Serve 20 pessoas.', 'description': 'Provolone, parmesão, gorgonzola, mussarela, lombo canadense, salaminho, presunto, azeitonas, tomate seco e snacks. Serve 20 pessoas.', 'tags': ['tabua', 'frios', 'queijos']},

    # --- Terrines e Pastas (por kg) ---
    {'sku': 'IVB-TERRINE-PERAS', 'category_slug': 'terrines-e-pastas', 'name': 'Terrine de Gorgonzola e Peras', 'price': Decimal('159.90'), 'featured': True, 'sort_order': 1,
     'short_description': 'R$ 159,90 / kg — pedido mínimo 500g.', 'description': 'Terrine de gorgonzola e peras. Apresentação a partir de 1kg (cada 1kg serve ~9 pessoas). Pedido mínimo 500g.', 'tags': ['terrine', 'gorgonzola', 'encomenda']},
    {'sku': 'IVB-TERRINE-DAMASCO', 'category_slug': 'terrines-e-pastas', 'name': 'Terrine de Gorgonzola e Damasco', 'price': Decimal('159.00'), 'featured': False, 'sort_order': 2,
     'short_description': 'R$ 159,00 / kg — pedido mínimo 500g.', 'description': 'Terrine de gorgonzola e damasco. Apresentação a partir de 1kg (cada 1kg serve ~9 pessoas). Pedido mínimo 500g.', 'tags': ['terrine', 'gorgonzola', 'encomenda']},
    {'sku': 'IVB-PASTA-FRANGO', 'category_slug': 'terrines-e-pastas', 'name': 'Pasta de Frango com Cream Cheese', 'price': Decimal('159.00'), 'featured': False, 'sort_order': 3,
     'short_description': 'R$ 159,00 / kg — pedido mínimo 500g.', 'description': 'Pasta de frango com cream cheese. Apresentação a partir de 1kg. Pedido mínimo 500g.', 'tags': ['pasta', 'frango', 'encomenda']},
    {'sku': 'IVB-QUEIJO-CREMOSO', 'category_slug': 'terrines-e-pastas', 'name': 'Queijo Cremoso e Tomatinho Confit', 'price': Decimal('139.90'), 'featured': False, 'sort_order': 4,
     'short_description': 'R$ 139,90 / kg — pedido mínimo 500g.', 'description': 'Queijo cremoso com tomatinho confit. Apresentação a partir de 1kg. Pedido mínimo 500g.', 'tags': ['queijo', 'antepasto', 'encomenda']},
    {'sku': 'IVB-PASTA-PALMITO', 'category_slug': 'terrines-e-pastas', 'name': 'Pasta de Palmito', 'price': Decimal('129.90'), 'featured': False, 'sort_order': 5,
     'short_description': 'R$ 129,90 / kg — pedido mínimo 500g.', 'description': 'Pasta de palmito. Apresentação a partir de 1kg. Pedido mínimo 500g.', 'tags': ['pasta', 'palmito', 'encomenda']},
    {'sku': 'IVB-QUEIJO-BRIE', 'category_slug': 'terrines-e-pastas', 'name': 'Queijo Brie com Compota de Morango e Frutas Vermelhas', 'price': Decimal('299.00'), 'featured': True, 'sort_order': 6,
     'short_description': 'R$ 299,00 / peça (aprox. 1,5kg).', 'description': 'Queijo brie com compota de morango e frutas vermelhas. Vendido por peça (aprox. 1,5kg).', 'tags': ['queijo', 'brie', 'encomenda']},

    # --- Tortas e Pratos (por kg) ---
    {'sku': 'IVB-TORTA-LOMBO', 'category_slug': 'tortas-e-pratos', 'name': 'Torta de Lombo Canadense', 'price': Decimal('120.00'), 'featured': False, 'sort_order': 1,
     'short_description': 'R$ 120,00 / kg — pedido mínimo 500g.', 'description': 'Torta de lombo canadense. Apresentação a partir de 1kg. Pedido mínimo 500g.', 'tags': ['torta', 'lombo', 'encomenda']},
    {'sku': 'IVB-TORTA-FRANGO', 'category_slug': 'tortas-e-pratos', 'name': 'Torta de Frango', 'price': Decimal('120.00'), 'featured': False, 'sort_order': 2,
     'short_description': 'R$ 120,00 / kg — pedido mínimo 1kg.', 'description': 'Torta de frango. Apresentação a partir de 1kg. Pedido mínimo 1kg.', 'tags': ['torta', 'frango', 'encomenda']},
    {'sku': 'IVB-LAGARTO', 'category_slug': 'tortas-e-pratos', 'name': 'Lagarto à Siciliana', 'price': Decimal('120.00'), 'featured': False, 'sort_order': 3,
     'short_description': 'R$ 120,00 / kg — pedido mínimo 500g.', 'description': 'Lagarto à siciliana. Apresentação a partir de 1kg. Pedido mínimo 500g.', 'tags': ['carne', 'lagarto', 'encomenda']},
    {'sku': 'IVB-BACALHAU', 'category_slug': 'tortas-e-pratos', 'name': 'Bacalhau', 'price': Decimal('129.90'), 'featured': False, 'sort_order': 4,
     'short_description': 'R$ 129,90 / kg — pedido mínimo 500g.', 'description': 'Bacalhau. Apresentação a partir de 1kg. Pedido mínimo 500g.', 'tags': ['bacalhau', 'encomenda']},
    {'sku': 'IVB-QUIBE', 'category_slug': 'tortas-e-pratos', 'name': 'Quibe Cru Recheado', 'price': Decimal('139.90'), 'featured': False, 'sort_order': 5,
     'short_description': 'R$ 139,90 / kg — pedido mínimo 500g.', 'description': 'Quibe cru recheado. Apresentação a partir de 1kg. Pedido mínimo 500g.', 'tags': ['quibe', 'encomenda']},
    {'sku': 'IVB-BERINGELA', 'category_slug': 'tortas-e-pratos', 'name': 'Antepasto de Berinjela', 'price': Decimal('90.00'), 'featured': False, 'sort_order': 6,
     'short_description': 'R$ 90,00 / kg — pedido mínimo 500g.', 'description': 'Antepasto de berinjela. Apresentação a partir de 1kg. Pedido mínimo 500g.', 'tags': ['antepasto', 'berinjela', 'encomenda']},

    # --- Salgados de Festa (vendidos por EMBALAGEM de 50 unidades) ---
    # Preço = embalagem com 50 un (preço unitário do menu × 50). A plataforma não
    # suporta quantidade mínima por produto, então o lote de 50 vira a unidade de venda.
    {'sku': 'IVB-PASTEL', 'category_slug': 'salgados-de-festa', 'name': 'Pastel de Feira de Carne', 'price': Decimal('80.00'), 'featured': True, 'sort_order': 1,
     'short_description': 'Embalagem com 50 unidades (R$ 1,60/un).', 'description': 'Pastel de feira recheado com carne. Vendido em embalagem com 50 unidades.', 'tags': ['salgado', 'pastel', 'frito']},
    {'sku': 'IVB-QUICHES', 'category_slug': 'salgados-de-festa', 'name': 'Quiches Variados', 'price': Decimal('150.00'), 'featured': False, 'sort_order': 2,
     'short_description': 'Embalagem com 50 unidades (R$ 3,00/un).', 'description': 'Quiches variados. Vendido em embalagem com 50 unidades.', 'tags': ['salgado', 'quiche', 'assado']},
    {'sku': 'IVB-FOLHADOS', 'category_slug': 'salgados-de-festa', 'name': 'Folhados Variados', 'price': Decimal('80.00'), 'featured': False, 'sort_order': 3,
     'short_description': 'Embalagem com 50 unidades (R$ 1,60/un).', 'description': 'Folhados variados. Vendido em embalagem com 50 unidades.', 'tags': ['salgado', 'folhado', 'assado']},
    {'sku': 'IVB-MINI-HAMBURGUER', 'category_slug': 'salgados-de-festa', 'name': 'Mini Hambúrguer', 'price': Decimal('215.00'), 'featured': True, 'sort_order': 4,
     'short_description': 'Embalagem com 50 unidades (R$ 4,30/un).', 'description': 'Mini hambúrguer. Vendido em embalagem com 50 unidades.', 'tags': ['salgado', 'mini', 'lanche']},
    {'sku': 'IVB-MINI-SANDUICHE', 'category_slug': 'salgados-de-festa', 'name': 'Mini Sanduíche', 'price': Decimal('195.00'), 'featured': False, 'sort_order': 5,
     'short_description': 'Embalagem com 50 unidades (R$ 3,90/un).', 'description': 'Mini sanduíche. Vendido em embalagem com 50 unidades.', 'tags': ['salgado', 'mini', 'lanche']},
    {'sku': 'IVB-MINI-BRIOCHE', 'category_slug': 'salgados-de-festa', 'name': 'Mini Sanduíche com Pão de Brioche', 'price': Decimal('225.00'), 'featured': False, 'sort_order': 6,
     'short_description': 'Embalagem com 50 unidades (R$ 4,50/un).', 'description': 'Mini sanduíche com pão de brioche. Vendido em embalagem com 50 unidades.', 'tags': ['salgado', 'mini', 'brioche']},
    {'sku': 'IVB-SALGADINHOS-FRITOS', 'category_slug': 'salgados-de-festa', 'name': 'Salgadinhos Fritos', 'price': Decimal('45.00'), 'featured': False, 'sort_order': 7,
     'short_description': 'Embalagem com 50 unidades (R$ 0,90/un).', 'description': 'Salgadinhos fritos sortidos. Vendido em embalagem com 50 unidades.', 'tags': ['salgado', 'frito', 'sortido']},
    {'sku': 'IVB-MINI-CROISSANT', 'category_slug': 'salgados-de-festa', 'name': 'Mini Croissant', 'price': Decimal('195.00'), 'featured': False, 'sort_order': 8,
     'short_description': 'Embalagem com 50 unidades (R$ 3,90/un).', 'description': 'Mini croissant. Vendido em embalagem com 50 unidades.', 'tags': ['salgado', 'croissant', 'assado']},
    {'sku': 'IVB-CANAPES', 'category_slug': 'salgados-de-festa', 'name': 'Canapés', 'price': Decimal('240.00'), 'featured': False, 'sort_order': 9,
     'short_description': 'Embalagem com 50 unidades (R$ 4,80/un).', 'description': 'Canapés variados. Vendido em embalagem com 50 unidades.', 'tags': ['salgado', 'canape', 'festa']},

    # --- Doces e Pães ---
    {'sku': 'IVB-BOLO-CHOCOLATE', 'category_slug': 'doces-e-paes', 'name': 'Bolo Simples de Chocolate', 'price': Decimal('70.00'), 'featured': True, 'sort_order': 1,
     'short_description': 'Aprox. 800g a 1kg.', 'description': 'Bolo simples de chocolate (aprox. 800g a 1kg).', 'tags': ['doce', 'bolo', 'chocolate']},
    {'sku': 'IVB-MINI-BOLO', 'category_slug': 'doces-e-paes', 'name': 'Mini Bolo', 'price': Decimal('4.50'), 'featured': False, 'sort_order': 2,
     'short_description': 'R$ 4,50 / unidade.', 'description': 'Mini bolo individual.', 'tags': ['doce', 'bolo', 'mini']},
    {'sku': 'IVB-CESTO-PAES', 'category_slug': 'doces-e-paes', 'name': 'Cesto de Pães', 'price': Decimal('80.00'), 'featured': False, 'sort_order': 3,
     'short_description': 'Cesto de pães variados.', 'description': 'Cesto de pães variados para acompanhar antepastos e tábuas.', 'tags': ['pao', 'cesto', 'acompanhamento']},

    # --- Bebidas ---
    {'sku': 'IVB-GUARANA-2L', 'category_slug': 'bebidas', 'name': 'Guaraná 2L', 'price': Decimal('15.00'), 'featured': False, 'sort_order': 1,
     'short_description': 'Refrigerante 2 litros.', 'description': 'Guaraná 2 litros gelado.', 'tags': ['bebida', 'refrigerante']},
    {'sku': 'IVB-SUCO-POLPA', 'category_slug': 'bebidas', 'name': 'Suco de Polpa 1L', 'price': Decimal('20.00'), 'featured': False, 'sort_order': 2,
     'short_description': 'Acerola, caju, abacaxi ou goiaba.', 'description': 'Suco natural de polpa 1 litro. Sabores: acerola, caju, abacaxi ou goiaba.', 'tags': ['bebida', 'suco', 'natural']},
    {'sku': 'IVB-COCA-2L', 'category_slug': 'bebidas', 'name': 'Coca-Cola 2L', 'price': Decimal('15.50'), 'featured': False, 'sort_order': 3,
     'short_description': 'Refrigerante 2 litros.', 'description': 'Coca-Cola 2 litros gelada.', 'tags': ['bebida', 'refrigerante']},
]


# Combos das "Sugestões" do cardápio. Modelados com preço dinâmico:
# o total = soma das opções escolhidas. `price` (override) por opção codifica
# a QUANTIDADE da sugestão quando ela difere da unidade de venda do produto
# (ex: 15 mini sanduíches, 500g de antepasto). Sem `price` → usa o preço do
# produto como está (ex: 1kg de terrine = preço/kg; 50 salgados = preço/50un).
COMBOS = [
    {
        'slug': 'sugestao-10-pessoas',
        'name': 'Sugestão para 10 Pessoas',
        'description': 'Monte sua encomenda para 10 pessoas: 1kg de terrine à sua escolha + 50 salgados (fritos ou folhados) + 15 mini sanduíches.',
        'featured': True,
        'sort_order': 1,
        'groups': [
            {'title': 'Escolha sua Terrine ou Pasta (1kg)', 'min': 1, 'max': 1, 'position': 1, 'options': [
                {'sku': 'IVB-TERRINE-PERAS'},
                {'sku': 'IVB-TERRINE-DAMASCO'},
                {'sku': 'IVB-PASTA-FRANGO'},
                {'sku': 'IVB-QUEIJO-CREMOSO'},
                {'sku': 'IVB-PASTA-PALMITO'},
            ]},
            {'title': 'Escolha os Salgados (50 unidades)', 'min': 1, 'max': 1, 'position': 2, 'options': [
                {'sku': 'IVB-SALGADINHOS-FRITOS'},  # R$ 45 (50 un)
                {'sku': 'IVB-FOLHADOS'},            # R$ 80 (50 un)
            ]},
            {'title': 'Mini Sanduíches (15 unidades)', 'min': 1, 'max': 1, 'position': 3, 'options': [
                {'sku': 'IVB-MINI-SANDUICHE', 'price': Decimal('58.50')},  # 15 × 3,90
                {'sku': 'IVB-MINI-BRIOCHE', 'price': Decimal('67.50')},    # 15 × 4,50
            ]},
        ],
    },
    {
        'slug': 'sugestao-15-pessoas',
        'name': 'Sugestão para 15 Pessoas',
        'description': 'Monte sua encomenda para 15 pessoas: 1kg de terrine à sua escolha + 50 salgados (fritos ou assados) + 1kg de torta + 500g de antepasto.',
        'featured': True,
        'sort_order': 2,
        'groups': [
            {'title': 'Escolha sua Terrine ou Pasta (1kg)', 'min': 1, 'max': 1, 'position': 1, 'options': [
                {'sku': 'IVB-TERRINE-PERAS'},
                {'sku': 'IVB-TERRINE-DAMASCO'},
                {'sku': 'IVB-PASTA-FRANGO'},
                {'sku': 'IVB-QUEIJO-CREMOSO'},
                {'sku': 'IVB-PASTA-PALMITO'},
            ]},
            {'title': 'Escolha os Salgados (50 unidades) — fritos ou assados', 'min': 1, 'max': 1, 'position': 2, 'options': [
                {'sku': 'IVB-SALGADINHOS-FRITOS'},  # fritos — R$ 45 (50 un)
                {'sku': 'IVB-FOLHADOS'},           # assados — R$ 80 (50 un)
                {'sku': 'IVB-QUICHES'},            # assados — R$ 150 (50 un)
            ]},
            {'title': 'Escolha sua Torta (1kg)', 'min': 1, 'max': 1, 'position': 3, 'options': [
                {'sku': 'IVB-TORTA-LOMBO'},   # R$ 120/kg
                {'sku': 'IVB-TORTA-FRANGO'},  # R$ 120/kg
            ]},
            {'title': 'Escolha o Antepasto (500g)', 'min': 1, 'max': 1, 'position': 4, 'options': [
                {'sku': 'IVB-BERINGELA', 'price': Decimal('45.00')},     # 0,5 × 90,00
                {'sku': 'IVB-PASTA-PALMITO', 'price': Decimal('64.95')},  # 0,5 × 129,90
                {'sku': 'IVB-BACALHAU', 'price': Decimal('64.95')},      # 0,5 × 129,90
            ]},
        ],
    },
]


# Produtos vendidos por kg que ganham variantes de peso 1kg (default) + 500g.
# product.price permanece = preço de 1kg (mantém os combos "1kg de terrine"
# corretos). 500g = metade exata (159,90/2 = 79,95). Torta de Frango fica fora
# (mínimo 1kg no menu) e Queijo Brie também (vendido por peça de ~1,5kg).
WEIGHT_VARIANT_SKUS = [
    'IVB-TERRINE-PERAS', 'IVB-TERRINE-DAMASCO', 'IVB-PASTA-FRANGO', 'IVB-QUEIJO-CREMOSO', 'IVB-PASTA-PALMITO',
    'IVB-TORTA-LOMBO', 'IVB-LAGARTO', 'IVB-BACALHAU', 'IVB-QUIBE', 'IVB-BERINGELA',
]


class Command(BaseCommand):
    help = 'Popula o cardápio da Ivoneth Banqueteria (Casa do Coffee Break) com dados reais do PDF de encomendas'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Reservado para compatibilidade (update_or_create já é idempotente)')

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('📋 Fase 1: Localizando Store (criada via painel)...')
        store = Store.objects.filter(slug=STORE_SLUG).first()
        if store is None:
            owner = (User.objects.filter(is_superuser=True).first()
                     or User.objects.filter(is_staff=True).first()
                     or User.objects.first())
            if not owner:
                self.stdout.write(self.style.ERROR('❌ Nenhum usuário encontrado para ser owner'))
                return
            store = Store.objects.create(
                slug=STORE_SLUG, name='Ivoneth Banqueteria', owner=owner,
                store_type=Store.StoreType.FOOD,
            )
            self.stdout.write(self.style.WARNING(f'⚠️  Store não existia — criada minimamente: {store.name}'))

        # Ajusta apenas campos de apoio ao catálogo, sem tocar em identidade
        # (name/phone/owner/endereço) definida no painel.
        store.store_type = Store.StoreType.FOOD
        store.currency = 'BRL'
        store.timezone = 'America/Sao_Paulo'
        store.pickup_enabled = True
        store.operating_hours = OPERATING_HOURS
        # Marca: flor magenta + teal do logo "Casa do Coffee Break".
        store.primary_color = '#9C2D54'
        store.secondary_color = '#4F8A8B'
        meta = dict(store.metadata or {})
        meta['seed_source'] = 'populate_ivoneth_banqueteria_menu'
        store.metadata = meta
        store.save()
        self.stdout.write(self.style.SUCCESS(f'🔄 Store ajustada: {store.name} ({store.slug})'))

        self.stdout.write('📋 Fase 2: Criando Categorias...')
        category_map = {}
        for cat_data in CATEGORIES:
            cat, _ = StoreCategory.objects.update_or_create(
                store=store,
                slug=cat_data['slug'],
                defaults={'name': cat_data['name'], 'description': cat_data['description'], 'sort_order': cat_data['sort_order']}
            )
            category_map[cat_data['slug']] = cat
        self.stdout.write(self.style.SUCCESS(f'✅ {len(CATEGORIES)} categoria(s) criada(s)'))

        self.stdout.write('📋 Fase 3: Criando Produtos (com otimização de imagens)...')
        optimizer = ImageOptimizer()
        optimized_count = 0
        product_by_sku = {}
        for prod_data in PRODUCTS:
            category = category_map.get(prod_data['category_slug'])
            image_url = ''
            filename = IMAGES.get(prod_data.get('sku'))
            if filename:
                image_path = Path(settings.MEDIA_ROOT) / IMG_PATH / filename
                if image_path.exists():
                    optimized_path = optimizer.optimize(str(image_path))
                    if optimized_path:
                        optimized_count += 1
                        image_url = f"{settings.MEDIA_URL.rstrip('/')}/{IMG_PATH}/{Path(optimized_path).name}"
                else:
                    self.stdout.write(self.style.WARNING(f"  ⚠️  Imagem ausente: {filename}"))

            product, _ = StoreProduct.objects.update_or_create(
                store=store,
                slug=slugify(prod_data['name']),
                defaults={
                    'category': category,
                    'name': prod_data['name'],
                    'short_description': prod_data.get('short_description', ''),
                    'description': prod_data.get('description', ''),
                    'price': prod_data['price'],
                    'sku': prod_data.get('sku', ''),
                    'featured': prod_data.get('featured', False),
                    'sort_order': prod_data['sort_order'],
                    'main_image_url': image_url,
                    'tags': prod_data.get('tags', []),
                    'track_stock': False,
                }
            )
            if prod_data.get('sku'):
                product_by_sku[prod_data['sku']] = product
        self.stdout.write(self.style.SUCCESS(f'✅ {len(PRODUCTS)} produto(s) criado(s), {optimized_count} imagem(ns) otimizada(s)'))

        self.stdout.write('📋 Fase 3b: Criando Variantes de Peso (1kg / 500g)...')
        ptype, _ = StoreProductType.objects.update_or_create(
            store=store, slug='peso',
            defaults={'name': 'Peso', 'custom_fields': [{'label': 'Peso'}], 'is_active': True},
        )
        variants_count = 0
        for sku in WEIGHT_VARIANT_SKUS:
            product = product_by_sku.get(sku)
            if not product:
                self.stdout.write(self.style.WARNING(f'  ⚠️  SKU não encontrado p/ variante: {sku}'))
                continue
            # Associa o tipo "Peso" → o label do seletor vira "Peso".
            if product.product_type_id != ptype.id:
                product.product_type = ptype
                product.save(update_fields=['product_type'])
            kg = product.price
            meia = (kg / 2).quantize(Decimal('0.01'))
            specs = [
                ('1 kg', kg, '1kg', 1),
                ('500 g', meia, '500g', 2),
            ]
            for name, price, peso, order in specs:
                StoreProductVariant.objects.update_or_create(
                    product=product, name=name,
                    defaults={'price': price, 'sku': f"{sku}-{peso.upper()}", 'options': {'peso': peso},
                              'is_active': True, 'sort_order': order},
                )
                variants_count += 1
        self.stdout.write(self.style.SUCCESS(f'✅ {variants_count} variante(s) em {len(WEIGHT_VARIANT_SKUS)} produto(s)'))

        self.stdout.write('📋 Fase 4: Criando Combos (Sugestões com escolha)...')
        sku_to_product = {p.sku: p for p in StoreProduct.objects.filter(store=store) if p.sku}
        for combo_data in COMBOS:
            combo, _ = StoreCombo.objects.update_or_create(
                store=store,
                slug=combo_data['slug'],
                defaults={
                    'name': combo_data['name'],
                    'description': combo_data.get('description', ''),
                    'price': Decimal('0.00'),  # base; total = soma das opções escolhidas
                    'dynamic_pricing': True,
                    'is_active': True,
                    'featured': combo_data.get('featured', False),
                    'track_stock': False,
                    'sort_order': combo_data.get('sort_order', 0),
                }
            )
            # Rebuild limpo dos grupos (grupos sem produto-âncora não dão para
            # casar via update_or_create — product=NULL não é único).
            combo.groups.all().delete()
            for grp in combo_data['groups']:
                group = ComboProductGroup.objects.create(
                    combo=combo,
                    product=None,
                    title=grp['title'],
                    is_required=True,
                    min_selections=grp['min'],
                    max_selections=grp['max'],
                    position=grp['position'],
                )
                for pos, opt in enumerate(grp['options'], start=1):
                    product = sku_to_product.get(opt['sku'])
                    if not product:
                        self.stdout.write(self.style.WARNING(f"  ⚠️  SKU não encontrado: {opt['sku']}"))
                        continue
                    ComboProductGroupProductOption.objects.create(
                        group=group,
                        product=product,
                        price_override=opt.get('price'),
                        position=pos,
                    )
        self.stdout.write(self.style.SUCCESS(f'✅ {len(COMBOS)} combo(s) criado(s)'))

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('✅ POPULAÇÃO CONCLUÍDA'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'Store: {store.name} ({store.slug})')
        self.stdout.write(f'Telefone: {store.phone}')
        self.stdout.write(f'Categorias: {len(CATEGORIES)}')
        self.stdout.write(f'Produtos: {len(PRODUCTS)}')
        self.stdout.write(f'Variantes de peso: {variants_count} (em {len(WEIGHT_VARIANT_SKUS)} produtos)')
        self.stdout.write(f'Combos: {len(COMBOS)}')
