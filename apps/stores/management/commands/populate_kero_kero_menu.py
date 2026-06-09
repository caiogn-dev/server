"""
Management command to populate Kero Kero Salgadinhos menu (updated with optimization).

Usage:
    python manage.py populate_kero_kero_menu
    python manage.py populate_kero_kero_menu --force
"""
import logging
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.db import transaction

from apps.stores.models import Store, StoreCategory, StoreProduct, StoreDeliveryZone
from apps.stores.utils.image_optimizer import ImageOptimizer

logger = logging.getLogger(__name__)
User = get_user_model()

STORE_SLUG = 'kero-kero'
IMG_PATH = 'stores/products/kero-kero'

SHARED_LOCATION = {"latitude": Decimal("-10.1852683"), "longitude": Decimal("-48.3036368"), "address": "Q. 112 Sul, Rua Sr 01, 2 - Palmas, Tocantins", "city": "Palmas", "state": "TO", "zip_code": "72000-000", "country": "BR"}
SHARED_OPERATING_HOURS = {"monday": {"open": "08:00", "close": "17:00"}, "tuesday": {"open": "08:00", "close": "17:00"}, "wednesday": {"open": "08:00", "close": "17:00"}, "thursday": {"open": "08:00", "close": "17:00"}, "friday": {"open": "08:00", "close": "17:00"}, "saturday": {"open": "08:00", "close": "17:00"}, "sunday": {"open": "00:00", "close": "00:00"}}
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

CATEGORIES = [
    {'slug': 'mais-pedidos', 'name': 'Mais Pedidos', 'description': 'Os produtos mais pedidos da Kero Kero.', 'sort_order': 1},
    {'slug': 'combos-com-refri', 'name': 'Combos com Refri', 'description': 'Salgadinhos + refrigerante pelo melhor preço.', 'sort_order': 2},
    {'slug': 'salgadinhos-fritos', 'name': 'Salgadinhos Fritos', 'description': 'Sortidos ou no sabor que você preferir.', 'sort_order': 3},
    {'slug': 'kit-festa', 'name': 'Kit Festa', 'description': 'Tudo para a sua festa em um só pedido.', 'sort_order': 4},
    {'slug': 'congelados', 'name': 'Congelados', 'description': 'Salgadinhos congelados para fritar em casa.', 'sort_order': 5},
    {'slug': 'bolos-e-doces', 'name': 'Bolos e Doces', 'description': 'Bolos vulcão e docinhos artesanais.', 'sort_order': 6},
    {'slug': 'lanches-e-massas', 'name': 'Lanches e Massas', 'description': 'Mini pizzas, pastéis, pão de queijo e sanduíches.', 'sort_order': 7},
    {'slug': 'bebidas', 'name': 'Bebidas', 'description': 'Refrigerantes gelados para acompanhar.', 'sort_order': 8},
]

PRODUCTS = [
    {'sku': 'KK-COMBO-25', 'category_slug': 'mais-pedidos', 'name': 'Combo 25 Salgadinhos Fritos', 'short_description': '25 fritos sortidos por preço promocional.', 'description': '25 salgadinhos fritos sortidos conforme disponibilidade.', 'price': Decimal('19.90'), 'featured': True, 'sort_order': 1, 'image': 'combo-25-fritos.png', 'tags': ['fritos', 'entrada', 'promocao'], 'track_stock': False},
    {'sku': 'KK-MIX', 'category_slug': 'salgadinhos-fritos', 'name': 'Mix Sortido de Salgadinhos Fritos', 'short_description': 'Sortidos conforme disponibilidade.', 'description': 'Mix de salgadinhos fritos sortidos.', 'price': Decimal('19.90'), 'featured': True, 'sort_order': 1, 'image': 'fritos-sortidos-50.png', 'tags': ['fritos', 'sortido', 'mais-pedido'], 'track_stock': False},
    {'sku': 'KK-KIT-FESTA', 'category_slug': 'kit-festa', 'name': 'Kit Festa', 'short_description': 'Salgado, doce, refri e bolo. Tudo para a sua festa.', 'description': 'Kit completo: 50 salgadinhos fritos, 25 docinhos, 1 refri 2L e 1 bolo.', 'price': Decimal('199.90'), 'featured': True, 'sort_order': 1, 'image': 'kit-festa.png', 'tags': ['kit', 'festa', 'completo'], 'track_stock': False},
    {'sku': 'KK-CONG-110', 'category_slug': 'congelados', 'name': '110 Salgadinhos Congelados', 'short_description': 'Salgadinhos congelados para fritar em casa.', 'description': '110 salgadinhos congelados sortidos para fritura.', 'price': Decimal('55.00'), 'featured': False, 'sort_order': 1, 'image': 'congelados-110.png', 'tags': ['congelados', 'fritar-em-casa'], 'track_stock': False},
    {'sku': 'KK-BOLO-VUL', 'category_slug': 'bolos-e-doces', 'name': 'Bolo Vulcão', 'short_description': 'Bolo vulcão com calda de chocolate.', 'description': 'Delicioso bolo vulcão com calda de chocolate que derrete na boca.', 'price': Decimal('45.00'), 'featured': True, 'sort_order': 1, 'image': 'bolo-vulcao.png', 'tags': ['bolo', 'chocolate', 'destaque'], 'track_stock': False},
    {'sku': 'KK-MINI-PIZZA', 'category_slug': 'lanches-e-massas', 'name': 'Mini Pizzas Sortidas', 'short_description': 'Mini pizzas assadas no forno de barro.', 'description': '12 mini pizzas sortidas assadas no forno de barro.', 'price': Decimal('35.00'), 'featured': False, 'sort_order': 1, 'image': 'mini-pizza.png', 'tags': ['pizza', 'lanche'], 'track_stock': False},
    {'sku': 'KK-REFRI-2L', 'category_slug': 'bebidas', 'name': 'Refrigerante 2L', 'short_description': 'Refrigerante gelado 2 litros.', 'description': 'Refrigerante 2 litros bem gelado para acompanhar seu pedido.', 'price': Decimal('9.90'), 'featured': False, 'sort_order': 1, 'image': 'refrigerante-2l.png', 'tags': ['bebida', 'refri'], 'track_stock': False},
    {'sku': 'KK-PAO-QUEIJO', 'category_slug': 'lanches-e-massas', 'name': 'Pão de Queijo Assado', 'short_description': 'Pão de queijo quente assado no forno.', 'description': 'Pão de queijo quente acabadinho do forno, macio e saboroso.', 'price': Decimal('15.00'), 'featured': False, 'sort_order': 2, 'image': 'pao-de-queijo-30.png', 'tags': ['pao', 'queijo', 'lanche'], 'track_stock': False},
    {'sku': 'KK-PASTEL-CARNE', 'category_slug': 'lanches-e-massas', 'name': 'Pastel de Carne', 'short_description': 'Pastel frito recheado com carne.', 'description': 'Pastel frito crocante recheado com carne moída temperada.', 'price': Decimal('12.00'), 'featured': False, 'sort_order': 3, 'image': 'pasteis-30.png', 'tags': ['pastel', 'carne'], 'track_stock': False},
    {'sku': 'KK-COMBO-REFRI', 'category_slug': 'combos-com-refri', 'name': 'Combo 50 Fritos + Refri 2L', 'short_description': '50 salgadinhos fritos + 1 refrigerante 2L.', 'description': '50 salgadinhos fritos sortidos + 1 refrigerante 2 litros gelado.', 'price': Decimal('59.90'), 'featured': True, 'sort_order': 1, 'image': 'combo-fritos-refri-lata.png', 'tags': ['combo', 'promo', 'refri'], 'track_stock': False},
    {'sku': 'KK-DOCINHO', 'category_slug': 'bolos-e-doces', 'name': 'Docinhos Sortidos', 'short_description': 'Caixa com 12 docinhos sortidos.', 'description': 'Caixa com 12 docinhos variados: brigadeiro, beijinho, romeu e julieta.', 'price': Decimal('28.00'), 'featured': False, 'sort_order': 2, 'image': 'docinhos-sortidos.png', 'tags': ['doce', 'caixa'], 'track_stock': False},
]


class Command(BaseCommand):
    help = 'Popula o cardápio da Kero Kero Salgadinhos com dados reais e otimização de imagens'

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
                'name': 'Kero Kero',
                'store_type': Store.StoreType.FOOD,
                'status': Store.StoreStatus.ACTIVE,
                'email': '',
                'phone': '63992332803',
                'whatsapp_number': '63992332803',
                'primary_color': '#6B4B8A',
                'secondary_color': '#F8A9D4',
                'currency': 'BRL',
                'timezone': 'America/Sao_Paulo',
                'tax_rate': Decimal('0.00'),
                'delivery_enabled': True,
                'pickup_enabled': True,
                'min_order_value': Decimal('0.00'),
                'default_delivery_fee': Decimal('7.00'),
                'free_delivery_threshold': Decimal('80.00'),
                'operating_hours': SHARED_OPERATING_HOURS,
                'owner': owner,
                **SHARED_LOCATION,
                'metadata': {'seed_source': 'populate_kero_kero_menu'},
            }
        )
        status = '✅ Criada' if created else '🔄 Atualizada'
        self.stdout.write(self.style.SUCCESS(f'{status}: {store.name}'))

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

        self.stdout.write('📋 Fase 3: Criando Produtos com otimização de imagens...')
        optimized_count = 0
        for prod_data in PRODUCTS:
            category = category_map.get(prod_data['category_slug'])
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
                    'name': prod_data['name'],
                    'short_description': prod_data.get('short_description', ''),
                    'description': prod_data.get('description', ''),
                    'price': prod_data['price'],
                    'sku': prod_data.get('sku', ''),
                    'featured': prod_data.get('featured', False),
                    'sort_order': prod_data['sort_order'],
                    'main_image_url': image_url,
                    'tags': prod_data.get('tags', []),
                    'track_stock': prod_data.get('track_stock', False),
                }
            )
        self.stdout.write(self.style.SUCCESS(f'✅ {len(PRODUCTS)} produto(s) criado(s), {optimized_count} imagem(ns) otimizada(s)'))

        self.stdout.write('📋 Fase 4: Criando Zonas de Entrega...')
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
        self.stdout.write(f'Telefone: {store.phone}')
        self.stdout.write(f'Categorias: {len(CATEGORIES)}')
        self.stdout.write(f'Produtos: {len(PRODUCTS)}')
        self.stdout.write(f'Zonas de Entrega: {zones_created}')
        self.stdout.write(f'Imagens otimizadas: {optimized_count}')
