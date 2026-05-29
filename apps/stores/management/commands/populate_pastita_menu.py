"""
Management command to populate Pastita Massas menu (consolidated from 3 scripts).

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
from django.db import transaction

from apps.stores.models import Store, StoreCategory, StoreProduct, StoreProductType, StoreDeliveryZone
from apps.stores.utils.image_optimizer import ImageOptimizer

logger = logging.getLogger(__name__)
User = get_user_model()

STORE_SLUG = 'pastita'
IMG_PATH = 'stores/products/pastita'

SHARED_LOCATION = {
    "latitude": Decimal("-10.1852683"),
    "longitude": Decimal("-48.3036368"),
    "address": "Q. 112 Sul, Rua Sr 01, 2 - Palmas, Tocantins",
    "city": "Palmas",
    "state": "TO",
    "zip_code": "72000-000",
    "country": "BR",
}

SHARED_OPERATING_HOURS = {
    "monday": {"open": "08:00", "close": "17:00"},
    "tuesday": {"open": "08:00", "close": "17:00"},
    "wednesday": {"open": "08:00", "close": "17:00"},
    "thursday": {"open": "08:00", "close": "17:00"},
    "friday": {"open": "08:00", "close": "17:00"},
    "saturday": {"open": "08:00", "close": "17:00"},
    "sunday": {"open": "00:00", "close": "00:00"},
}

DELIVERY_ZONES = [
    {"min_km": 0, "max_km": 2, "fee": Decimal("7.00"), "sort": 1},
    {"min_km": Decimal("2.1"), "max_km": 3, "fee": Decimal("8.00"), "sort": 2},
    {"min_km": Decimal("3.1"), "max_km": 5, "fee": Decimal("9.00"), "sort": 3},
    {"min_km": Decimal("5.1"), "max_km": 6, "fee": Decimal("10.00"), "sort": 4},
    {"min_km": Decimal("6.1"), "max_km": Decimal("6.9"), "fee": Decimal("11.00"), "sort": 5},
    {"min_km": 7, "max_km": Decimal("7.9"), "fee": Decimal("12.00"), "sort": 6},
    {"min_km": 8, "max_km": 8, "fee": Decimal("13.00"), "sort": 7},
    {"min_km": 9, "max_km": 9, "fee": Decimal("14.00"), "sort": 8},
    {"min_km": 10, "max_km": 10, "fee": Decimal("15.00"), "sort": 9},
    {"min_km": 11, "max_km": 11, "fee": Decimal("16.00"), "sort": 10},
    {"min_km": 12, "max_km": 12, "fee": Decimal("18.00"), "sort": 11},
    {"min_km": 13, "max_km": 13, "fee": Decimal("20.00"), "sort": 12},
    {"min_km": 14, "max_km": 14, "fee": Decimal("22.00"), "sort": 13},
    {"min_km": 15, "max_km": 15, "fee": Decimal("24.00"), "sort": 14},
    {"min_km": 16, "max_km": 16, "fee": Decimal("26.00"), "sort": 15},
    {"min_km": 17, "max_km": 17, "fee": Decimal("28.00"), "sort": 16},
]

PRODUCT_TYPES = [
    {"name": "Rondelli", "slug": "rondelli", "description": "Massas tipo rondelli recheadas artesanalmente", "icon": "🍝"},
    {"name": "Molho", "slug": "molho", "description": "Molhos artesanais para acompanhar massas", "icon": "🥫"},
]

CATEGORIES = [
    {"slug": "rondelli", "name": "Rondelli", "description": "Deliciosas massas de rondelli recheadas com ingredientes selecionados.", "sort_order": 1},
    {"slug": "molhos", "name": "Molhos", "description": "Molhos artesanais preparados com receitas tradicionais.", "sort_order": 2},
    {"slug": "promocoes", "name": "Promoções", "description": "Aproveite nossas ofertas especiais e combos!", "sort_order": 3},
]

PRODUCTS = [
    {"category_slug": "rondelli", "product_type_slug": "rondelli", "name": "Rondelli de Tomate Seco com Rúcula", "short_description": "Rondelli recheado com tomate seco e rúcula fresca", "description": "Delicioso rondelli recheado com tomates secos selecionados e rúcula fresca.", "price": Decimal("39.99"), "compare_at_price": Decimal("44.99"), "cost_price": Decimal("18.00"), "sku": "RON-TOM-RUC-001", "barcode": "7891234567891", "stock_quantity": 10, "featured": True, "sort_order": 1, "image": "tomate.webp", "tags": ["rondelli", "tomate-seco", "rucula", "vegetariano"]},
    {"category_slug": "rondelli", "product_type_slug": "rondelli", "name": "Rondelli de Frango com Queijo", "short_description": "Rondelli recheado com frango desfiado e queijo", "description": "Clássico rondelli de frango com queijo.", "price": Decimal("39.99"), "cost_price": Decimal("17.50"), "sku": "RON-FRA-QUE-002", "barcode": "7891234567892", "stock_quantity": 10, "featured": False, "sort_order": 2, "image": "frango.webp", "tags": ["rondelli", "frango", "queijo"]},
]


class Command(BaseCommand):
    help = 'Popula o cardápio da Pastita Massas com dados reais'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Força sobrescrita de dados existentes')

    @transaction.atomic
    def handle(self, *args, **options):
        force = options.get('force', False)
        optimizer = ImageOptimizer()

        owner = User.objects.filter(is_superuser=True).first()
        if not owner:
            owner = User.objects.filter(is_staff=True).first()
        if not owner:
            owner = User.objects.first()
        if not owner:
            self.stdout.write(self.style.ERROR('❌ Nenhum usuário encontrado'))
            return

        self.stdout.write('📋 Fase 1: Criando Store...')
        store, created = Store.objects.update_or_create(
            slug=STORE_SLUG,
            defaults={
                'name': 'Pastita',
                'store_type': Store.StoreType.FOOD,
                'status': Store.StoreStatus.ACTIVE,
                'email': 'pastita.oficial@gmail.com',
                'phone': '63991172166',
                'whatsapp_number': '63991172166',
                'primary_color': '#FF9800',
                'secondary_color': '#FFC107',
                'currency': 'BRL',
                'timezone': 'America/Sao_Paulo',
                'tax_rate': Decimal('0.00'),
                'delivery_enabled': True,
                'pickup_enabled': True,
                'min_order_value': Decimal('0.00'),
                'default_delivery_fee': Decimal('10.00'),
                'free_delivery_threshold': Decimal('100.00'),
                'operating_hours': SHARED_OPERATING_HOURS,
                'owner': owner,
                **SHARED_LOCATION,
                'metadata': {'seed_source': 'populate_pastita_menu'},
            }
        )
        status = '✅ Criada' if created else '🔄 Atualizada'
        self.stdout.write(self.style.SUCCESS(f'{status}: {store.name}'))

        self.stdout.write('📋 Fase 2: Criando Tipos de Produtos...')
        type_map = {}
        for type_data in PRODUCT_TYPES:
            pt, _ = StoreProductType.objects.update_or_create(
                store=store,
                slug=type_data['slug'],
                defaults={'name': type_data['name'], 'description': type_data['description'], 'icon': type_data['icon']}
            )
            type_map[type_data['slug']] = pt
        self.stdout.write(self.style.SUCCESS(f'✅ {len(PRODUCT_TYPES)} tipo(s) de produto criado(s)'))

        self.stdout.write('📋 Fase 3: Criando Categorias...')
        category_map = {}
        for cat_data in CATEGORIES:
            cat, _ = StoreCategory.objects.update_or_create(
                store=store,
                slug=cat_data['slug'],
                defaults={'name': cat_data['name'], 'description': cat_data['description'], 'sort_order': cat_data['sort_order']}
            )
            category_map[cat_data['slug']] = cat
        self.stdout.write(self.style.SUCCESS(f'✅ {len(CATEGORIES)} categoria(s) criada(s)'))

        self.stdout.write('📋 Fase 4: Criando Produtos com otimização de imagens...')
        optimized_count = 0
        for prod_data in PRODUCTS:
            category = category_map.get(prod_data['category_slug'])
            product_type = type_map.get(prod_data['product_type_slug'])
            image_url = ''
            if prod_data.get('image'):
                image_path = Path(settings.MEDIA_ROOT) / IMG_PATH / prod_data['image']
                if image_path.exists():
                    optimized_path = optimizer.optimize(str(image_path))
                    if optimized_path:
                        optimized_count += 1
                        image_url = f"{settings.MEDIA_URL.rstrip('/')}/{IMG_PATH}/{Path(optimized_path).name}"

            StoreProduct.objects.update_or_create(
                store=store,
                slug=slugify(prod_data['name']),
                defaults={
                    'category': category,
                    'product_type': product_type,
                    'name': prod_data['name'],
                    'short_description': prod_data.get('short_description', ''),
                    'description': prod_data.get('description', ''),
                    'price': prod_data['price'],
                    'compare_at_price': prod_data.get('compare_at_price'),
                    'cost_price': prod_data.get('cost_price'),
                    'sku': prod_data.get('sku', ''),
                    'barcode': prod_data.get('barcode', ''),
                    'stock_quantity': prod_data.get('stock_quantity', 0),
                    'featured': prod_data.get('featured', False),
                    'sort_order': prod_data['sort_order'],
                    'main_image_url': image_url,
                    'tags': prod_data.get('tags', []),
                    'track_stock': prod_data.get('track_stock', False),
                }
            )
        self.stdout.write(self.style.SUCCESS(f'✅ {len(PRODUCTS)} produto(s) criado(s), {optimized_count} imagem(ns) otimizada(s)'))

        self.stdout.write('📋 Fase 5: Criando Zonas de Entrega...')
        zones_created = 0
        for zone_data in DELIVERY_ZONES:
            StoreDeliveryZone.objects.update_or_create(
                store=store,
                zone_type='distance_band',
                distance_band=f"{zone_data['min_km']}-{zone_data['max_km']}",
                defaults={'name': f"{zone_data['min_km']}-{zone_data['max_km']}km", 'min_km': zone_data['min_km'], 'max_km': zone_data['max_km'], 'delivery_fee': zone_data['fee'], 'is_active': True, 'sort_order': zone_data['sort']}
            )
            zones_created += 1
        self.stdout.write(self.style.SUCCESS(f'✅ {zones_created} zona(s) de entrega criada(s)'))

        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('✅ POPULAÇÃO CONCLUÍDA'))
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(f'Store: {store.name} ({store.slug})')
        self.stdout.write(f'Email: {store.email}')
        self.stdout.write(f'Categorias: {len(CATEGORIES)}')
        self.stdout.write(f'Produtos: {len(PRODUCTS)}')
        self.stdout.write(f'Zonas de Entrega: {zones_created}')
        self.stdout.write(f'Imagens otimizadas: {optimized_count}')
