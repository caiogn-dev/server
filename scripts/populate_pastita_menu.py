#!/usr/bin/env python
"""
Script para popular o cardápio da Pastita Massas.

Execute com:
    python manage.py shell < scripts/populate_pastita_menu.py
    
Ou:
    python manage.py runscript populate_pastita_menu
"""
import os
import sys
import django

# Setup Django if running standalone
if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
    django.setup()

from decimal import Decimal
from pathlib import Path
from django.conf import settings
from django.utils.text import slugify
from apps.stores.models import Store, StoreCategory, StoreProduct
from apps.core.utils import build_absolute_media_url


# Configuração
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

# Dados do cardápio
CATEGORIES = [
    {
        "name": "Rondelli",
        "slug": "rondelli",
        "description": "Deliciosas massas de rondelli recheadas",
        "sort_order": 1,
    },
    {
        "name": "Molhos",
        "slug": "molhos", 
        "description": "Molhos artesanais para acompanhar",
        "sort_order": 2,
    },
]

PRODUCTS = [
    # Rondelli
    {
        "category_slug": "rondelli",
        "name": "Rondelli de Tomate Seco com Rúcula",
        "description": "Rondelli recheado com tomate seco e rúcula",
        "price": Decimal("39.99"),
        "image": "tomate.webp",
        "sku": "RON-TOM-RUC",
        "sort_order": 1,
    },
    {
        "category_slug": "rondelli",
        "name": "Rondelli de Frango com Queijo",
        "description": "Massa de Rondelli recheada com frango.",
        "price": Decimal("39.99"),
        "image": "frango.webp",
        "sku": "RON-FRA-QUE",
        "sort_order": 2,
    },
    {
        "category_slug": "rondelli",
        "name": "Rondelli de Presunto e Queijo",
        "description": "Rondelli recheado com Presunto e Queijo",
        "price": Decimal("39.99"),
        "image": "presunto-queijo.webp",
        "sku": "RON-PRE-QUE",
        "sort_order": 3,
    },
    {
        "category_slug": "rondelli",
        "name": "Rondelli de Damasco e Nozes",
        "description": "Rondelli recheado com damasco, nozes e queijo brie",
        "price": Decimal("39.99"),
        "image": "damasco.webp",
        "sku": "RON-DAM-NOZ",
        "sort_order": 4,
    },
    {
        "category_slug": "rondelli",
        "name": "Rondelli 4 Queijos",
        "description": "Rondelli recheado com quatro tipos de queijos",
        "price": Decimal("39.99"),
        "image": "4queijos.webp",
        "sku": "RON-4QUE",
        "sort_order": 5,
    },
    # Molhos
    {
        "category_slug": "molhos",
        "name": "Molho de Tomate",
        "description": "Delicioso e natural molho de tomate",
        "price": Decimal("19.90"),
        "image": "molho-tomate.webp",
        "sku": "MOL-TOM",
        "sort_order": 1,
    },
    {
        "category_slug": "molhos",
        "name": "Molho Branco",
        "description": "Delicioso e natural molho branco",
        "price": Decimal("16.90"),
        "image": "molho-branco.webp",
        "sku": "MOL-BRA",
        "sort_order": 2,
    },
]


def populate_menu():
    """Popula o cardápio da Pastita."""
    
    # Encontrar a loja Pastita
    store = Store.objects.filter(slug__icontains='pastita').first()
    if not store:
        store = Store.objects.filter(name__icontains='pastita').first()
    
    if not store:
        print("❌ Loja Pastita não encontrada!")
        print("Lojas disponíveis:")
        for s in Store.objects.all():
            print(f"  - {s.name} (slug: {s.slug})")
        return
    
    print(f"✅ Loja encontrada: {store.name} (ID: {store.id})")
    
    # Criar categorias
    print("\n📁 Criando categorias...")
    categories = {}
    for cat_data in CATEGORIES:
        category, created = StoreCategory.objects.update_or_create(
            store=store,
            slug=cat_data["slug"],
            defaults={
                "name": cat_data["name"],
                "description": cat_data["description"],
                "sort_order": cat_data["sort_order"],
                "is_active": True,
            }
        )
        categories[cat_data["slug"]] = category
        status = "✨ Criada" if created else "🔄 Atualizada"
        print(f"  {status}: {category.name}")
    
    # Criar produtos
    print("\n🍝 Criando produtos...")
    for prod_data in PRODUCTS:
        category = categories.get(prod_data["category_slug"])
        slug = slugify(prod_data["name"])
        image_url = build_seed_media_url('products', prod_data.get('image', ''))
        
        product, created = StoreProduct.objects.update_or_create(
            store=store,
            sku=prod_data["sku"],
            defaults={
                "category": category,
                "name": prod_data["name"],
                "slug": slug,
                "description": prod_data["description"],
                "price": prod_data["price"],
                "main_image_url": image_url,
                "status": StoreProduct.ProductStatus.ACTIVE,
                "track_stock": False,  # Não controlar estoque
                "sort_order": prod_data["sort_order"],
            }
        )
        status = "✨ Criado" if created else "🔄 Atualizado"
        print(f"  {status}: {product.name} - R$ {product.price}")
    
    # Resumo
    total_categories = StoreCategory.objects.filter(store=store).count()
    total_products = StoreProduct.objects.filter(store=store).count()
    
    print(f"\n✅ Cardápio populado com sucesso!")
    print(f"   📁 Categorias: {total_categories}")
    print(f"   🍝 Produtos: {total_products}")
    seed_base = os.environ.get('STORE_SEED_MEDIA_BASE_URL', '').strip() or f"{settings.BACKEND_URL.rstrip('/')}{settings.MEDIA_URL}seeds"
    print(f"\n📸 Base URL das imagens: {seed_base}")


if __name__ == '__main__':
    populate_menu()
else:
    # Executando via shell
    populate_menu()
