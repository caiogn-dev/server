"""
Management command to populate Pastita menu (products, categories, combos).

This combines store setup with product population for a complete setup.

Usage:
    python manage.py populate_pastita_menu
    python manage.py populate_pastita_menu --force
"""
import logging
import sys
import os
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.stores.models import (
    Store, StoreCategory, StoreProduct, StoreProductType, StoreCombo
)
from apps.core.utils import build_absolute_media_url

logger = logging.getLogger(__name__)

# Configuração de URLs
def build_seed_media_url(folder: str, filename: str) -> str:
    """Resolve menu seed images from local media or an explicit base URL."""
    if not filename:
        return ''

    explicit_base = os.environ.get('STORE_SEED_MEDIA_BASE_URL', '').strip().rstrip('/')
    if explicit_base:
        return f"{explicit_base}/{folder}/{filename}"

    relative_path = Path('seeds') / folder / filename
    local_file = Path(settings.MEDIA_ROOT) / relative_path
    if local_file.exists():
        return build_absolute_media_url(
            f"{settings.MEDIA_URL.rstrip('/')}/{relative_path.as_posix()}"
        )

    return ''

# Product types
PRODUCT_TYPES = [
    {
        "name": "Rondelli",
        "slug": "rondelli",
        "description": "Massas tipo rondelli recheadas artesanalmente",
        "icon": "🍝",
    },
    {
        "name": "Molho",
        "slug": "molho",
        "description": "Molhos artesanais para acompanhar massas",
        "icon": "🥫",
    },
]

# Categories
CATEGORIES = [
    {
        "name": "Rondelli",
        "slug": "rondelli",
        "description": "Deliciosas massas de rondelli recheadas com ingredientes selecionados.",
        "sort_order": 1,
        "image": "rondelli.webp",
    },
    {
        "name": "Molhos",
        "slug": "molhos",
        "description": "Molhos artesanais preparados com receitas tradicionais.",
        "sort_order": 2,
        "image": "molhos.webp",
    },
    {
        "name": "Promoções",
        "slug": "promocoes",
        "description": "Aproveite nossas ofertas especiais e combos!",
        "sort_order": 3,
        "image": "promocoes.webp",
    },
]

# Products
PRODUCTS = [
    # Rondelli
    {
        "category_slug": "rondelli",
        "product_type_slug": "rondelli",
        "name": "Rondelli de Tomate Seco com Rúcula",
        "short_description": "Rondelli recheado com tomate seco e rúcula fresca",
        "description": "Delicioso rondelli recheado com tomates secos selecionados e rúcula fresca. Massa artesanal feita diariamente.",
        "price": Decimal("39.99"),
        "compare_at_price": Decimal("44.99"),
        "image": "tomate.webp",
        "sku": "RON-TOM-RUC-001",
        "stock_quantity": 10,
        "featured": True,
        "sort_order": 1,
        "tags": ["rondelli", "vegetariano", "destaque"],
    },
    {
        "category_slug": "rondelli",
        "product_type_slug": "rondelli",
        "name": "Rondelli de Frango com Queijo",
        "short_description": "Rondelli recheado com frango desfiado e queijo",
        "description": "Clássico rondelli de frango com queijo. Frango desfiado temperado com ervas finas.",
        "price": Decimal("39.99"),
        "image": "frango.webp",
        "sku": "RON-FRA-QUE-002",
        "stock_quantity": 10,
        "featured": False,
        "sort_order": 2,
        "tags": ["rondelli", "frango", "classico"],
    },
    {
        "category_slug": "rondelli",
        "product_type_slug": "rondelli",
        "name": "Rondelli de Presunto e Queijo",
        "short_description": "Tradicional rondelli de presunto com queijo",
        "description": "O tradicional rondelli de presunto e queijo que todo mundo ama.",
        "price": Decimal("39.99"),
        "image": "presunto-queijo.webp",
        "sku": "RON-PRE-QUE-003",
        "stock_quantity": 10,
        "featured": True,
        "sort_order": 3,
        "tags": ["rondelli", "presunto", "tradicional", "destaque"],
    },
    {
        "category_slug": "rondelli",
        "product_type_slug": "rondelli",
        "name": "Rondelli de Damasco e Nozes",
        "short_description": "Rondelli gourmet com damasco, nozes e queijo brie",
        "description": "Combinação sofisticada de damascos, nozes e queijo brie.",
        "price": Decimal("42.99"),
        "compare_at_price": Decimal("47.99"),
        "image": "damasco.webp",
        "sku": "RON-DAM-NOZ-004",
        "stock_quantity": 5,
        "featured": True,
        "sort_order": 4,
        "tags": ["rondelli", "gourmet", "destaque"],
    },
    {
        "category_slug": "rondelli",
        "product_type_slug": "rondelli",
        "name": "Rondelli de Queijo Minas",
        "short_description": "Rondelli recheado com queijo minas tradicional",
        "description": "Rondelli com queijo minas de qualidade, perfeito para quem ama queijo.",
        "price": Decimal("37.99"),
        "image": "queijo-minas.webp",
        "sku": "RON-QUE-MIN-005",
        "stock_quantity": 10,
        "featured": False,
        "sort_order": 5,
        "tags": ["rondelli", "queijo", "tradicional"],
    },
    # Molhos
    {
        "category_slug": "molhos",
        "product_type_slug": "molho",
        "name": "Molho de Tomate Artesanal",
        "short_description": "Molho de tomate caseiro com temperos frescos",
        "description": "Molho de tomate tradicional feito com tomates maduros e temperos frescos.",
        "price": Decimal("18.99"),
        "image": "molho-tomate.webp",
        "sku": "MOL-TOM-001",
        "stock_quantity": 20,
        "featured": False,
        "sort_order": 1,
        "tags": ["molho", "tomate", "tradicional"],
    },
    {
        "category_slug": "molhos",
        "product_type_slug": "molho",
        "name": "Molho Branco",
        "short_description": "Molho branco cremoso para massas",
        "description": "Molho branco aveludado, perfeito para acompanhar qualquer massa.",
        "price": Decimal("19.99"),
        "image": "molho-branco.webp",
        "sku": "MOL-BRA-002",
        "stock_quantity": 15,
        "featured": True,
        "sort_order": 2,
        "tags": ["molho", "branco", "cremoso", "destaque"],
    },
    {
        "category_slug": "molhos",
        "product_type_slug": "molho",
        "name": "Molho 4 Queijos",
        "short_description": "Molho especial com 4 tipos de queijo",
        "description": "Molho cremoso com gorgonzola, parmesão, provolone e mussarela.",
        "price": Decimal("24.99"),
        "image": "molho-4queijos.webp",
        "sku": "MOL-4QU-003",
        "stock_quantity": 10,
        "featured": True,
        "sort_order": 3,
        "tags": ["molho", "queijo", "gourmet", "destaque"],
    },
    {
        "category_slug": "molhos",
        "product_type_slug": "molho",
        "name": "Molho Bolonhesa",
        "short_description": "Molho bolonhesa tradicional com carne",
        "description": "Molho bolonhesa tradicional italiano com carne moída especial.",
        "price": Decimal("22.99"),
        "image": "molho-bolonhesa.webp",
        "sku": "MOL-BOL-004",
        "stock_quantity": 12,
        "featured": False,
        "sort_order": 4,
        "tags": ["molho", "carne", "bolonhesa"],
    },
]


class Command(BaseCommand):
    help = 'Populate Pastita menu with products, categories, and product types'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update existing products'
        )
        parser.add_argument(
            '--store-slug',
            type=str,
            default='pastita',
            help='Store slug to populate (default: pastita)'
        )

    def handle(self, *args, **options):
        force = options['force']
        store_slug = options['store_slug']

        self.stdout.write(self.style.NOTICE(f'\n{"="*60}'))
        self.stdout.write(self.style.NOTICE('POPULATING PASTITA MENU'))
        self.stdout.write(self.style.NOTICE(f'{"="*60}\n'))

        # Get the store
        try:
            store = Store.objects.get(slug=store_slug)
            self.stdout.write(f'📦 Found store: {store.name} (ID: {store.id})')
        except Store.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Store "{store_slug}" not found!'))
            self.stdout.write(self.style.WARNING('Run "python manage.py setup_pastita_store" first.'))
            return

        # Create Product Types
        self.stdout.write('\n📋 Creating Product Types...')
        product_types = {}
        for type_data in PRODUCT_TYPES:
            product_type, created = StoreProductType.objects.update_or_create(
                store=store,
                slug=type_data["slug"],
                defaults={
                    "name": type_data["name"],
                    "description": type_data["description"],
                    "icon": type_data["icon"],
                    "is_active": True,
                    "show_in_menu": True,
                }
            )
            product_types[type_data["slug"]] = product_type
            icon = "✨" if created else "🔄"
            self.stdout.write(f'  {icon} {product_type.name}')

        # Create Categories
        self.stdout.write('\n📁 Creating Categories...')
        categories = {}
        for cat_data in CATEGORIES:
            image_url = build_seed_media_url('categories', cat_data.get('image', ''))
            category, created = StoreCategory.objects.update_or_create(
                store=store,
                slug=cat_data["slug"],
                defaults={
                    "name": cat_data["name"],
                    "description": cat_data["description"],
                    "image_url": image_url,
                    "sort_order": cat_data["sort_order"],
                    "is_active": True,
                }
            )
            categories[cat_data["slug"]] = category
            icon = "✨" if created else "🔄"
            self.stdout.write(f'  {icon} {category.name}')

        # Create Products
        self.stdout.write('\n🍝 Creating Products...')
        created_count = 0
        updated_count = 0

        for prod_data in PRODUCTS:
            category = categories.get(prod_data["category_slug"])
            product_type = product_types.get(prod_data["product_type_slug"])
            slug = slugify(prod_data["name"])
            image_url = build_seed_media_url('products', prod_data.get('image', ''))

            defaults = {
                "category": category,
                "product_type": product_type,
                "name": prod_data["name"],
                "slug": slug,
                "description": prod_data["description"],
                "short_description": prod_data["short_description"],
                "sku": prod_data["sku"],
                "price": prod_data["price"],
                "compare_at_price": prod_data.get("compare_at_price"),
                "stock_quantity": prod_data.get("stock_quantity", 10),
                "status": StoreProduct.ProductStatus.ACTIVE,
                "featured": prod_data.get("featured", False),
                "sort_order": prod_data.get("sort_order", 0),
                "main_image_url": image_url,
                "tags": prod_data.get("tags", []),
            }

            # Try to find existing by SKU
            product, created = StoreProduct.objects.update_or_create(
                store=store,
                sku=prod_data["sku"],
                defaults=defaults
            )

            if created:
                created_count += 1
                icon = "✨"
            else:
                updated_count += 1
                icon = "🔄"

            promo = "🏷️ PROMO" if product.compare_at_price else ""
            featured = "⭐" if product.featured else ""
            self.stdout.write(f'  {icon} {product.name} - R$ {product.price} {promo} {featured}')

        # Summary
        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(self.style.SUCCESS('✅ MENU POPULATED SUCCESSFULLY!'))
        self.stdout.write(f'{"="*60}')

        total_product_types = StoreProductType.objects.filter(store=store).count()
        total_categories = StoreCategory.objects.filter(store=store).count()
        total_products = StoreProduct.objects.filter(store=store).count()
        total_featured = StoreProduct.objects.filter(store=store, featured=True).count()

        self.stdout.write(f'\n📊 STATISTICS:')
        self.stdout.write(f'  • Product Types: {total_product_types}')
        self.stdout.write(f'  • Categories: {total_categories}')
        self.stdout.write(f'  • Products: {total_products}')
        self.stdout.write(f'  • Featured: {total_featured}')
        self.stdout.write(f'\n  • Created: {created_count}')
        self.stdout.write(f'  • Updated: {updated_count}')
        self.stdout.write(f'\n{"="*60}')
