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
from django.utils.text import slugify
from apps.stores.models import Store, StoreCategory, StoreProduct


# Configuração
S3_BASE_URL = "https://pastita-final.s3.sa-east-1.amazonaws.com/products/"

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
        image_url = f"{S3_BASE_URL}{prod_data['image']}"
        
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
    print(f"\n📸 Base URL das imagens: {S3_BASE_URL}")


if __name__ == '__main__':
    populate_menu()
else:
    # Executando via shell
    populate_menu()
