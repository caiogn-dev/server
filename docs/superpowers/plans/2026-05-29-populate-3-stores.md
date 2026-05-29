# Consolidação e Otimização: Scripts de População das 3 Lojas

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar um master script unificado que popula as 3 lojas (Cê Saladas, Pastita, Kero Kero) com dados reais, integração WhatsApp (Cê Saladas), e otimização automática de imagens para WebP.

**Architecture:** 
- Classe `ImageOptimizer` centralizada que redimensiona/comprime imagens
- 3 management commands independentes (um por loja) + master script que orquestra todos
- Delivery zones populadas via tabela de preços (0-17 km)
- TDD: escrever testes antes de implementação

**Tech Stack:** Django management commands, Pillow (image optimization), `Decimal` para preços, `transaction.atomic` para consistency

---

## Task 1: ImageOptimizer Class (Utilities)

**Files:**
- Create: `apps/stores/utils/image_optimizer.py`
- Create: `tests/stores/utils/test_image_optimizer.py`

### 1.1 Write failing test for ImageOptimizer

- [ ] Create test file `/home/graco/WORK/server2/tests/stores/utils/test_image_optimizer.py`

```python
import os
import tempfile
from pathlib import Path
from PIL import Image
from django.test import TestCase
from apps.stores.utils.image_optimizer import ImageOptimizer

class ImageOptimizerTestCase(TestCase):
    def setUp(self):
        self.optimizer = ImageOptimizer()
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        # Clean up temp files
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_optimize_converts_to_webp(self):
        """Test that optimize() converts image to WebP format."""
        # Create a test PNG image (100x100)
        test_image_path = Path(self.temp_dir) / "test.png"
        img = Image.new('RGB', (100, 100), color='red')
        img.save(test_image_path, 'PNG')
        
        # Optimize
        result_path = self.optimizer.optimize(str(test_image_path))
        
        # Assert
        self.assertTrue(Path(result_path).exists())
        self.assertTrue(result_path.endswith('.webp'))
        
        # Verify it's actually WebP by opening it
        optimized = Image.open(result_path)
        self.assertEqual(optimized.format, 'WEBP')
    
    def test_optimize_respects_max_dimensions(self):
        """Test that optimize() respects max_width and max_height."""
        # Create a large test image (1000x1000)
        test_image_path = Path(self.temp_dir) / "large.png"
        img = Image.new('RGB', (1000, 1000), color='blue')
        img.save(test_image_path, 'PNG')
        
        # Optimize with max 600x600
        result_path = self.optimizer.optimize(str(test_image_path), max_width=600, max_height=600)
        
        # Verify dimensions
        optimized = Image.open(result_path)
        self.assertLessEqual(optimized.width, 600)
        self.assertLessEqual(optimized.height, 600)
    
    def test_optimize_maintains_aspect_ratio(self):
        """Test that optimize() maintains aspect ratio during resize."""
        # Create a wide image (800x200)
        test_image_path = Path(self.temp_dir) / "wide.png"
        img = Image.new('RGB', (800, 200), color='green')
        img.save(test_image_path, 'PNG')
        
        # Optimize
        result_path = self.optimizer.optimize(str(test_image_path), max_width=600, max_height=600)
        
        # Check aspect ratio is maintained (800:200 = 4:1)
        optimized = Image.open(result_path)
        original_ratio = 800 / 200
        optimized_ratio = optimized.width / optimized.height
        self.assertAlmostEqual(original_ratio, optimized_ratio, places=1)
    
    def test_optimize_returns_none_for_nonexistent_file(self):
        """Test that optimize() returns None for non-existent file."""
        result = self.optimizer.optimize("/nonexistent/path/image.png")
        self.assertIsNone(result)
```

Run: `pytest tests/stores/utils/test_image_optimizer.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'apps.stores.utils'`

---

### 1.2 Create ImageOptimizer class (minimal implementation to pass tests)

- [ ] Create directory: `mkdir -p /home/graco/WORK/server2/apps/stores/utils`

- [ ] Create `apps/stores/utils/__init__.py` (empty)

```python
```

- [ ] Create `apps/stores/utils/image_optimizer.py`

```python
"""
Image optimization utilities for product and category images.
Converts to WebP, redimensiona com aspect ratio preservation.
"""
from pathlib import Path
from PIL import Image
import logging

logger = logging.getLogger(__name__)


class ImageOptimizer:
    """
    Otimiza imagens para WebP com redimensionamento automático.
    """
    
    DEFAULT_MAX_WIDTH = 600
    DEFAULT_MAX_HEIGHT = 600
    
    def optimize(self, image_path, max_width=None, max_height=None):
        """
        Otimiza uma imagem: redimensiona, converte para WebP, comprime.
        
        Args:
            image_path (str): Caminho completo da imagem
            max_width (int): Largura máxima em pixels (default: 600)
            max_height (int): Altura máxima em pixels (default: 600)
        
        Returns:
            str: Caminho da imagem otimizada (.webp) ou None se falhar
        """
        max_width = max_width or self.DEFAULT_MAX_WIDTH
        max_height = max_height or self.DEFAULT_MAX_HEIGHT
        
        image_path = Path(image_path)
        
        # Validar arquivo
        if not image_path.exists():
            logger.warning(f"Imagem não encontrada: {image_path}")
            return None
        
        try:
            # Abrir imagem original
            img = Image.open(image_path)
            
            # Converter RGBA -> RGB se necessário (WebP pode gerar problemas com RGBA)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Criar fundo branco
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = bg
            
            # Redimensionar mantendo aspect ratio
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            # Gerar caminho de saída (.webp)
            output_path = image_path.parent / f"{image_path.stem}.webp"
            
            # Salvar como WebP (otimizado)
            img.save(output_path, 'WEBP', quality=80, method=6)
            
            logger.info(f"Imagem otimizada: {image_path} → {output_path} ({img.width}x{img.height})")
            
            return str(output_path)
        
        except Exception as e:
            logger.error(f"Erro ao otimizar {image_path}: {e}")
            return None
```

- [ ] Run tests: `pytest tests/stores/utils/test_image_optimizer.py -v`

Expected: PASS (4 tests)

- [ ] Commit

```bash
git add apps/stores/utils/ tests/stores/utils/
git commit -m "feat(stores): add ImageOptimizer class for WebP conversion"
```

---

## Task 2: Update populate_ce_saladas_menu.py (WhatsApp + Optimization)

**Files:**
- Modify: `apps/stores/management/commands/populate_ce_saladas_menu.py`
- Create: `tests/stores/management/commands/test_populate_ce_saladas_menu.py`

### 2.1 Write failing test for Cê Saladas population

- [ ] Create test file `/home/graco/WORK/server2/tests/stores/management/commands/test_populate_ce_saladas_menu.py`

```python
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.stores.models import Store
from apps.whatsapp.models import WhatsAppAccount
from io import StringIO
from django.core.management import call_command

User = get_user_model()


class PopulateCeSaladasTestCase(TestCase):
    def setUp(self):
        # Create a superuser for store ownership
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
    
    def test_command_creates_ce_saladas_store(self):
        """Test that populate_ce_saladas_menu creates Store."""
        out = StringIO()
        call_command('populate_ce_saladas_menu', stdout=out)
        
        store = Store.objects.get(slug='ce-saladas')
        self.assertIsNotNone(store)
        self.assertEqual(store.name, 'Cê Saladas')
        self.assertEqual(store.phone, '63991386719')
    
    def test_command_creates_whatsapp_account(self):
        """Test that populate_ce_saladas_menu creates WhatsAppAccount."""
        out = StringIO()
        call_command('populate_ce_saladas_menu', stdout=out)
        
        store = Store.objects.get(slug='ce-saladas')
        self.assertIsNotNone(store.whatsapp_account)
        
        wa_account = store.whatsapp_account
        self.assertEqual(wa_account.waba_id, '1537842617304215')
        self.assertEqual(wa_account.phone_number_id, '941408229062882')
        self.assertEqual(wa_account.phone_number, '63991386719')
    
    def test_command_creates_7_salads(self):
        """Test that populate_ce_saladas_menu creates 7 salads."""
        out = StringIO()
        call_command('populate_ce_saladas_menu', stdout=out)
        
        store = Store.objects.get(slug='ce-saladas')
        products = store.products.all()
        self.assertEqual(products.count(), 7)
        
        # Check product names
        expected_names = [
            'Tilápia Suprema',
            'Especial Filé de Frango',
            'Basic Lombo',
            'Salmão Sublime',
            'Almôndega Premium',
            'Queridinha',
            'Magnifico Camarão',
        ]
        product_names = set(products.values_list('name', flat=True))
        for name in expected_names:
            self.assertIn(name, product_names)
    
    def test_command_creates_delivery_zones(self):
        """Test that populate_ce_saladas_menu creates delivery zones."""
        out = StringIO()
        call_command('populate_ce_saladas_menu', stdout=out)
        
        store = Store.objects.get(slug='ce-saladas')
        zones = store.delivery_zones.all()
        self.assertEqual(zones.count(), 16)  # 16 km bands (0-17km)
```

Run: `pytest tests/stores/management/commands/test_populate_ce_saladas_menu.py::PopulateCeSaladasTestCase::test_command_creates_ce_saladas_store -v`

Expected: FAIL - `Store matching query does not exist`

---

### 2.2 Update populate_ce_saladas_menu.py to create WhatsAppAccount and use ImageOptimizer

- [ ] Modify `apps/stores/management/commands/populate_ce_saladas_menu.py`

Replace the entire file with:

```python
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
from django.db import transaction

from apps.stores.models import Store, StoreCategory, StoreProduct, StoreDeliveryZone
from apps.whatsapp.models import WhatsAppAccount
from apps.stores.utils.image_optimizer import ImageOptimizer

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


# Shared location data
SHARED_LOCATION = {
    "latitude": Decimal("-10.1852683"),
    "longitude": Decimal("-48.3036368"),
    "address": "Q. 112 Sul, Rua Sr 01, 2 - Palmas, Tocantins",
    "city": "Palmas",
    "state": "TO",
    "zip_code": "72000-000",
    "country": "BR",
}

# Shared operating hours
SHARED_OPERATING_HOURS = {
    "monday": {"open": "08:00", "close": "17:00"},
    "tuesday": {"open": "08:00", "close": "17:00"},
    "wednesday": {"open": "08:00", "close": "17:00"},
    "thursday": {"open": "08:00", "close": "17:00"},
    "friday": {"open": "08:00", "close": "17:00"},
    "saturday": {"open": "08:00", "close": "17:00"},
    "sunday": {"open": "00:00", "close": "00:00"},
}

# Delivery zones (0-17km)
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
        'image': 'basic-lombo.png',
        'tags': ['salada', 'carne'],
        'track_stock': False,
    },
    {
        'sku': 'CS-SAL',
        'category_slug': 'saladas',
        'name': 'Salmão Sublime',
        'short_description': 'Salada com salmão grelhado e ervas.',
        'description': 'Salada sofisticada com salmão grelhado ao ponto.',
        'price': Decimal('45.90'),
        'featured': True,
        'sort_order': 4,
        'image': 'salmao.png',
        'tags': ['salada', 'peixe', 'premium'],
        'track_stock': False,
    },
    {
        'sku': 'CS-ALM',
        'category_slug': 'saladas',
        'name': 'Almôndega Premium',
        'short_description': 'Salada com almôndegas caseiras.',
        'description': 'Salada com almôndegas preparadas artesanalmente.',
        'price': Decimal('39.90'),
        'featured': False,
        'sort_order': 5,
        'image': 'almondegas.png',
        'tags': ['salada', 'carne'],
        'track_stock': False,
    },
    {
        'sku': 'CS-QUE',
        'category_slug': 'saladas',
        'name': 'Queridinha',
        'short_description': 'A salada mais popular da Cê Saladas.',
        'description': 'A salada mais pedida com blend especial de proteínas.',
        'price': Decimal('41.90'),
        'featured': True,
        'sort_order': 6,
        'image': 'queridinha.png',
        'tags': ['salada', 'destaque'],
        'track_stock': False,
    },
    {
        'sku': 'CS-CAM',
        'category_slug': 'saladas',
        'name': 'Magnifico Camarão',
        'short_description': 'Salada com camarão grelhado.',
        'description': 'Salada sofisticada com camarão fresco grelhado.',
        'price': Decimal('48.90'),
        'featured': True,
        'sort_order': 7,
        'image': 'camarao.png',
        'tags': ['salada', 'frutos-do-mar', 'premium'],
        'track_stock': False,
    },
]


class Command(BaseCommand):
    help = 'Popula o cardápio da Cê Saladas com dados reais e WhatsApp integration'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Força sobrescrita de dados existentes')

    @transaction.atomic
    def handle(self, *args, **options):
        force = options.get('force', False)
        optimizer = ImageOptimizer()
        
        # Get or create owner
        owner = User.objects.filter(is_superuser=True).first()
        if not owner:
            owner = User.objects.filter(is_staff=True).first()
        if not owner:
            owner = User.objects.first()
        if not owner:
            self.stdout.write(self.style.ERROR('❌ Nenhum usuário encontrado'))
            return

        # =========================================================================
        # FASE 1: Create Store
        # =========================================================================
        self.stdout.write('📋 Fase 1: Criando Store...')
        store, created = Store.objects.update_or_create(
            slug=STORE_SLUG,
            defaults={
                'name': 'Cê Saladas',
                'store_type': Store.StoreType.FOOD,
                'status': Store.StoreStatus.ACTIVE,
                'email': '',
                'phone': '63991386719',
                'whatsapp_number': '63991386719',
                'primary_color': '#2E7D32',
                'secondary_color': '#F9A825',
                'currency': 'BRL',
                'timezone': 'America/Sao_Paulo',
                'tax_rate': Decimal('0.00'),
                'delivery_enabled': True,
                'pickup_enabled': True,
                'min_order_value': Decimal('0.00'),
                'default_delivery_fee': Decimal('8.00'),
                'free_delivery_threshold': Decimal('100.00'),
                'operating_hours': SHARED_OPERATING_HOURS,
                'owner': owner,
                **SHARED_LOCATION,
                'metadata': {
                    'seed_source': 'populate_ce_saladas_menu',
                    'waba_id': '1537842617304215',
                },
            }
        )
        status = '✅ Criada' if created else '🔄 Atualizada'
        self.stdout.write(self.style.SUCCESS(f'{status}: {store.name}'))

        # =========================================================================
        # FASE 2: Create WhatsApp Account (Cê Saladas only)
        # =========================================================================
        self.stdout.write('📋 Fase 2: Criando WhatsAppAccount...')
        wa_account, wa_created = WhatsAppAccount.objects.update_or_create(
            phone_number_id='941408229062882',
            defaults={
                'name': 'Cê Saladas Official',
                'waba_id': '1537842617304215',
                'phone_number': '63991386719',
                'display_phone_number': '+55 63 9 9138-6719',
                'status': WhatsAppAccount.AccountStatus.ACTIVE,
                'auto_response_enabled': True,
                'human_handoff_enabled': True,
                'owner': owner,
            }
        )
        # Link WhatsApp account to store
        store.whatsapp_account = wa_account
        store.save(update_fields=['whatsapp_account'])
        
        wa_status = '✅ Criada' if wa_created else '🔄 Atualizada'
        self.stdout.write(self.style.SUCCESS(f'{wa_status}: WABA {wa_account.waba_id}'))

        # =========================================================================
        # FASE 3: Create Categories
        # =========================================================================
        self.stdout.write('📋 Fase 3: Criando Categorias...')
        category_map = {}
        for cat_data in CATEGORIES:
            cat, _ = StoreCategory.objects.update_or_create(
                store=store,
                slug=cat_data['slug'],
                defaults={
                    'name': cat_data['name'],
                    'description': cat_data['description'],
                    'sort_order': cat_data['sort_order'],
                }
            )
            category_map[cat_data['slug']] = cat
        self.stdout.write(self.style.SUCCESS(f'✅ {len(CATEGORIES)} categoria(s) criada(s)'))

        # =========================================================================
        # FASE 4: Create Products with Image Optimization
        # =========================================================================
        self.stdout.write('📋 Fase 4: Criando Produtos com otimização de imagens...')
        optimized_count = 0
        for prod_data in PRODUCTS:
            category = category_map.get(prod_data['category_slug'])
            
            # Optimize image if it exists
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

        # =========================================================================
        # FASE 5: Create Delivery Zones
        # =========================================================================
        self.stdout.write('📋 Fase 5: Criando Zonas de Entrega...')
        zones_created = 0
        for zone_data in DELIVERY_ZONES:
            StoreDeliveryZone.objects.update_or_create(
                store=store,
                zone_type='distance_band',
                distance_band=f"{zone_data['min_km']}-{zone_data['max_km']}",
                defaults={
                    'name': f"{zone_data['min_km']}-{zone_data['max_km']}km",
                    'min_km': zone_data['min_km'],
                    'max_km': zone_data['max_km'],
                    'delivery_fee': zone_data['fee'],
                    'is_active': True,
                    'sort_order': zone_data['sort'],
                }
            )
            zones_created += 1
        self.stdout.write(self.style.SUCCESS(f'✅ {zones_created} zona(s) de entrega criada(s)'))

        # =========================================================================
        # SUMMARY
        # =========================================================================
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('✅ POPULAÇÃO CONCLUÍDA'))
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(f'Store: {store.name} ({store.slug})')
        self.stdout.write(f'WhatsApp: {wa_account.display_phone_number}')
        self.stdout.write(f'Categorias: {len(CATEGORIES)}')
        self.stdout.write(f'Produtos: {len(PRODUCTS)}')
        self.stdout.write(f'Zonas de Entrega: {zones_created}')
        self.stdout.write(f'Imagens otimizadas: {optimized_count}')
        self.stdout.write('')
```

- [ ] Run tests: `pytest tests/stores/management/commands/test_populate_ce_saladas_menu.py -v`

Expected: PASS (all 5 tests)

- [ ] Commit

```bash
git add apps/stores/management/commands/populate_ce_saladas_menu.py \
        tests/stores/management/commands/test_populate_ce_saladas_menu.py
git commit -m "feat(ce-saladas): add WhatsApp integration + image optimization + delivery zones"
```

---

## Task 3: Create populate_pastita_menu.py (Consolidated from 3 scripts)

**Files:**
- Create: `apps/stores/management/commands/populate_pastita_menu.py` (consolidate 3 scripts)
- Create: `tests/stores/management/commands/test_populate_pastita_menu.py`

### 3.1 Write failing test for Pastita

- [ ] Create test file `/home/graco/WORK/server2/tests/stores/management/commands/test_populate_pastita_menu.py`

```python
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.stores.models import Store
from io import StringIO
from django.core.management import call_command

User = get_user_model()


class PopulatePastitaTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
    
    def test_command_creates_pastita_store(self):
        """Test that populate_pastita_menu creates Store."""
        out = StringIO()
        call_command('populate_pastita_menu', stdout=out)
        
        store = Store.objects.get(slug='pastita')
        self.assertIsNotNone(store)
        self.assertEqual(store.name, 'Pastita')
        self.assertEqual(store.email, 'pastita.oficial@gmail.com')
    
    def test_command_creates_categories(self):
        """Test that populate_pastita_menu creates categories."""
        out = StringIO()
        call_command('populate_pastita_menu', stdout=out)
        
        store = Store.objects.get(slug='pastita')
        categories = store.categories.all()
        self.assertGreater(categories.count(), 0)
    
    def test_command_creates_products(self):
        """Test that populate_pastita_menu creates products."""
        out = StringIO()
        call_command('populate_pastita_menu', stdout=out)
        
        store = Store.objects.get(slug='pastita')
        products = store.products.all()
        self.assertGreater(products.count(), 0)
    
    def test_command_creates_delivery_zones(self):
        """Test that populate_pastita_menu creates delivery zones."""
        out = StringIO()
        call_command('populate_pastita_menu', stdout=out)
        
        store = Store.objects.get(slug='pastita')
        zones = store.delivery_zones.all()
        self.assertEqual(zones.count(), 16)
```

Run: `pytest tests/stores/management/commands/test_populate_pastita_menu.py::PopulatePastitaTestCase::test_command_creates_pastita_store -v`

Expected: FAIL - `Store matching query does not exist`

---

### 3.2 Create populate_pastita_menu.py (consolidate existing scripts)

- [ ] Read existing `/home/graco/WORK/server2/scripts/populate_pastita_menu.py` to extract product data

- [ ] Read existing `/home/graco/WORK/server2/scripts/populate_pastita_menu_complete.py` to get complete product list

- [ ] Create `/home/graco/WORK/server2/apps/stores/management/commands/populate_pastita_menu.py`

```python
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

# Shared location data (same as Cê Saladas)
SHARED_LOCATION = {
    "latitude": Decimal("-10.1852683"),
    "longitude": Decimal("-48.3036368"),
    "address": "Q. 112 Sul, Rua Sr 01, 2 - Palmas, Tocantins",
    "city": "Palmas",
    "state": "TO",
    "zip_code": "72000-000",
    "country": "BR",
}

# Shared operating hours
SHARED_OPERATING_HOURS = {
    "monday": {"open": "08:00", "close": "17:00"},
    "tuesday": {"open": "08:00", "close": "17:00"},
    "wednesday": {"open": "08:00", "close": "17:00"},
    "thursday": {"open": "08:00", "close": "17:00"},
    "friday": {"open": "08:00", "close": "17:00"},
    "saturday": {"open": "08:00", "close": "17:00"},
    "sunday": {"open": "00:00", "close": "00:00"},
}

# Delivery zones (same as Cê Saladas)
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
        "slug": "rondelli",
        "name": "Rondelli",
        "description": "Deliciosas massas de rondelli recheadas com ingredientes selecionados.",
        "sort_order": 1,
    },
    {
        "slug": "molhos",
        "name": "Molhos",
        "description": "Molhos artesanais preparados com receitas tradicionais.",
        "sort_order": 2,
    },
    {
        "slug": "promocoes",
        "name": "Promoções",
        "description": "Aproveite nossas ofertas especiais e combos!",
        "sort_order": 3,
    },
]

# Products (consolidado de populate_pastita_menu_complete.py)
PRODUCTS = [
    {
        "category_slug": "rondelli",
        "product_type_slug": "rondelli",
        "name": "Rondelli de Tomate Seco com Rúcula",
        "short_description": "Rondelli recheado com tomate seco e rúcula fresca",
        "description": "Delicioso rondelli recheado com tomates secos selecionados e rúcula fresca.",
        "price": Decimal("39.99"),
        "compare_at_price": Decimal("44.99"),
        "cost_price": Decimal("18.00"),
        "sku": "RON-TOM-RUC-001",
        "barcode": "7891234567891",
        "stock_quantity": 10,
        "featured": True,
        "sort_order": 1,
        "image": "tomate.webp",
        "tags": ["rondelli", "tomate-seco", "rucula", "vegetariano"],
    },
    {
        "category_slug": "rondelli",
        "product_type_slug": "rondelli",
        "name": "Rondelli de Frango com Queijo",
        "short_description": "Rondelli recheado com frango desfiado e queijo",
        "description": "Clássico rondelli de frango com queijo.",
        "price": Decimal("39.99"),
        "cost_price": Decimal("17.50"),
        "sku": "RON-FRA-QUE-002",
        "barcode": "7891234567892",
        "stock_quantity": 10,
        "featured": False,
        "sort_order": 2,
        "image": "frango.webp",
        "tags": ["rondelli", "frango", "queijo"],
    },
    {
        "category_slug": "rondelli",
        "product_type_slug": "rondelli",
        "name": "Rondelli de Presunto e Queijo",
        "short_description": "Rondelli recheado com presunto e queijo",
        "description": "Rondelli recheado com presunto e queijo.",
        "price": Decimal("39.99"),
        "cost_price": Decimal("17.00"),
        "sku": "RON-PRE-QUE-003",
        "barcode": "7891234567893",
        "stock_quantity": 10,
        "featured": False,
        "sort_order": 3,
        "image": "presunto-queijo.webp",
        "tags": ["rondelli", "presunto", "queijo"],
    },
]


class Command(BaseCommand):
    help = 'Popula o cardápio da Pastita Massas com dados reais'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Força sobrescrita de dados existentes')

    @transaction.atomic
    def handle(self, *args, **options):
        force = options.get('force', False)
        optimizer = ImageOptimizer()
        
        # Get or create owner
        owner = User.objects.filter(is_superuser=True).first()
        if not owner:
            owner = User.objects.filter(is_staff=True).first()
        if not owner:
            owner = User.objects.first()
        if not owner:
            self.stdout.write(self.style.ERROR('❌ Nenhum usuário encontrado'))
            return

        # =========================================================================
        # FASE 1: Create Store
        # =========================================================================
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
                'metadata': {
                    'seed_source': 'populate_pastita_menu',
                },
            }
        )
        status = '✅ Criada' if created else '🔄 Atualizada'
        self.stdout.write(self.style.SUCCESS(f'{status}: {store.name}'))

        # =========================================================================
        # FASE 2: Create Product Types
        # =========================================================================
        self.stdout.write('📋 Fase 2: Criando Tipos de Produtos...')
        type_map = {}
        for type_data in PRODUCT_TYPES:
            pt, _ = StoreProductType.objects.update_or_create(
                store=store,
                slug=type_data['slug'],
                defaults={
                    'name': type_data['name'],
                    'description': type_data['description'],
                    'icon': type_data['icon'],
                }
            )
            type_map[type_data['slug']] = pt
        self.stdout.write(self.style.SUCCESS(f'✅ {len(PRODUCT_TYPES)} tipo(s) de produto criado(s)'))

        # =========================================================================
        # FASE 3: Create Categories
        # =========================================================================
        self.stdout.write('📋 Fase 3: Criando Categorias...')
        category_map = {}
        for cat_data in CATEGORIES:
            cat, _ = StoreCategory.objects.update_or_create(
                store=store,
                slug=cat_data['slug'],
                defaults={
                    'name': cat_data['name'],
                    'description': cat_data['description'],
                    'sort_order': cat_data['sort_order'],
                }
            )
            category_map[cat_data['slug']] = cat
        self.stdout.write(self.style.SUCCESS(f'✅ {len(CATEGORIES)} categoria(s) criada(s)'))

        # =========================================================================
        # FASE 4: Create Products with Image Optimization
        # =========================================================================
        self.stdout.write('📋 Fase 4: Criando Produtos com otimização de imagens...')
        optimized_count = 0
        for prod_data in PRODUCTS:
            category = category_map.get(prod_data['category_slug'])
            product_type = type_map.get(prod_data['product_type_slug'])
            
            # Optimize image if it exists
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

        # =========================================================================
        # FASE 5: Create Delivery Zones
        # =========================================================================
        self.stdout.write('📋 Fase 5: Criando Zonas de Entrega...')
        zones_created = 0
        for zone_data in DELIVERY_ZONES:
            StoreDeliveryZone.objects.update_or_create(
                store=store,
                zone_type='distance_band',
                distance_band=f"{zone_data['min_km']}-{zone_data['max_km']}",
                defaults={
                    'name': f"{zone_data['min_km']}-{zone_data['max_km']}km",
                    'min_km': zone_data['min_km'],
                    'max_km': zone_data['max_km'],
                    'delivery_fee': zone_data['fee'],
                    'is_active': True,
                    'sort_order': zone_data['sort'],
                }
            )
            zones_created += 1
        self.stdout.write(self.style.SUCCESS(f'✅ {zones_created} zona(s) de entrega criada(s)'))

        # =========================================================================
        # SUMMARY
        # =========================================================================
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('✅ POPULAÇÃO CONCLUÍDA'))
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(f'Store: {store.name} ({store.slug})')
        self.stdout.write(f'Email: {store.email}')
        self.stdout.write(f'Categorias: {len(CATEGORIES)}')
        self.stdout.write(f'Produtos: {len(PRODUCTS)}')
        self.stdout.write(f'Zonas de Entrega: {zones_created}')
        self.stdout.write(f'Imagens otimizadas: {optimized_count}')
        self.stdout.write('')
```

- [ ] Run tests: `pytest tests/stores/management/commands/test_populate_pastita_menu.py -v`

Expected: PASS (all 4 tests)

- [ ] Commit

```bash
git add apps/stores/management/commands/populate_pastita_menu.py \
        tests/stores/management/commands/test_populate_pastita_menu.py
git commit -m "feat(pastita): consolidate 3 scripts + image optimization + delivery zones"
```

---

## Task 4: Create populate_kero_kero_menu.py (Update existing)

**Files:**
- Modify: `apps/stores/management/commands/populate_kero_kero_menu.py` (add ImageOptimizer + delivery zones)
- Create: `tests/stores/management/commands/test_populate_kero_kero_menu.py`

### 4.1 Write failing test for Kero Kero

- [ ] Create test file `/home/graco/WORK/server2/tests/stores/management/commands/test_populate_kero_kero_menu.py`

```python
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.stores.models import Store
from io import StringIO
from django.core.management import call_command

User = get_user_model()


class PopulateKeroKeroTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
    
    def test_command_creates_kero_kero_store(self):
        """Test that populate_kero_kero_menu creates Store."""
        out = StringIO()
        call_command('populate_kero_kero_menu', stdout=out)
        
        store = Store.objects.get(slug='kero-kero')
        self.assertIsNotNone(store)
        self.assertEqual(store.name, 'Kero Kero')
        self.assertEqual(store.phone, '63992332803')
    
    def test_command_creates_8_categories(self):
        """Test that populate_kero_kero_menu creates 8 categories."""
        out = StringIO()
        call_command('populate_kero_kero_menu', stdout=out)
        
        store = Store.objects.get(slug='kero-kero')
        categories = store.categories.all()
        self.assertEqual(categories.count(), 8)
    
    def test_command_creates_products(self):
        """Test that populate_kero_kero_menu creates products."""
        out = StringIO()
        call_command('populate_kero_kero_menu', stdout=out)
        
        store = Store.objects.get(slug='kero-kero')
        products = store.products.all()
        self.assertGreaterEqual(products.count(), 11)
    
    def test_command_creates_delivery_zones(self):
        """Test that populate_kero_kero_menu creates delivery zones."""
        out = StringIO()
        call_command('populate_kero_kero_menu', stdout=out)
        
        store = Store.objects.get(slug='kero-kero')
        zones = store.delivery_zones.all()
        self.assertEqual(zones.count(), 16)
```

Run: `pytest tests/stores/management/commands/test_populate_kero_kero_menu.py::PopulateKeroKeroTestCase::test_command_creates_kero_kero_store -v`

Expected: FAIL - `Store matching query does not exist`

---

### 4.2 Update populate_kero_kero_menu.py (add delivery zones + image optimization)

- [ ] Read the current file at `/home/graco/WORK/server2/apps/stores/management/commands/populate_kero_kero_menu.py` (from git show)

- [ ] Modify to add:
  - Import ImageOptimizer
  - Add DELIVERY_ZONES constant (same as Cê Saladas)
  - Add SHARED_LOCATION and SHARED_OPERATING_HOURS
  - Update Store creation to include these fields
  - Update product creation to use ImageOptimizer
  - Add Fase 4 for delivery zones

Complete file (replace entire file):

```python
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

# Shared location data
SHARED_LOCATION = {
    "latitude": Decimal("-10.1852683"),
    "longitude": Decimal("-48.3036368"),
    "address": "Q. 112 Sul, Rua Sr 01, 2 - Palmas, Tocantins",
    "city": "Palmas",
    "state": "TO",
    "zip_code": "72000-000",
    "country": "BR",
}

# Shared operating hours
SHARED_OPERATING_HOURS = {
    "monday": {"open": "08:00", "close": "17:00"},
    "tuesday": {"open": "08:00", "close": "17:00"},
    "wednesday": {"open": "08:00", "close": "17:00"},
    "thursday": {"open": "08:00", "close": "17:00"},
    "friday": {"open": "08:00", "close": "17:00"},
    "saturday": {"open": "08:00", "close": "17:00"},
    "sunday": {"open": "00:00", "close": "00:00"},
}

# Delivery zones
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
        'short_description': 'Bolo vulcão com calda de chocolate.',
        'description': 'Delicioso bolo vulcão com calda de chocolate que derrete na boca.',
        'price': Decimal('45.00'),
        'featured': True,
        'sort_order': 1,
        'image': 'bolo-vulcao.png',
        'tags': ['bolo', 'chocolate', 'destaque'],
        'track_stock': False,
    },
    {
        'sku': 'KK-MINI-PIZZA',
        'category_slug': 'lanches-e-massas',
        'name': 'Mini Pizzas Sortidas',
        'short_description': 'Mini pizzas assadas no forno de barro.',
        'description': '12 mini pizzas sortidas assadas no forno de barro.',
        'price': Decimal('35.00'),
        'featured': False,
        'sort_order': 1,
        'image': 'mini-pizzas.png',
        'tags': ['pizza', 'lanche'],
        'track_stock': False,
    },
    {
        'sku': 'KK-REFRI-2L',
        'category_slug': 'bebidas',
        'name': 'Refrigerante 2L',
        'short_description': 'Refrigerante gelado 2 litros.',
        'description': 'Refrigerante 2 litros bem gelado para acompanhar seu pedido.',
        'price': Decimal('9.90'),
        'featured': False,
        'sort_order': 1,
        'image': 'refri-2l.png',
        'tags': ['bebida', 'refri'],
        'track_stock': False,
    },
    {
        'sku': 'KK-PAO-QUEIJO',
        'category_slug': 'lanches-e-massas',
        'name': 'Pão de Queijo Assado',
        'short_description': 'Pão de queijo quente assado no forno.',
        'description': 'Pão de queijo quente acabadinho do forno, macio e saboroso.',
        'price': Decimal('15.00'),
        'featured': False,
        'sort_order': 2,
        'image': 'pao-queijo.png',
        'tags': ['pao', 'queijo', 'lanche'],
        'track_stock': False,
    },
    {
        'sku': 'KK-PASTEL-CARNE',
        'category_slug': 'lanches-e-massas',
        'name': 'Pastel de Carne',
        'short_description': 'Pastel frito recheado com carne.',
        'description': 'Pastel frito crocante recheado com carne moída temperada.',
        'price': Decimal('12.00'),
        'featured': False,
        'sort_order': 3,
        'image': 'pastel-carne.png',
        'tags': ['pastel', 'carne'],
        'track_stock': False,
    },
    {
        'sku': 'KK-COMBO-REFRI',
        'category_slug': 'combos-com-refri',
        'name': 'Combo 50 Fritos + Refri 2L',
        'short_description': '50 salgadinhos fritos + 1 refrigerante 2L.',
        'description': '50 salgadinhos fritos sortidos + 1 refrigerante 2 litros gelado.',
        'price': Decimal('59.90'),
        'featured': True,
        'sort_order': 1,
        'image': 'combo-fritos-refri.png',
        'tags': ['combo', 'promo', 'refri'],
        'track_stock': False,
    },
    {
        'sku': 'KK-DOCINHO',
        'category_slug': 'bolos-e-doces',
        'name': 'Docinhos Sortidos',
        'short_description': 'Caixa com 12 docinhos sortidos.',
        'description': 'Caixa com 12 docinhos variados: brigadeiro, beijinho, romeu e julieta.',
        'price': Decimal('28.00'),
        'featured': False,
        'sort_order': 2,
        'image': 'docinhos.png',
        'tags': ['doce', 'caixa'],
        'track_stock': False,
    },
]


class Command(BaseCommand):
    help = 'Popula o cardápio da Kero Kero Salgadinhos com dados reais e otimização de imagens'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Força sobrescrita de dados existentes')

    @transaction.atomic
    def handle(self, *args, **options):
        force = options.get('force', False)
        optimizer = ImageOptimizer()
        
        # Get or create owner
        owner = User.objects.filter(is_superuser=True).first()
        if not owner:
            owner = User.objects.filter(is_staff=True).first()
        if not owner:
            owner = User.objects.first()
        if not owner:
            self.stdout.write(self.style.ERROR('❌ Nenhum usuário encontrado'))
            return

        # =========================================================================
        # FASE 1: Create Store
        # =========================================================================
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
                'primary_color': '#E91E63',
                'secondary_color': '#FF6EC7',
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
                'metadata': {
                    'seed_source': 'populate_kero_kero_menu',
                },
            }
        )
        status = '✅ Criada' if created else '🔄 Atualizada'
        self.stdout.write(self.style.SUCCESS(f'{status}: {store.name}'))

        # =========================================================================
        # FASE 2: Create Categories
        # =========================================================================
        self.stdout.write('📋 Fase 2: Criando Categorias...')
        category_map = {}
        for cat_data in CATEGORIES:
            cat, _ = StoreCategory.objects.update_or_create(
                store=store,
                slug=cat_data['slug'],
                defaults={
                    'name': cat_data['name'],
                    'description': cat_data['description'],
                    'sort_order': cat_data['sort_order'],
                }
            )
            category_map[cat_data['slug']] = cat
        self.stdout.write(self.style.SUCCESS(f'✅ {len(CATEGORIES)} categoria(s) criada(s)'))

        # =========================================================================
        # FASE 3: Create Products with Image Optimization
        # =========================================================================
        self.stdout.write('📋 Fase 3: Criando Produtos com otimização de imagens...')
        optimized_count = 0
        for prod_data in PRODUCTS:
            category = category_map.get(prod_data['category_slug'])
            
            # Optimize image if it exists
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

        # =========================================================================
        # FASE 4: Create Delivery Zones
        # =========================================================================
        self.stdout.write('📋 Fase 4: Criando Zonas de Entrega...')
        zones_created = 0
        for zone_data in DELIVERY_ZONES:
            StoreDeliveryZone.objects.update_or_create(
                store=store,
                zone_type='distance_band',
                distance_band=f"{zone_data['min_km']}-{zone_data['max_km']}",
                defaults={
                    'name': f"{zone_data['min_km']}-{zone_data['max_km']}km",
                    'min_km': zone_data['min_km'],
                    'max_km': zone_data['max_km'],
                    'delivery_fee': zone_data['fee'],
                    'is_active': True,
                    'sort_order': zone_data['sort'],
                }
            )
            zones_created += 1
        self.stdout.write(self.style.SUCCESS(f'✅ {zones_created} zona(s) de entrega criada(s)'))

        # =========================================================================
        # SUMMARY
        # =========================================================================
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('✅ POPULAÇÃO CONCLUÍDA'))
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(f'Store: {store.name} ({store.slug})')
        self.stdout.write(f'Telefone: {store.phone}')
        self.stdout.write(f'Categorias: {len(CATEGORIES)}')
        self.stdout.write(f'Produtos: {len(PRODUCTS)}')
        self.stdout.write(f'Zonas de Entrega: {zones_created}')
        self.stdout.write(f'Imagens otimizadas: {optimized_count}')
        self.stdout.write('')
```

- [ ] Run tests: `pytest tests/stores/management/commands/test_populate_kero_kero_menu.py -v`

Expected: PASS (all 4 tests)

- [ ] Commit

```bash
git add apps/stores/management/commands/populate_kero_kero_menu.py \
        tests/stores/management/commands/test_populate_kero_kero_menu.py
git commit -m "feat(kero-kero): add image optimization + delivery zones"
```

---

## Task 5: Create Master Script (populate_all_stores.py)

**Files:**
- Create: `apps/stores/management/commands/populate_all_stores.py`
- Create: `tests/stores/management/commands/test_populate_all_stores.py`

### 5.1 Write failing test for master script

- [ ] Create test file `/home/graco/WORK/server2/tests/stores/management/commands/test_populate_all_stores.py`

```python
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.stores.models import Store
from io import StringIO
from django.core.management import call_command

User = get_user_model()


class PopulateAllStoresTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
    
    def test_command_creates_all_3_stores(self):
        """Test that populate_all_stores creates all 3 stores."""
        out = StringIO()
        call_command('populate_all_stores', '--all', stdout=out)
        
        ce_saladas = Store.objects.get(slug='ce-saladas')
        pastita = Store.objects.get(slug='pastita')
        kero_kero = Store.objects.get(slug='kero-kero')
        
        self.assertEqual(Store.objects.count(), 3)
    
    def test_command_creates_all_categories(self):
        """Test that populate_all_stores creates all categories."""
        out = StringIO()
        call_command('populate_all_stores', '--all', stdout=out)
        
        total_categories = sum(
            store.categories.count()
            for store in Store.objects.all()
        )
        self.assertGreater(total_categories, 0)
    
    def test_command_creates_all_products(self):
        """Test that populate_all_stores creates all products."""
        out = StringIO()
        call_command('populate_all_stores', '--all', stdout=out)
        
        total_products = sum(
            store.products.count()
            for store in Store.objects.all()
        )
        self.assertGreater(total_products, 0)
    
    def test_command_creates_all_delivery_zones(self):
        """Test that populate_all_stores creates delivery zones for all stores."""
        out = StringIO()
        call_command('populate_all_stores', '--all', stdout=out)
        
        for store in Store.objects.all():
            zones = store.delivery_zones.all()
            self.assertEqual(zones.count(), 16, f"{store.name} should have 16 zones")
    
    def test_command_with_single_store_option(self):
        """Test that --store=ce-saladas creates only Cê Saladas."""
        out = StringIO()
        call_command('populate_all_stores', '--store=ce-saladas', stdout=out)
        
        self.assertEqual(Store.objects.count(), 1)
        store = Store.objects.first()
        self.assertEqual(store.slug, 'ce-saladas')
```

Run: `pytest tests/stores/management/commands/test_populate_all_stores.py::PopulateAllStoresTestCase::test_command_creates_all_3_stores -v`

Expected: FAIL - `Store matching query does not exist`

---

### 5.2 Create populate_all_stores.py master script

- [ ] Create `/home/graco/WORK/server2/apps/stores/management/commands/populate_all_stores.py`

```python
"""
Master command to populate all 3 stores (Cê Saladas, Pastita, Kero Kero).

Usage:
    python manage.py populate_all_stores --all              # Populate all 3 stores
    python manage.py populate_all_stores --store=ce-saladas # Populate only Cê Saladas
    python manage.py populate_all_stores --store=pastita --store=kero-kero
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from io import StringIO

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Master command to populate all 3 stores with data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Populate all 3 stores (default)',
        )
        parser.add_argument(
            '--store',
            action='append',
            dest='stores',
            help='Populate specific store (ce-saladas, pastita, kero-kero). Can be specified multiple times.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force overwrite of existing data',
        )

    def handle(self, *args, **options):
        stores_to_populate = []
        force = options.get('force', False)
        
        # Determine which stores to populate
        if options.get('all'):
            stores_to_populate = ['ce-saladas', 'pastita', 'kero-kero']
        elif options.get('stores'):
            stores_to_populate = options['stores']
        else:
            # Default: populate all
            stores_to_populate = ['ce-saladas', 'pastita', 'kero-kero']
        
        # Validate store names
        valid_stores = {'ce-saladas', 'pastita', 'kero-kero'}
        for store in stores_to_populate:
            if store not in valid_stores:
                raise CommandError(f"Unknown store: {store}. Valid: {valid_stores}")
        
        # Mapping of store to management command
        store_commands = {
            'ce-saladas': 'populate_ce_saladas_menu',
            'pastita': 'populate_pastita_menu',
            'kero-kero': 'populate_kero_kero_menu',
        }
        
        # =========================================================================
        # MASTER EXECUTION
        # =========================================================================
        self.stdout.write(self.style.HTTP_SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.HTTP_SUCCESS('🚀 INICIANDO POPULAÇÃO DAS 3 LOJAS'))
        self.stdout.write(self.style.HTTP_SUCCESS('='*70 + '\n'))
        
        results = {}
        for store_slug in stores_to_populate:
            command_name = store_commands[store_slug]
            
            self.stdout.write(f'\n📦 Populando: {store_slug.upper()}')
            self.stdout.write('-' * 70)
            
            try:
                out = StringIO()
                call_command(
                    command_name,
                    '--force' if force else '',
                    stdout=out,
                    stderr=out,
                )
                
                # Print command output
                self.stdout.write(out.getvalue())
                results[store_slug] = 'SUCCESS'
                
            except Exception as e:
                logger.exception(f"Erro ao popular {store_slug}")
                self.stdout.write(self.style.ERROR(f'❌ ERRO: {e}'))
                results[store_slug] = f'FAILED: {e}'
        
        # =========================================================================
        # SUMMARY
        # =========================================================================
        self.stdout.write(self.style.HTTP_SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.HTTP_SUCCESS('📊 RESUMO DA EXECUÇÃO'))
        self.stdout.write(self.style.HTTP_SUCCESS('='*70 + '\n'))
        
        for store_slug, status in results.items():
            if status == 'SUCCESS':
                self.stdout.write(self.style.SUCCESS(f'✅ {store_slug}: {status}'))
            else:
                self.stdout.write(self.style.ERROR(f'❌ {store_slug}: {status}'))
        
        self.stdout.write('\n')
```

- [ ] Run tests: `pytest tests/stores/management/commands/test_populate_all_stores.py -v`

Expected: PASS (all 5 tests)

- [ ] Commit

```bash
git add apps/stores/management/commands/populate_all_stores.py \
        tests/stores/management/commands/test_populate_all_stores.py
git commit -m "feat(stores): add master populate_all_stores command"
```

---

## Task 6: Integration Tests and Documentation

**Files:**
- Create: `tests/stores/management/commands/test_populate_integration.py`
- Create: `docs/POPULATION.md` (documentation)

### 6.1 Write integration tests

- [ ] Create `/home/graco/WORK/server2/tests/stores/management/commands/test_populate_integration.py`

```python
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.stores.models import Store, StoreProduct, StoreDeliveryZone
from apps.whatsapp.models import WhatsAppAccount
from io import StringIO
from django.core.management import call_command

User = get_user_model()


class PopulationIntegrationTestCase(TestCase):
    """Integration tests for the complete population workflow."""
    
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
    
    def test_full_population_workflow(self):
        """Test complete populate_all_stores --all workflow."""
        out = StringIO()
        call_command('populate_all_stores', '--all', stdout=out)
        
        # Verify all stores exist
        self.assertEqual(Store.objects.count(), 3)
        
        # Verify store data
        ce_saladas = Store.objects.get(slug='ce-saladas')
        self.assertEqual(ce_saladas.name, 'Cê Saladas')
        self.assertEqual(ce_saladas.phone, '63991386719')
        self.assertTrue(ce_saladas.delivery_enabled)
        self.assertTrue(ce_saladas.pickup_enabled)
        
        # Verify WhatsApp account for Cê Saladas
        self.assertIsNotNone(ce_saladas.whatsapp_account)
        wa = ce_saladas.whatsapp_account
        self.assertEqual(wa.waba_id, '1537842617304215')
        self.assertEqual(wa.phone_number_id, '941408229062882')
        
        # Verify products
        self.assertEqual(ce_saladas.products.count(), 7)
        self.assertEqual(Store.objects.get(slug='kero-kero').products.count(), 11)
        
        # Verify delivery zones
        for store in Store.objects.all():
            zones = store.delivery_zones.all()
            self.assertEqual(zones.count(), 16)
            
            # Verify zone prices
            zone_0_2 = zones.get(distance_band='0-2')
            self.assertEqual(zone_0_2.delivery_fee, 7)
            
            zone_17 = zones.get(distance_band='17-17')
            self.assertEqual(zone_17.delivery_fee, 28)
    
    def test_ce_saladas_has_correct_salads(self):
        """Test Cê Saladas has all 7 salads."""
        out = StringIO()
        call_command('populate_ce_saladas_menu', stdout=out)
        
        store = Store.objects.get(slug='ce-saladas')
        expected_salads = [
            'Tilápia Suprema',
            'Especial Filé de Frango',
            'Basic Lombo',
            'Salmão Sublime',
            'Almôndega Premium',
            'Queridinha',
            'Magnifico Camarão',
        ]
        
        product_names = set(store.products.values_list('name', flat=True))
        for salad in expected_salads:
            self.assertIn(salad, product_names)
    
    def test_all_stores_have_same_location(self):
        """Test all stores have same location data."""
        out = StringIO()
        call_command('populate_all_stores', '--all', stdout=out)
        
        stores = Store.objects.all()
        locations = set(
            (str(s.latitude), str(s.longitude), s.address)
            for s in stores
        )
        
        # All should have same location (1 unique set)
        self.assertEqual(len(locations), 1)
    
    def test_idempotency(self):
        """Test that running populate twice gives same results."""
        # First run
        out = StringIO()
        call_command('populate_all_stores', '--all', stdout=out)
        
        count_stores_1 = Store.objects.count()
        count_products_1 = sum(s.products.count() for s in Store.objects.all())
        
        # Second run (idempotent)
        out = StringIO()
        call_command('populate_all_stores', '--all', stdout=out)
        
        count_stores_2 = Store.objects.count()
        count_products_2 = sum(s.products.count() for s in Store.objects.all())
        
        # Same counts (no duplicates)
        self.assertEqual(count_stores_1, count_stores_2)
        self.assertEqual(count_products_1, count_products_2)
```

- [ ] Run tests: `pytest tests/stores/management/commands/test_populate_integration.py -v`

Expected: PASS (all 4 integration tests)

---

### 6.2 Create documentation

- [ ] Create `/home/graco/WORK/server2/docs/POPULATION.md`

```markdown
# Population Scripts Documentation

## Overview

Complete automation for populating 3 stores (Cê Saladas, Pastita, Kero Kero) with realistic data:
- Store information, contact details, operating hours
- WhatsApp Business Account integration (Cê Saladas only)
- Products with automatic WebP image optimization
- Delivery zones (16 distance bands: 0-17 km)

## Quick Start

### Populate All 3 Stores

```bash
python manage.py populate_all_stores --all
```

### Populate Single Store

```bash
python manage.py populate_ce_saladas_menu
python manage.py populate_pastita_menu
python manage.py populate_kero_kero_menu
```

### Force Overwrite

```bash
python manage.py populate_all_stores --all --force
```

## Architecture

### ImageOptimizer Class
- Location: `apps/stores/utils/image_optimizer.py`
- Automatically converts images to WebP
- Redimensiones to max 600x600px (preserves aspect ratio)
- Compresses with quality=80

### Master Script
- Location: `apps/stores/management/commands/populate_all_stores.py`
- Orchestrates all 3 individual scripts
- Idempotent (safe to run multiple times)
- Supports `--store=name` for selective population

### Individual Scripts
- `populate_ce_saladas_menu.py` — 7 salads + WhatsApp Account
- `populate_pastita_menu.py` — Rondelli & Molhos (consolidated from 3 scripts)
- `populate_kero_kero_menu.py` — 11 salgadinhos products in 8 categories

## Data Structure

### Shared Across All 3 Stores
- **Location:** Q. 112 Sul, Rua Sr 01, 2 - Palmas, Tocantins
  - Latitude: -10.1852683
  - Longitude: -48.3036368
- **Operating Hours:** Monday-Saturday 08:00-17:00 (Sunday closed)
- **Delivery:** Enabled (distance bands 0-17 km)
- **Pickup:** Enabled
- **Tax Rate:** 0% (no taxes applied)

### Store-Specific Data

| Store | Email | Phone | Default Fee | Free Threshold | Colors |
|-------|-------|-------|------------|----------------|--------|
| Cê Saladas | (none) | 63991386719 | R$ 8 | R$ 100 | Green/Orange |
| Pastita | pastita.oficial@gmail.com | 63991172166 | R$ 10 | R$ 100 | Orange/Yellow |
| Kero Kero | (none) | 63992332803 | R$ 7 | R$ 80 | Pink/Magenta |

### Delivery Zones (All Stores)

| Distance | Fee |
|----------|-----|
| 0-2 km | R$ 7 |
| 2.1-3 km | R$ 8 |
| 3.1-5 km | R$ 9 |
| 5.1-6 km | R$ 10 |
| 6.1-6.9 km | R$ 11 |
| 7-7.9 km | R$ 12 |
| 8 km | R$ 13 |
| 9 km | R$ 14 |
| 10 km | R$ 15 |
| 11 km | R$ 16 |
| 12 km | R$ 18 |
| 13 km | R$ 20 |
| 14 km | R$ 22 |
| 15 km | R$ 24 |
| 16 km | R$ 26 |
| 17 km | R$ 28 |

## WhatsApp Integration (Cê Saladas Only)

- **WABA ID:** 1537842617304215
- **Phone Number ID:** 941408229062882
- **Phone Number:** 63991386719
- **Access Token:** Added manually post-population
- **Status:** ACTIVE
- **Auto Response:** Enabled
- **Human Handoff:** Enabled

## Image Optimization

All product and category images are automatically optimized:

```python
from apps.stores.utils.image_optimizer import ImageOptimizer

optimizer = ImageOptimizer()
result_path = optimizer.optimize('/path/to/image.png', max_width=600, max_height=600)
# Returns: /path/to/image.webp (converted and compressed)
```

**Features:**
- Format conversion: PNG/JPG → WebP
- Resize: Maintains aspect ratio, max 600x600px
- Quality: 80/100 (balanced size/quality)
- Fallback: Returns None if image not found or processing fails

## Testing

Run all tests:
```bash
pytest tests/stores/management/commands/ -v
```

Key test suites:
- `test_image_optimizer.py` — ImageOptimizer class
- `test_populate_ce_saladas_menu.py` — Cê Saladas (+ WhatsApp)
- `test_populate_pastita_menu.py` — Pastita menu
- `test_populate_kero_kero_menu.py` — Kero Kero menu
- `test_populate_all_stores.py` — Master script
- `test_populate_integration.py` — Full workflow

## Idempotency

All scripts are idempotent and safe to run multiple times:
```bash
python manage.py populate_all_stores --all
python manage.py populate_all_stores --all  # Same data, no duplication
```

Uses Django's `update_or_create()` pattern to prevent duplicates.

## Troubleshooting

### "No users found"
Create a superuser first:
```bash
python manage.py createsuperuser
```

### Images not optimizing
Check that image files exist in `settings.MEDIA_ROOT`. If missing, ImageOptimizer silently skips optimization (logs warning).

### WhatsApp Account token missing
The access_token must be added manually via Django admin or API. It's not seeded for security.

## Files

- **Commands:** `apps/stores/management/commands/populate_*.py`
- **Utils:** `apps/stores/utils/image_optimizer.py`
- **Tests:** `tests/stores/management/commands/test_populate_*.py`
- **Docs:** `docs/POPULATION.md` (this file)
```

- [ ] Commit

```bash
git add tests/stores/management/commands/test_populate_integration.py \
        docs/POPULATION.md
git commit -m "docs: add population guide + integration tests"
```

---

## Final: Self-Review

- [ ] **Spec Coverage:** ✅ All spec sections have corresponding tasks
  - Store creation ✅
  - WhatsAppAccount (Cê Saladas) ✅
  - Categories ✅
  - Products (7, N, 11) ✅
  - Image optimization (WebP) ✅
  - Delivery zones (16 bands) ✅
  - Master script orchestration ✅

- [ ] **No Placeholders:** ✅ All code is complete (no TBD, no "add validation", no "implement later")

- [ ] **Type Consistency:** ✅ ImageOptimizer, Decimal, StoreDeliveryZone all consistent across tasks

---

## Execution Options

**Plan complete and saved to `docs/superpowers/plans/2026-05-29-populate-3-stores.md`.**

Two execution options:

### 1. Subagent-Driven (Recommended)
I dispatch a fresh subagent per task, review between tasks, fast iteration. Parallelize independent tasks.

### 2. Inline Execution
Execute tasks in this session using executing-plans skill, batch execution with checkpoints.

**Which approach?**
