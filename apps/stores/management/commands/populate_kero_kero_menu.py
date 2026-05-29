"""
Management command to populate Kero Kero Salgadinhos menu.

Usage:
    python manage.py populate_kero_kero_menu
    python manage.py populate_kero_kero_menu --force
    python manage.py populate_kero_kero_menu --deactivate-legacy
"""
import logging
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils.text import slugify

from apps.stores.models import Store, StoreCategory, StoreProduct, StoreProductVariant

logger = logging.getLogger(__name__)
User = get_user_model()

STORE_SLUG = 'kero-kero'
IMG_PATH = 'stores/products/kero-kero'


def _img(filename):
    """Return relative media URL if file exists in container, else empty string."""
    if not filename:
        return ''
    local = Path(settings.MEDIA_ROOT) / IMG_PATH / filename
    if local.exists():
        media_url = settings.MEDIA_URL.rstrip('/')
        return f"{media_url}/{IMG_PATH}/{filename}"
    return ''


CATEGORIES = [
    {
        'slug': 'mais-pedidos',
        'name': 'Mais Pedidos',
        'description': 'Os produtos mais pedidos da Kero Kero.',
        'sort_order': 1,
    },
    {
        'slug': 'combos-com-refri',
        'name': 'Combos com Refri',
        'description': 'Salgadinhos + refrigerante pelo melhor preço.',
        'sort_order': 2,
    },
    {
        'slug': 'salgadinhos-fritos',
        'name': 'Salgadinhos Fritos',
        'description': 'Sortidos ou no sabor que você preferir.',
        'sort_order': 3,
    },
    {
        'slug': 'kit-festa',
        'name': 'Kit Festa',
        'description': 'Tudo para a sua festa em um só pedido.',
        'sort_order': 4,
    },
    {
        'slug': 'congelados',
        'name': 'Congelados',
        'description': 'Salgadinhos congelados para fritar em casa.',
        'sort_order': 5,
    },
    {
        'slug': 'bolos-e-doces',
        'name': 'Bolos e Doces',
        'description': 'Bolos vulcão e docinhos artesanais.',
        'sort_order': 6,
    },
    {
        'slug': 'lanches-e-massas',
        'name': 'Lanches e Massas',
        'description': 'Mini pizzas, pastéis, pão de queijo e sanduíches.',
        'sort_order': 7,
    },
    {
        'slug': 'bebidas',
        'name': 'Bebidas',
        'description': 'Refrigerantes gelados para acompanhar.',
        'sort_order': 8,
    },
]

PRODUCTS = [
    {
        'sku': 'KK-COMBO-25',
        'category_slug': 'mais-pedidos',
        'name': 'Combo 25 Salgadinhos Fritos',
        'short_description': '25 fritos sortidos por preço promocional.',
        'description': '25 salgadinhos fritos sortidos conforme disponibilidade.',
        'price': Decimal('19.90'),
        'featured': True,
        'sort_order': 1,
        'image': 'combo-25-fritos.png',
        'tags': ['fritos', 'entrada', 'promocao'],
        'track_stock': False,
    },
    {
        'sku': 'KK-MIX',
        'category_slug': 'salgadinhos-fritos',
        'name': 'Mix Sortido de Salgadinhos Fritos',
        'short_description': 'Sortidos conforme disponibilidade.',
        'description': 'Mix de salgadinhos fritos sortidos.',
        'price': Decimal('19.90'),
        'featured': True,
        'sort_order': 1,
        'image': 'fritos-sortidos-50.png',
        'tags': ['fritos', 'sortido', 'mais-pedido'],
        'track_stock': False,
        'variants': [
            {'name': '25 unidades', 'sku': 'KK-MIX-025', 'price': Decimal('19.90'), 'options': {'quantidade': '25 unidades'}, 'sort_order': 1},
            {'name': '50 unidades', 'sku': 'KK-MIX-050', 'price': Decimal('35.00'), 'options': {'quantidade': '50 unidades'}, 'sort_order': 2},
            {'name': '100 unidades', 'sku': 'KK-MIX-100', 'price': Decimal('65.00'), 'options': {'quantidade': '100 unidades'}, 'sort_order': 3},
        ],
    },
    {
        'sku': 'KK-KIT-FESTA',
        'category_slug': 'kit-festa',
        'name': 'Kit Festa',
        'short_description': 'Salgado, doce, refri e bolo. Tudo para a sua festa.',
        'description': 'Kit completo: 50 salgadinhos fritos, 25 docinhos, 1 refri 2L e 1 bolo.',
        'price': Decimal('199.90'),
        'featured': True,
        'sort_order': 1,
        'image': 'kit-festa.png',
        'tags': ['kit', 'festa', 'completo'],
        'track_stock': False,
    },
    {
        'sku': 'KK-CONG-110',
        'category_slug': 'congelados',
        'name': '110 Salgadinhos Congelados',
        'short_description': 'Salgadinhos congelados para fritar em casa.',
        'description': '110 salgadinhos congelados sortidos para fritura.',
        'price': Decimal('55.00'),
        'featured': False,
        'sort_order': 1,
        'image': 'congelados-110.png',
        'tags': ['congelados', 'fritar-em-casa'],
        'track_stock': False,
    },
    {
        'sku': 'KK-BOLO-VUL',
        'category_slug': 'bolos-e-doces',
        'name': 'Bolo Vulcão',
        'short_description': 'Bolo vulcão cremoso.',
        'description': 'Bolo vulcão individual com cobertura cremosa.',
        'price': Decimal('35.00'),
        'featured': False,
        'sort_order': 1,
        'image': 'bolo-vulcao.png',
        'tags': ['bolo', 'doce', 'vulcao'],
        'track_stock': False,
    },
    {
        'sku': 'KK-PIZZA',
        'category_slug': 'lanches-e-massas',
        'name': 'Mini Pizza Mista',
        'short_description': 'Mini pizzas sortidas.',
        'description': 'Mini pizzas assadas com recheios variados.',
        'price': Decimal('49.90'),
        'featured': False,
        'sort_order': 1,
        'image': 'mini-pizza.png',
        'tags': ['pizza', 'mini', 'assado'],
        'track_stock': False,
    },
    {
        'sku': 'KK-PASTEIS-30',
        'category_slug': 'lanches-e-massas',
        'name': '30 Pastéis',
        'short_description': '30 pastéis pequenos crocantes.',
        'description': 'Pastéis fritos pequenos, crocantes.',
        'price': Decimal('51.90'),
        'featured': False,
        'sort_order': 2,
        'image': 'pasteis-30.png',
        'tags': ['pastel', 'frito'],
        'track_stock': False,
    },
    {
        'sku': 'KK-PQ-30',
        'category_slug': 'lanches-e-massas',
        'name': '30 Pães de Queijo',
        'short_description': '30 pães de queijo tradicionais.',
        'description': 'Pão de queijo tradicional, macio por dentro.',
        'price': Decimal('44.90'),
        'featured': False,
        'sort_order': 3,
        'image': 'pao-de-queijo-30.png',
        'tags': ['pao-de-queijo'],
        'track_stock': False,
    },
    {
        'sku': 'KK-SANDUICHE-20',
        'category_slug': 'lanches-e-massas',
        'name': '20 Mini Sanduíches',
        'short_description': '20 mini sanduíches para festa.',
        'description': 'Mini sanduíches macios, prontos para servir.',
        'price': Decimal('78.00'),
        'featured': False,
        'sort_order': 4,
        'image': 'mini-sanduiche-20.png',
        'tags': ['sanduiche', 'mini'],
        'track_stock': False,
    },
    {
        'sku': 'KK-PQ-REC-20',
        'category_slug': 'lanches-e-massas',
        'name': '20 Pães de Queijo Recheados',
        'short_description': '20 pães de queijo recheados.',
        'description': 'Pão de queijo recheado, escolha o sabor.',
        'price': Decimal('54.00'),
        'featured': False,
        'sort_order': 5,
        'image': 'pao-de-queijo-recheado-20.png',
        'tags': ['pao-de-queijo', 'recheado'],
        'track_stock': False,
    },
    {
        'sku': 'KK-REFRI-2L',
        'category_slug': 'bebidas',
        'name': 'Refrigerante 2L',
        'short_description': 'Refrigerante 2L gelado.',
        'description': 'Refrigerante 2L gelado, conforme disponibilidade.',
        'price': Decimal('15.00'),
        'featured': False,
        'sort_order': 1,
        'image': 'refrigerante-2l.png',
        'tags': ['bebida', 'refri'],
        'track_stock': False,
    },
]


class Command(BaseCommand):
    help = 'Populate Kero Kero Salgadinhos menu with categories and products.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-creation of products.',
        )
        parser.add_argument(
            '--deactivate-legacy',
            action='store_true',
            help='Deactivate products not in this catalog.',
        )

    def handle(self, *args, **options):
        force = options['force']
        deactivate_legacy = options['deactivate_legacy']

        self.stdout.write(self.style.NOTICE('\n' + '=' * 60))
        self.stdout.write(self.style.NOTICE('POPULANDO CARDAPIO KERO KERO'))
        self.stdout.write(self.style.NOTICE('=' * 60 + '\n'))

        owner = User.objects.filter(is_superuser=True).first()
        store, created = Store.objects.update_or_create(
            slug=STORE_SLUG,
            defaults={
                'name': 'Kero Kero Salgadinhos',
                'store_type': Store.StoreType.FOOD,
                'status': Store.StoreStatus.ACTIVE,
                'description': 'Salgadinhos fritos, congelados, kits festa e muito mais.',
                'primary_color': '#FF6B00',
                'secondary_color': '#FFF3E0',
                'currency': 'BRL',
                'timezone': 'America/Sao_Paulo',
                'delivery_enabled': True,
                'pickup_enabled': True,
                'owner': owner,
            }
        )
        icon = '✨' if created else '🔄'
        self.stdout.write(f'{icon} Loja {store.name}')

        if deactivate_legacy:
            new_skus = {p['sku'] for p in PRODUCTS}
            legacy_qs = StoreProduct.objects.filter(store=store, status=StoreProduct.ProductStatus.ACTIVE).exclude(sku__in=new_skus)
            if legacy_qs.count():
                legacy_qs.update(status=StoreProduct.ProductStatus.INACTIVE)

        self.stdout.write('\nCriando categorias...')
        categories = {}
        for cat in CATEGORIES:
            obj, created = StoreCategory.objects.update_or_create(
                store=store,
                slug=cat['slug'],
                defaults={
                    'name': cat['name'],
                    'description': cat['description'],
                    'sort_order': cat['sort_order'],
                    'is_active': True,
                },
            )
            categories[cat['slug']] = obj
            icon = '✨' if created else '🔄'
            self.stdout.write(f'  {icon} {cat["name"]}')

        self.stdout.write('\nCriando produtos...')
        created_count = updated_count = variant_count = 0

        for prod in PRODUCTS:
            category = categories.get(prod['category_slug'])
            image_url = _img(prod.get('image', ''))

            defaults = {
                'category': category,
                'name': prod['name'],
                'slug': slugify(prod['name']),
                'short_description': prod.get('short_description', ''),
                'description': prod.get('description', ''),
                'price': prod['price'],
                'status': StoreProduct.ProductStatus.ACTIVE,
                'featured': prod.get('featured', False),
                'sort_order': prod.get('sort_order', 0),
                'main_image_url': image_url,
                'tags': prod.get('tags', []),
                'track_stock': prod.get('track_stock', False),
                'stock_quantity': 0,
            }

            slug = defaults['slug']
            try:
                product = StoreProduct.objects.get(store=store, slug=slug)
                for k, v in defaults.items():
                    setattr(product, k, v)
                product.sku = prod['sku']
                product.save()
                created = False
            except StoreProduct.DoesNotExist:
                product = StoreProduct.objects.create(store=store, sku=prod['sku'], **defaults)
                created = True

            if created:
                created_count += 1
                icon = '✨'
            else:
                updated_count += 1
                icon = '🔄'

            self.stdout.write(f'  {icon} {product.name}')

            variants_data = prod.get('variants', [])
            if variants_data:
                if force:
                    product.variants.all().delete()

                for vdata in variants_data:
                    variant, vcreated = StoreProductVariant.objects.update_or_create(
                        product=product,
                        sku=vdata['sku'],
                        defaults={
                            'name': vdata['name'],
                            'price': vdata['price'],
                            'options': vdata.get('options', {}),
                            'sort_order': vdata.get('sort_order', 0),
                            'is_active': True,
                            'stock_quantity': 0,
                        },
                    )
                    variant_count += 1
                    vicon = '✨' if vcreated else '·'
                    self.stdout.write(f'     {vicon} {variant.name}')

        total_active = StoreProduct.objects.filter(store=store, status=StoreProduct.ProductStatus.ACTIVE).count()

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('CARDAPIO POPULADO!'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'  Produtos criados:   {created_count}')
        self.stdout.write(f'  Produtos atualizados: {updated_count}')
        self.stdout.write(f'  Variantes:          {variant_count}')
        self.stdout.write(f'  Total ativos:       {total_active}')
        self.stdout.write(f'  Categorias:         {len(categories)}\n')
