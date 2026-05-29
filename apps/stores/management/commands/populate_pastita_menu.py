"""
Management command to populate Pastita menu.

Usage:
    python manage.py populate_pastita_menu
    python manage.py populate_pastita_menu --force
"""
import logging
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils.text import slugify

from apps.stores.models import Store, StoreCategory, StoreProduct, StoreProductType

logger = logging.getLogger(__name__)
User = get_user_model()

STORE_SLUG = 'pastita'
IMG_PATH = 'stores/products/pastita'


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
        'slug': 'rondelli',
        'name': 'Rondelli',
        'description': 'Deliciosas massas recheadas artesanalmente.',
        'sort_order': 1,
    },
    {
        'slug': 'molhos',
        'name': 'Molhos',
        'description': 'Molhos artesanais para acompanhar suas refeições.',
        'sort_order': 2,
    },
]

PRODUCTS = [
    {
        'sku': 'PT-RON-001',
        'category_slug': 'rondelli',
        'name': 'Rondelli de Tomate Seco com Rúcula',
        'short_description': 'Rondelli recheado com tomate seco e rúcula fresca.',
        'description': 'Delicioso rondelli recheado com tomates secos e rúcula. Massa artesanal.',
        'price': Decimal('39.99'),
        'compare_at_price': Decimal('44.99'),
        'featured': True,
        'sort_order': 1,
        'image': 'rondelli-tomate.png',
        'tags': ['rondelli', 'vegetariano', 'destaque'],
        'track_stock': False,
    },
    {
        'sku': 'PT-RON-002',
        'category_slug': 'rondelli',
        'name': 'Rondelli de Frango com Queijo',
        'short_description': 'Rondelli recheado com frango desfiado e queijo.',
        'description': 'Clássico rondelli de frango com queijo. Frango temperado com ervas finas.',
        'price': Decimal('39.99'),
        'featured': False,
        'sort_order': 2,
        'image': 'rondelli-frango.png',
        'tags': ['rondelli', 'frango'],
        'track_stock': False,
    },
    {
        'sku': 'PT-RON-003',
        'category_slug': 'rondelli',
        'name': 'Rondelli de Presunto e Queijo',
        'short_description': 'Tradicional rondelli de presunto com queijo.',
        'description': 'O tradicional rondelli de presunto e queijo que todo mundo ama.',
        'price': Decimal('39.99'),
        'featured': True,
        'sort_order': 3,
        'image': 'rondelli-presunto.png',
        'tags': ['rondelli', 'presunto', 'tradicional'],
        'track_stock': False,
    },
    {
        'sku': 'PT-RON-004',
        'category_slug': 'rondelli',
        'name': 'Rondelli de Damasco e Nozes',
        'short_description': 'Rondelli gourmet com damasco, nozes e queijo brie.',
        'description': 'Combinação sofisticada de damascos, nozes e queijo brie.',
        'price': Decimal('42.99'),
        'compare_at_price': Decimal('47.99'),
        'featured': True,
        'sort_order': 4,
        'image': 'rondelli-damasco.png',
        'tags': ['rondelli', 'gourmet', 'destaque'],
        'track_stock': False,
    },
    {
        'sku': 'PT-RON-005',
        'category_slug': 'rondelli',
        'name': 'Rondelli de Queijo Minas',
        'short_description': 'Rondelli recheado com queijo minas tradicional.',
        'description': 'Rondelli com queijo minas de qualidade, perfeito para quem ama queijo.',
        'price': Decimal('37.99'),
        'featured': False,
        'sort_order': 5,
        'image': 'rondelli-queijo-minas.png',
        'tags': ['rondelli', 'queijo'],
        'track_stock': False,
    },
    {
        'sku': 'PT-MOL-001',
        'category_slug': 'molhos',
        'name': 'Molho de Tomate Artesanal',
        'short_description': 'Molho de tomate caseiro com temperos frescos.',
        'description': 'Molho de tomate tradicional com tomates maduros e temperos frescos.',
        'price': Decimal('18.99'),
        'featured': False,
        'sort_order': 1,
        'image': 'molho-tomate.png',
        'tags': ['molho', 'tomate'],
        'track_stock': False,
    },
    {
        'sku': 'PT-MOL-002',
        'category_slug': 'molhos',
        'name': 'Molho Branco',
        'short_description': 'Molho branco cremoso para massas.',
        'description': 'Molho branco aveludado, perfeito para qualquer massa.',
        'price': Decimal('19.99'),
        'featured': True,
        'sort_order': 2,
        'image': 'molho-branco.png',
        'tags': ['molho', 'branco', 'cremoso'],
        'track_stock': False,
    },
    {
        'sku': 'PT-MOL-003',
        'category_slug': 'molhos',
        'name': 'Molho 4 Queijos',
        'short_description': 'Molho especial com 4 tipos de queijo.',
        'description': 'Molho cremoso com gorgonzola, parmesão, provolone e mussarela.',
        'price': Decimal('24.99'),
        'featured': True,
        'sort_order': 3,
        'image': 'molho-4-queijos.png',
        'tags': ['molho', 'queijo', 'gourmet'],
        'track_stock': False,
    },
    {
        'sku': 'PT-MOL-004',
        'category_slug': 'molhos',
        'name': 'Molho Bolonhesa',
        'short_description': 'Molho bolonhesa tradicional com carne.',
        'description': 'Molho bolonhesa italiano com carne moída temperada.',
        'price': Decimal('22.99'),
        'featured': False,
        'sort_order': 4,
        'image': 'molho-bolonhesa.png',
        'tags': ['molho', 'carne'],
        'track_stock': False,
    },
]


class Command(BaseCommand):
    help = 'Populate Pastita menu with categories and products.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-creation of products.',
        )

    def handle(self, *args, **options):
        force = options['force']

        self.stdout.write(self.style.NOTICE('\n' + '=' * 60))
        self.stdout.write(self.style.NOTICE('POPULANDO CARDAPIO PASTITA'))
        self.stdout.write(self.style.NOTICE('=' * 60 + '\n'))

        owner = User.objects.filter(is_superuser=True).first()
        store, created = Store.objects.update_or_create(
            slug=STORE_SLUG,
            defaults={
                'name': 'Pastita',
                'store_type': Store.StoreType.FOOD,
                'status': Store.StoreStatus.ACTIVE,
                'description': 'Rondelli artesanal e molhos especiais.',
                'primary_color': '#1e40af',
                'secondary_color': '#3b82f6',
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
                'compare_at_price': prod.get('compare_at_price'),
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
