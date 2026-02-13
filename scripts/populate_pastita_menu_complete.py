#!/usr/bin/env python3
"""
Script COMPLETO para popular o cardápio da Pastita Massas.
Versão 2.0 - Usa todos os campos do modelo StoreProduct

Execute com:
    docker-compose exec web python scripts/populate_pastita_menu_complete.py
"""
import os
import sys
import django

# Setup Django
if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
    django.setup()

from decimal import Decimal
from django.utils.text import slugify
from apps.stores.models import (
    Store, StoreCategory, StoreProduct, StoreProductType
)

# Configuração
S3_BASE_URL = "https://pastita-final.s3.sa-east-1.amazonaws.com/products/"
CATEGORY_IMAGE_URL = "https://pastita-final.s3.sa-east-1.amazonaws.com/categories/"

# =============================================================================
# TIPOS DE PRODUTO (Product Types)
# =============================================================================
PRODUCT_TYPES = [
    {
        "name": "Rondelli",
        "slug": "rondelli",
        "description": "Massas tipo rondelli recheadas artesanalmente",
        "icon": "🍝",
        "custom_fields": [
            {"name": "recheio_principal", "type": "text", "label": "Recheio Principal"},
            {"name": "peso_gramas", "type": "number", "label": "Peso (g)"},
        ]
    },
    {
        "name": "Molho",
        "slug": "molho",
        "description": "Molhos artesanais para acompanhar massas",
        "icon": "🥫",
        "custom_fields": [
            {"name": "volume_ml", "type": "number", "label": "Volume (ml)"},
            {"name": "ingredientes", "type": "text", "label": "Ingredientes Principais"},
        ]
    },
]

# =============================================================================
# CATEGORIAS
# =============================================================================
CATEGORIES = [
    {
        "name": "Rondelli",
        "slug": "rondelli",
        "description": "Deliciosas massas de rondelli recheadas com ingredientes selecionados. Disponíveis em vários sabores.",
        "sort_order": 1,
        "image": "rondelli.webp",
        "is_active": True,
    },
    {
        "name": "Molhos",
        "slug": "molhos",
        "description": "Molhos artesanais preparados com receitas tradicionais italianas. Perfeitos para acompanhar nossas massas.",
        "sort_order": 2,
        "image": "molhos.webp",
        "is_active": True,
    },
    {
        "name": "Promoções",
        "slug": "promocoes",
        "description": "Aproveite nossas ofertas especiais e combos!",
        "sort_order": 3,
        "image": "promocoes.webp",
        "is_active": True,
    },
]

# =============================================================================
# PRODUTOS COMPLETOS
# =============================================================================
PRODUCTS = [
    # ==================== RONDELLI ====================
    {
        "category_slug": "rondelli",
        "product_type_slug": "rondelli",
        "name": "Rondelli de Tomate Seco com Rúcula",
        "short_description": "Rondelli recheado com tomate seco e rúcula fresca",
        "description": "Delicioso rondelli recheado com uma combinação perfeita de tomates secos selecionados e rúcula fresca. Massa artesanal feita diariamente.",
        "price": Decimal("39.99"),
        "compare_at_price": Decimal("44.99"),  # Preço original (em promoção)
        "cost_price": Decimal("18.00"),  # Custo
        "image": "tomate.webp",
        "sku": "RON-TOM-RUC-001",
        "barcode": "7891234567891",
        "stock_quantity": 10,
        "low_stock_threshold": 3,
        "track_stock": True,
        "allow_backorder": False,
        "featured": True,
        "sort_order": 1,
        "weight": Decimal("0.500"),  # 500g
        "weight_unit": "kg",
        "dimensions": {"length": 20, "width": 15, "height": 5, "unit": "cm"},
        "meta_title": "Rondelli de Tomate Seco com Rúcula | Pastita",
        "meta_description": "Rondelli artesanal recheado com tomate seco e rúcula. Entrega rápida em São Paulo.",
        "tags": ["rondelli", "tomate-seco", "rucula", "vegetariano", "destaque"],
        "attributes": {
            "porcoes": "2 a 3 pessoas",
            "conservacao": "3 dias na geladeira",
            "preparo": "20 minutos no forno",
            "alergenos": ["gluten", "lactose"]
        },
        "type_attributes": {"recheio_principal": "Tomate Seco e Rúcula", "peso_gramas": 500},
    },
    {
        "category_slug": "rondelli",
        "product_type_slug": "rondelli",
        "name": "Rondelli de Frango com Queijo",
        "short_description": "Rondelli recheado com frango desfiado e queijo",
        "description": "Clássico rondelli de frango com queijo. Frango desfiado temperado com ervas finas e queijo derretido na massa.",
        "price": Decimal("39.99"),
        "compare_at_price": None,
        "cost_price": Decimal("17.50"),
        "image": "frango.webp",
        "sku": "RON-FRA-QUE-002",
        "barcode": "7891234567892",
        "stock_quantity": 10,
        "low_stock_threshold": 3,
        "track_stock": True,
        "allow_backorder": False,
        "featured": False,
        "sort_order": 2,
        "weight": Decimal("0.500"),
        "weight_unit": "kg",
        "dimensions": {"length": 20, "width": 15, "height": 5, "unit": "cm"},
        "meta_title": "Rondelli de Frango com Queijo | Pastita",
        "meta_description": "Rondelli artesanal de frango com queijo. Massa fresca entregue em São Paulo.",
        "tags": ["rondelli", "frango", "queijo", "classico"],
        "attributes": {
            "porcoes": "2 a 3 pessoas",
            "conservacao": "3 dias na geladeira",
            "preparo": "20 minutos no forno",
            "alergenos": ["gluten", "lactose"]
        },
        "type_attributes": {"recheio_principal": "Frango e Queijo", "peso_gramas": 500},
    },
    {
        "category_slug": "rondelli",
        "product_type_slug": "rondelli",
        "name": "Rondelli de Presunto e Queijo",
        "short_description": "Tradicional rondelli de presunto com queijo",
        "description": "O tradicional rondelli de presunto e queijo que todo mundo ama. Presunto de qualidade e queijo derretido.",
        "price": Decimal("39.99"),
        "compare_at_price": None,
        "cost_price": Decimal("17.00"),
        "image": "presunto-queijo.webp",
        "sku": "RON-PRE-QUE-003",
        "barcode": "7891234567893",
        "stock_quantity": 10,
        "low_stock_threshold": 3,
        "track_stock": True,
        "allow_backorder": False,
        "featured": True,
        "sort_order": 3,
        "weight": Decimal("0.500"),
        "weight_unit": "kg",
        "dimensions": {"length": 20, "width": 15, "height": 5, "unit": "cm"},
        "meta_title": "Rondelli de Presunto e Queijo | Pastita",
        "meta_description": "Tradicional rondelli de presunto e queijo. Massa artesanal entregue fresca.",
        "tags": ["rondelli", "presunto", "queijo", "tradicional", "destaque"],
        "attributes": {
            "porcoes": "2 a 3 pessoas",
            "conservacao": "3 dias na geladeira",
            "preparo": "20 minutos no forno",
            "alergenos": ["gluten", "lactose"]
        },
        "type_attributes": {"recheio_principal": "Presunto e Queijo", "peso_gramas": 500},
    },
    {
        "category_slug": "rondelli",
        "product_type_slug": "rondelli",
        "name": "Rondelli de Damasco e Nozes",
        "short_description": "Rondelli gourmet com damasco, nozes e queijo brie",
        "description": "Combinação sofisticada de damascos, nozes e queijo brie. Perfeito para ocasiões especiais.",
        "price": Decimal("42.99"),
        "compare_at_price": Decimal("47.99"),
        "cost_price": Decimal("20.00"),
        "image": "damasco.webp",
        "sku": "RON-DAM-NOZ-004",
        "barcode": "7891234567894",
        "stock_quantity": 10,
        "low_stock_threshold": 2,
        "track_stock": True,
        "allow_backorder": False,
        "featured": True,
        "sort_order": 4,
        "weight": Decimal("0.500"),
        "weight_unit": "kg",
        "dimensions": {"length": 20, "width": 15, "height": 5, "unit": "cm"},
        "meta_title": "Rondelli de Damasco e Nozes | Pastita",
        "meta_description": "Rondelli gourmet com damasco, nozes e brie. Massa artesanal premium.",
        "tags": ["rondelli", "damasco", "nozes", "brie", "gourmet", "premium"],
        "attributes": {
            "porcoes": "2 a 3 pessoas",
            "conservacao": "3 dias na geladeira",
            "preparo": "20 minutos no forno",
            "alergenos": ["gluten", "lactose", "nozes"]
        },
        "type_attributes": {"recheio_principal": "Damasco, Nozes e Brie", "peso_gramas": 500},
    },
    {
        "category_slug": "rondelli",
        "product_type_slug": "rondelli",
        "name": "Rondelli 4 Queijos",
        "short_description": "Rondelli recheado com quatro tipos de queijos",
        "description": "Para os amantes de queijo! Mussarela, parmesão, gorgonzola e cream cheese em uma combinação irresistível.",
        "price": Decimal("41.99"),
        "compare_at_price": None,
        "cost_price": Decimal("19.00"),
        "image": "4queijos.webp",
        "sku": "RON-4QUE-005",
        "barcode": "7891234567895",
        "stock_quantity": 10,
        "low_stock_threshold": 3,
        "track_stock": True,
        "allow_backorder": False,
        "featured": False,
        "sort_order": 5,
        "weight": Decimal("0.500"),
        "weight_unit": "kg",
        "dimensions": {"length": 20, "width": 15, "height": 5, "unit": "cm"},
        "meta_title": "Rondelli 4 Queijos | Pastita",
        "meta_description": "Rondelli com mussarela, parmesão, gorgonzola e cream cheese. Massa fresca.",
        "tags": ["rondelli", "queijo", "4-queijos", "cream-cheese"],
        "attributes": {
            "porcoes": "2 a 3 pessoas",
            "conservacao": "3 dias na geladeira",
            "preparo": "20 minutos no forno",
            "alergenos": ["gluten", "lactose"]
        },
        "type_attributes": {"recheio_principal": "4 Queijos", "peso_gramas": 500},
    },
    # ==================== MOLHOS ====================
    {
        "category_slug": "molhos",
        "product_type_slug": "molho",
        "name": "Molho de Tomate Artesanal",
        "short_description": "Molho de tomate caseiro com manjericão",
        "description": "Molho de tomate preparado artesanalmente com tomates selecionados, alho, cebola e manjericão fresco.",
        "price": Decimal("19.90"),
        "compare_at_price": Decimal("24.90"),
        "cost_price": Decimal("8.00"),
        "image": "molho-tomate.webp",
        "sku": "MOL-TOM-001",
        "barcode": "7891234567901",
        "stock_quantity": 10,
        "low_stock_threshold": 5,
        "track_stock": True,
        "allow_backorder": True,
        "featured": True,
        "sort_order": 1,
        "weight": Decimal("0.500"),
        "weight_unit": "kg",
        "dimensions": {"length": 10, "width": 10, "height": 12, "unit": "cm"},
        "meta_title": "Molho de Tomate Artesanal | Pastita",
        "meta_description": "Molho de tomate caseiro com manjericão fresco. 500ml.",
        "tags": ["molho", "tomate", "caseiro", "manjericao", "promocao"],
        "attributes": {
            "volume": "500ml",
            "conservacao": "7 dias na geladeira",
            "ingredientes": ["tomate", "manjericão", "alho", "cebola", "azeite"],
            "vegano": True
        },
        "type_attributes": {"volume_ml": 500, "ingredientes": "Tomate, Manjericão, Alho, Cebola"},
    },
    {
        "category_slug": "molhos",
        "product_type_slug": "molho",
        "name": "Molho Branco Cremoso",
        "short_description": "Molho branco cremoso tipo bechamel",
        "description": "Molho branco cremoso à base de leite, manteiga e noz-moscada. Perfeito para rondelli e lasanha.",
        "price": Decimal("16.90"),
        "compare_at_price": None,
        "cost_price": Decimal("6.50"),
        "image": "molho-branco.webp",
        "sku": "MOL-BRA-002",
        "barcode": "7891234567902",
        "stock_quantity": 10,
        "low_stock_threshold": 5,
        "track_stock": True,
        "allow_backorder": True,
        "featured": False,
        "sort_order": 2,
        "weight": Decimal("0.500"),
        "weight_unit": "kg",
        "dimensions": {"length": 10, "width": 10, "height": 12, "unit": "cm"},
        "meta_title": "Molho Branco Cremoso | Pastita",
        "meta_description": "Molho branco tipo bechamel cremoso. 500ml.",
        "tags": ["molho", "branco", "bechamel", "cremoso"],
        "attributes": {
            "volume": "500ml",
            "conservacao": "5 dias na geladeira",
            "ingredientes": ["leite", "manteiga", "noz-moscada", "farinha"],
            "vegetariano": True
        },
        "type_attributes": {"volume_ml": 500, "ingredientes": "Leite, Manteiga, Noz-moscada"},
    },
    {
        "category_slug": "molhos",
        "product_type_slug": "molho",
        "name": "Molho Pesto",
        "short_description": "Molho pesto tradicional italiano",
        "description": "Autêntico molho pesto feito com manjericão fresco, pinoli, queijo parmesão e azeite extra virgem.",
        "price": Decimal("24.90"),
        "compare_at_price": None,
        "cost_price": Decimal("12.00"),
        "image": "molho-pesto.webp",
        "sku": "MOL-PES-003",
        "barcode": "7891234567903",
        "stock_quantity": 10,
        "low_stock_threshold": 3,
        "track_stock": True,
        "allow_backorder": False,
        "featured": True,
        "sort_order": 3,
        "weight": Decimal("0.250"),
        "weight_unit": "kg",
        "dimensions": {"length": 8, "width": 8, "height": 10, "unit": "cm"},
        "meta_title": "Molho Pesto Artesanal | Pastita",
        "meta_description": "Molho pesto tradicional com manjericão fresco e pinoli. 250ml.",
        "tags": ["molho", "pesto", "manjericao", "pinoli", "italiano", "premium"],
        "attributes": {
            "volume": "250ml",
            "conservacao": "10 dias na geladeira",
            "ingredientes": ["manjericão", "pinoli", "parmesão", "azeite", "alho"],
            "vegetariano": True
        },
        "type_attributes": {"volume_ml": 250, "ingredientes": "Manjericão, Pinoli, Parmesão, Azeite"},
    },
    # ==================== KIT/PROMOÇÃO ====================
    {
        "category_slug": "promocoes",
        "product_type_slug": None,
        "name": "Kit Família Rondelli",
        "short_description": "2 rondellis + molho grátis - Economize R$ 20!",
        "description": "Kit especial para família: 2 rondellis de sua escolha + molho de tomate artesanal (500ml) GRÁTIS! Perfeito para o almoço de domingo.",
        "price": Decimal("69.90"),
        "compare_at_price": Decimal("89.88"),
        "cost_price": Decimal("35.00"),
        "image": "kit-familia.webp",
        "sku": "KIT-FAM-001",
        "barcode": "7891234567910",
        "stock_quantity": 10,
        "low_stock_threshold": 2,
        "track_stock": True,
        "allow_backorder": False,
        "featured": True,
        "sort_order": 1,
        "weight": Decimal("1.500"),
        "weight_unit": "kg",
        "dimensions": {"length": 30, "width": 25, "height": 10, "unit": "cm"},
        "meta_title": "Kit Família Rondelli + Molho Grátis | Pastita",
        "meta_description": "2 rondellis + molho grátis. Economize R$ 20! Entrega em São Paulo.",
        "tags": ["kit", "promocao", "familia", "economia", "combo", "destaque"],
        "attributes": {
            "conteudo": "2 rondellis + molho de tomate 500ml",
            "economia": "R$ 19.98",
            "porcoes": "4 a 6 pessoas"
        },
        "type_attributes": {},
    },
]


def populate_complete_menu():
    """Popula o cardápio completo da Pastita com todos os campos."""
    
    # Encontrar a loja Pastita
    store = Store.objects.filter(slug__icontains='pastita').first()
    if not store:
        store = Store.objects.filter(name__icontains='pastita').first()
    
    if not store:
        print("❌ ERRO: Loja Pastita não encontrada!")
        print("Lojas disponíveis:")
        for s in Store.objects.all():
            print(f"  - {s.name} (slug: {s.slug})")
        return False
    
    print(f"\n{'='*60}")
    print(f"🍝 POPULANDO CARDÁPIO - PASTITA")
    print(f"{'='*60}")
    print(f"Loja: {store.name}")
    print(f"ID: {store.id}")
    print(f"{'='*60}\n")
    
    # =============================================================================
    # 1. CRIAR TIPOS DE PRODUTO
    # =============================================================================
    print("📋 [1/4] Criando Tipos de Produto...")
    product_types = {}
    for type_data in PRODUCT_TYPES:
        product_type, created = StoreProductType.objects.update_or_create(
            store=store,
            slug=type_data["slug"],
            defaults={
                "name": type_data["name"],
                "description": type_data["description"],
                "icon": type_data["icon"],
                "custom_fields": type_data["custom_fields"],
                "is_active": True,
                "show_in_menu": True,
            }
        )
        product_types[type_data["slug"]] = product_type
        icon = "✨" if created else "🔄"
        print(f"  {icon} {product_type.name} {'(criado)' if created else '(atualizado)'}")
    
    # =============================================================================
    # 2. CRIAR CATEGORIAS
    # =============================================================================
    print("\n📁 [2/4] Criando Categorias...")
    categories = {}
    for cat_data in CATEGORIES:
        image_url = f"{CATEGORY_IMAGE_URL}{cat_data['image']}" if cat_data.get('image') else ""
        category, created = StoreCategory.objects.update_or_create(
            store=store,
            slug=cat_data["slug"],
            defaults={
                "name": cat_data["name"],
                "description": cat_data["description"],
                "image_url": image_url,
                "sort_order": cat_data["sort_order"],
                "is_active": cat_data["is_active"],
            }
        )
        categories[cat_data["slug"]] = category
        icon = "✨" if created else "🔄"
        print(f"  {icon} {category.name} {'(criada)' if created else '(atualizada)'}")
    
    # =============================================================================
    # 3. CRIAR PRODUTOS COMPLETOS
    # =============================================================================
    print("\n🍝 [3/4] Criando Produtos (com todos os campos)...")
    created_count = 0
    updated_count = 0
    
    for prod_data in PRODUCTS:
        category = categories.get(prod_data["category_slug"])
        product_type = product_types.get(prod_data["product_type_slug"]) if prod_data.get("product_type_slug") else None
        
        slug = slugify(prod_data["name"])
        image_url = f"{S3_BASE_URL}{prod_data['image']}"
        
        # Campos do modelo StoreProduct
        defaults = {
            # Relacionamentos
            "category": category,
            "product_type": product_type,
            
            # Basic Info
            "name": prod_data["name"],
            "slug": slug,
            "description": prod_data["description"],
            "short_description": prod_data["short_description"],
            
            # SKU e Barcode
            "sku": prod_data["sku"],
            "barcode": prod_data.get("barcode", ""),
            
            # Preços
            "price": prod_data["price"],
            "compare_at_price": prod_data.get("compare_at_price"),
            "cost_price": prod_data.get("cost_price"),
            
            # Estoque (completo)
            "track_stock": prod_data.get("track_stock", True),
            "stock_quantity": prod_data.get("stock_quantity", 10),
            "low_stock_threshold": prod_data.get("low_stock_threshold", 5),
            "allow_backorder": prod_data.get("allow_backorder", False),
            
            # Status
            "status": StoreProduct.ProductStatus.ACTIVE,
            "featured": prod_data.get("featured", False),
            "sort_order": prod_data.get("sort_order", 0),
            
            # Imagens
            "main_image_url": image_url,
            
            # SEO
            "meta_title": prod_data.get("meta_title", prod_data["name"]),
            "meta_description": prod_data.get("meta_description", prod_data["short_description"]),
            
            # Físico
            "weight": prod_data.get("weight"),
            "weight_unit": prod_data.get("weight_unit", "kg"),
            "dimensions": prod_data.get("dimensions", {}),
            
            # Atributos e Tags
            "attributes": prod_data.get("attributes", {}),
            "tags": prod_data.get("tags", []),
            
            # Type Attributes
            "type_attributes": prod_data.get("type_attributes", {}),
        }
        
        # Tentar atualizar por SKU primeiro, depois por slug
        try:
            product = StoreProduct.objects.get(store=store, sku=prod_data["sku"])
            created = False
            for key, value in defaults.items():
                setattr(product, key, value)
            product.save()
        except StoreProduct.DoesNotExist:
            try:
                product = StoreProduct.objects.get(store=store, slug=slug)
                created = False
                for key, value in defaults.items():
                    setattr(product, key, value)
                product.save()
            except StoreProduct.DoesNotExist:
                product = StoreProduct.objects.create(store=store, **defaults)
                created = True
        
        if created:
            created_count += 1
            icon = "✨"
            status = "CRIADO"
        else:
            updated_count += 1
            icon = "🔄"
            status = "ATUALIZADO"
        
        print(f"  {icon} {product.name}")
        print(f"     💰 R$ {product.price} | 📦 Estoque: {product.stock_quantity} | 📊 SKU: {product.sku}")
        if product.compare_at_price:
            discount = int(((product.compare_at_price - product.price) / product.compare_at_price) * 100)
            print(f"     🏷️  PROMOÇÃO: {discount}% OFF (de R$ {product.compare_at_price})")
        if product.featured:
            print(f"     ⭐ DESTAQUE")
        print()
    
    # =============================================================================
    # 4. RESUMO FINAL
    # =============================================================================
    print(f"\n{'='*60}")
    print("✅ CARDÁPIO POPULADO COM SUCESSO!")
    print(f"{'='*60}")
    
    # Estatísticas
    total_product_types = StoreProductType.objects.filter(store=store).count()
    total_categories = StoreCategory.objects.filter(store=store).count()
    total_products = StoreProduct.objects.filter(store=store).count()
    total_featured = StoreProduct.objects.filter(store=store, featured=True).count()
    total_on_sale = StoreProduct.objects.filter(store=store, compare_at_price__isnull=False).count()
    
    print(f"\n📊 ESTATÍSTICAS:")
    print(f"  • Tipos de Produto: {total_product_types}")
    print(f"  • Categorias: {total_categories}")
    print(f"  • Produtos: {total_products}")
    print(f"  • Produtos em Destaque: {total_featured}")
    print(f"  • Produtos em Promoção: {total_on_sale}")
    
    print(f"\n📝 RESUMO DA OPERAÇÃO:")
    print(f"  • Produtos CRIADOS: {created_count}")
    print(f"  • Produtos ATUALIZADOS: {updated_count}")
    
    # Produtos com estoque baixo
    low_stock = StoreProduct.objects.filter(
        store=store, 
        track_stock=True, 
        stock_quantity__lte=models.F('low_stock_threshold')
    )
    if low_stock.exists():
        print(f"\n⚠️  ALERTA DE ESTOQUE BAIXO:")
        for p in low_stock:
            print(f"  • {p.name}: {p.stock_quantity} unidades")
    
    print(f"\n{'='*60}")
    print("🚀 PRODUTOS PRONTOS PARA VENDA!")
    print(f"{'='*60}")
    
    return True


if __name__ == '__main__':
    from django.db import models
    success = populate_complete_menu()
    sys.exit(0 if success else 1)
