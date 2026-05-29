"""
Management command to populate Cê Saladas menu.

Usage:
    python manage.py populate_ce_saladas_menu
    python manage.py populate_ce_saladas_menu --force
"""
import logging
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils.text import slugify

from apps.stores.models import Store, StoreCategory, StoreProduct

logger = logging.getLogger(__name__)
User = get_user_model()

STORE_SLUG = 'ce-saladas'
IMG_PATH = 'stores/products/ce-saladas'


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
        'slug': 'saladas',
        'name': 'Saladas Especiais',
        'description': 'Saladas frescas preparadas com ingredientes premium.',
        'sort_order': 1,
    },
]

PRODUCTS = [
    {
        'sku': 'CS-TIL',
        'category_slug': 'saladas',
        'name': 'Tilápia Suprema',
        'short_description': 'Salada com tilápia grelhada fresca.',
        'description': 'Salada equilibrada com tilápia grelhada no ponto.',
        'price': Decimal('42.90'),
        'featured': True,
        'sort_order': 1,
        'image': 'tilapia.webp',
        'tags': ['salada', 'peixe'],
        'track_stock': False,
    },
    {
        'sku': 'CS-FRA',
        'category_slug': 'saladas',
        'name': 'Especial Filé de Frango',
        'short_description': 'Salada com filé de frango grelhado.',
        'description': 'Salada com filé de frango suculento.',
        'price': Decimal('38.90'),
        'featured': True,
        'sort_order': 2,
        'image': 'especial-frango.png',
        'tags': ['salada', 'frango'],
        'track_stock': False,
    },
    {
        'sku': 'CS-LOM',
        'category_slug': 'saladas',
        'name': 'Basic Lombo',
        'short_description': 'Salada leve com lombo grelhado.',
        'description': 'Salada simples e nutritiva com lombo grelhado.',
        'price': Decimal('36.90'),
        'featured': False,
        'sort_order': 3,
        'image': 'basic-lombo.webp',
        'tags': ['salada', 'carne'],
        'track_stock': False,
    },
    {
        'sku': 'CS-SAL',
        'category_slug': 'saladas',
        'name': 'Salmão Premium',
        'short_description': 'Salada gourmet com salmão grelhado.',
        'description': 'Salada premium com salmão fresco grelhado.',
        'price': Decimal('52.90'),
        'featured': True,
        'sort_order': 4,
        'image': 'salmao.webp',
        'tags': ['salada', 'salmao', 'gourmet'],
        'track_stock': False,
    },
    {
        'sku': 'CS-ALM',
        'category_slug': 'saladas',
        'name': 'Almôndegas Premium',
        'short_description': 'Salada com almôndegas suculentas.',
        'description': 'Salada equilibrada com almôndegas caseiras.',
        'price': Decimal('40.90'),
        'featured': False,
        'sort_order': 5,
        'image': 'almondega.png',
        'tags': ['salada', 'carne'],
        'track_stock': False,
    },
    {
        'sku': 'CS-QUE',
        'category_slug': 'saladas',
        'name': 'Queridinha',
        'short_description': 'Salada leve e saudável.',
        'description': 'Salada verde abundante com ingredientes selecionados.',
        'price': Decimal('36.90'),
        'featured': False,
        'sort_order': 6,
        'image': 'queridinha.webp',
        'tags': ['salada', 'vegetariana'],
        'track_stock': False,
    },
    {
        'sku': 'CS-CAM',
        'category_slug': 'saladas',
        'name': 'Magnífico Camarão',
        'short_description': 'Salada premium com camarão grelhado.',
        'description': 'Salada sofisticada com camarão grelhado.',
        'price': Decimal('54.90'),
        'featured': True,
        'sort_order': 7,
        'image': 'camarão.webp',
        'tags': ['salada', 'camarao', 'gourmet'],
        'track_stock': False,
    },
]


class Command(BaseCommand):
    help = 'Populate Cê Saladas menu with categories and products.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-creation of products.',
        )

    def handle(self, *args, **options):
        force = options['force']

        self.stdout.write(self.style.NOTICE('\n' + '=' * 60))
        self.stdout.write(self.style.NOTICE('POPULANDO CARDAPIO CÊ SALADAS'))
        self.stdout.write(self.style.NOTICE('=' * 60 + '\n'))

        owner = User.objects.filter(is_superuser=True).first()
        store, created = Store.objects.update_or_create(
            slug=STORE_SLUG,
            defaults={
                'name': 'Cê Saladas',
                'store_type': Store.StoreType.FOOD,
                'status': Store.StoreStatus.ACTIVE,
                'description': 'Saladas frescas e saudáveis preparadas com ingredientes premium.',
                'primary_color': '#649e20',
                'secondary_color': '#f97316',
                'currency': 'BRL',
                'timezone': 'America/Sao_Paulo',
                'delivery_enabled': True,
                'pickup_enabled': True,
                'owner': owner,
            }
        )
        icon = '✨' if created else '🔄'
        self.stdout.write(f'{icon} Loja {store.name}')

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
        created_count = updated_count = 0

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

        total_active = StoreProduct.objects.filter(store=store, status=StoreProduct.ProductStatus.ACTIVE).count()

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('CARDAPIO POPULADO!'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'  Produtos criados:   {created_count}')
        self.stdout.write(f'  Produtos atualizados: {updated_count}')
        self.stdout.write(f'  Total ativos:       {total_active}')
        self.stdout.write(f'  Categorias:         {len(categories)}\n')
