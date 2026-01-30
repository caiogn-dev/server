"""
Data migration to migrate Pastita data to the unified stores system.

This migration:
1. Creates the Pastita store if it doesn't exist
2. Creates product types (Molho, Carne, Rondelli) with custom field definitions
3. Migrates Produto, Molho, Carne, Rondelli to StoreProduct with type_attributes
4. Migrates Combo to StoreCombo with StoreComboItem
5. Migrates Pedido to StoreOrder with StoreOrderItem

After this migration, the Pastita-3D frontend should use:
- /api/v1/stores/pastita/catalog/
- /api/v1/stores/pastita/cart/
- /api/v1/stores/pastita/checkout/
"""
from django.db import migrations
from django.utils.text import slugify
import uuid


def migrate_pastita_data(apps, schema_editor):
    """Migrate all Pastita data to the unified stores system."""
    
    # Get models
    Store = apps.get_model('stores', 'Store')
    StoreProductType = apps.get_model('stores', 'StoreProductType')
    StoreProduct = apps.get_model('stores', 'StoreProduct')
    StoreCombo = apps.get_model('stores', 'StoreCombo')
    StoreComboItem = apps.get_model('stores', 'StoreComboItem')
    StoreOrder = apps.get_model('stores', 'StoreOrder')
    StoreOrderItem = apps.get_model('stores', 'StoreOrderItem')
    StoreOrderComboItem = apps.get_model('stores', 'StoreOrderComboItem')
    
    # Pastita models
    try:
        Produto = apps.get_model('pastita', 'Produto')
        Molho = apps.get_model('pastita', 'Molho')
        Carne = apps.get_model('pastita', 'Carne')
        Rondelli = apps.get_model('pastita', 'Rondelli')
        Combo = apps.get_model('pastita', 'Combo')
        Pedido = apps.get_model('pastita', 'Pedido')
        ItemPedido = apps.get_model('pastita', 'ItemPedido')
        ItemComboPedido = apps.get_model('pastita', 'ItemComboPedido')
    except LookupError:
        # Pastita app not installed, skip migration
        print("Pastita app not found, skipping data migration")
        return
    
    # Get or create Pastita store
    pastita_store = Store.objects.filter(slug='pastita').first()
    if not pastita_store:
        print("Pastita store not found, skipping data migration")
        return
    
    print(f"Migrating data for store: {pastita_store.name}")
    
    # ==========================================================================
    # 1. Create Product Types with custom field definitions
    # ==========================================================================
    
    # Molho (Sauce) type
    molho_type, _ = StoreProductType.objects.get_or_create(
        store=pastita_store,
        slug='molho',
        defaults={
            'name': 'Molho',
            'description': 'Molhos artesanais para acompanhar suas massas',
            'icon': '🍝',
            'custom_fields': [
                {
                    'name': 'tipo',
                    'label': 'Tipo de Molho',
                    'type': 'select',
                    'required': True,
                    'options': [
                        {'value': '4queijos', 'label': '4 Queijos'},
                        {'value': 'sugo', 'label': 'Sugo'},
                        {'value': 'branco', 'label': 'Molho Branco'},
                        {'value': 'pesto', 'label': 'Pesto'},
                        {'value': 'bolonhesa', 'label': 'Bolonhesa'},
                        {'value': 'carbonara', 'label': 'Carbonara'},
                    ]
                },
                {
                    'name': 'quantidade',
                    'label': 'Quantidade',
                    'type': 'text',
                    'required': True,
                    'placeholder': 'Ex: 150g, 300g'
                }
            ],
            'sort_order': 1,
            'is_active': True,
            'show_in_menu': True
        }
    )
    print(f"  Created/found product type: {molho_type.name}")
    
    # Carne (Meat) type
    carne_type, _ = StoreProductType.objects.get_or_create(
        store=pastita_store,
        slug='carne',
        defaults={
            'name': 'Carne',
            'description': 'Carnes selecionadas para acompanhar suas massas',
            'icon': '🥩',
            'custom_fields': [
                {
                    'name': 'tipo',
                    'label': 'Tipo de Carne',
                    'type': 'select',
                    'required': True,
                    'options': [
                        {'value': 'isca_file', 'label': 'Iscas de Filé'},
                        {'value': 'frango_grelhado', 'label': 'Frango Grelhado'},
                        {'value': 'carne_moida', 'label': 'Carne Moída'},
                        {'value': 'linguica_calabresa', 'label': 'Linguiça Calabresa'},
                        {'value': 'bacon', 'label': 'Bacon'},
                        {'value': 'costela', 'label': 'Costela Desfiada'},
                        {'value': 'picanha', 'label': 'Picanha'},
                    ]
                },
                {
                    'name': 'quantidade',
                    'label': 'Quantidade',
                    'type': 'text',
                    'required': True,
                    'placeholder': 'Ex: 200g, 300g'
                }
            ],
            'sort_order': 2,
            'is_active': True,
            'show_in_menu': True
        }
    )
    print(f"  Created/found product type: {carne_type.name}")
    
    # Rondelli (Pasta) type
    rondelli_type, _ = StoreProductType.objects.get_or_create(
        store=pastita_store,
        slug='rondelli',
        defaults={
            'name': 'Rondelli',
            'description': 'Massas artesanais recheadas',
            'icon': '🍜',
            'custom_fields': [
                {
                    'name': 'categoria',
                    'label': 'Categoria',
                    'type': 'select',
                    'required': True,
                    'options': [
                        {'value': 'classicos', 'label': 'Clássicos'},
                        {'value': 'gourmet', 'label': 'Gourmet'},
                    ]
                },
                {
                    'name': 'sabor',
                    'label': 'Sabor',
                    'type': 'select',
                    'required': True,
                    'options': [
                        {'value': 'presunto_e_queijo', 'label': 'Presunto e Queijo'},
                        {'value': 'calabresa_com_requeijao', 'label': 'Calabresa com Requeijão'},
                        {'value': 'frango_requeijao_mucarela', 'label': 'Frango, Requeijão e Muçarela'},
                        {'value': 'linguica_toscana_erva_doce', 'label': 'Linguiça Toscana e Erva-Doce'},
                        {'value': 'queijo_brocolis', 'label': 'Queijo e Brócolis'},
                        {'value': 'tomate_seco_rucula', 'label': 'Tomate Seco com Rúcula'},
                        {'value': '4queijos', 'label': '4 Queijos'},
                        {'value': 'queijos_manjericao', 'label': 'Queijos com Manjericão'},
                        {'value': 'palmito', 'label': 'Palmito'},
                        {'value': 'bacalhau_cremoso', 'label': 'Bacalhau Cremoso'},
                        {'value': 'queijo_brie_damasco_castanha', 'label': 'Queijo Brie, Damasco e Castanha'},
                        {'value': 'chambari_especiarias', 'label': 'Chambari com Especiarias'},
                        {'value': 'camarao_catupiry', 'label': 'Camarão com Catupiry'},
                        {'value': 'carne_seca_abobora', 'label': 'Carne Seca com Abóbora'},
                    ]
                },
                {
                    'name': 'quantidade',
                    'label': 'Quantidade',
                    'type': 'text',
                    'required': True,
                    'placeholder': 'Ex: 500g, 1kg'
                }
            ],
            'sort_order': 3,
            'is_active': True,
            'show_in_menu': True
        }
    )
    print(f"  Created/found product type: {rondelli_type.name}")
    
    # ==========================================================================
    # 2. Migrate Molho products
    # ==========================================================================
    
    molho_count = 0
    for molho in Molho.objects.all():
        # Check if already migrated
        existing = StoreProduct.objects.filter(
            store=pastita_store,
            slug=slugify(f"molho-{molho.tipo}-{molho.quantidade}")
        ).first()
        
        if not existing:
            product = StoreProduct.objects.create(
                store=pastita_store,
                product_type=molho_type,
                name=molho.nome,
                slug=slugify(f"molho-{molho.tipo}-{molho.quantidade}"),
                description=molho.descricao,
                price=molho.preco,
                stock_quantity=molho.estoque,
                status='active' if molho.ativo else 'inactive',
                type_attributes={
                    'tipo': molho.tipo,
                    'quantidade': molho.quantidade
                }
            )
            molho_count += 1
    
    print(f"  Migrated {molho_count} Molho products")
    
    # ==========================================================================
    # 3. Migrate Carne products
    # ==========================================================================
    
    carne_count = 0
    for carne in Carne.objects.all():
        existing = StoreProduct.objects.filter(
            store=pastita_store,
            slug=slugify(f"carne-{carne.tipo}-{carne.quantidade}")
        ).first()
        
        if not existing:
            product = StoreProduct.objects.create(
                store=pastita_store,
                product_type=carne_type,
                name=carne.nome,
                slug=slugify(f"carne-{carne.tipo}-{carne.quantidade}"),
                description=carne.descricao,
                price=carne.preco,
                stock_quantity=carne.estoque,
                status='active' if carne.ativo else 'inactive',
                type_attributes={
                    'tipo': carne.tipo,
                    'quantidade': carne.quantidade
                }
            )
            carne_count += 1
    
    print(f"  Migrated {carne_count} Carne products")
    
    # ==========================================================================
    # 4. Migrate Rondelli products
    # ==========================================================================
    
    rondelli_count = 0
    for rondelli in Rondelli.objects.all():
        existing = StoreProduct.objects.filter(
            store=pastita_store,
            slug=slugify(f"rondelli-{rondelli.sabor}-{rondelli.quantidade}")
        ).first()
        
        if not existing:
            product = StoreProduct.objects.create(
                store=pastita_store,
                product_type=rondelli_type,
                name=rondelli.nome,
                slug=slugify(f"rondelli-{rondelli.sabor}-{rondelli.quantidade}"),
                description=rondelli.descricao,
                price=rondelli.preco,
                stock_quantity=rondelli.estoque,
                status='active' if rondelli.ativo else 'inactive',
                type_attributes={
                    'categoria': rondelli.categoria,
                    'sabor': rondelli.sabor,
                    'quantidade': rondelli.quantidade
                }
            )
            rondelli_count += 1
    
    print(f"  Migrated {rondelli_count} Rondelli products")
    
    # ==========================================================================
    # 5. Migrate Combos
    # ==========================================================================
    
    combo_count = 0
    for combo in Combo.objects.all():
        existing = StoreCombo.objects.filter(
            store=pastita_store,
            slug=slugify(combo.nome)
        ).first()
        
        if not existing:
            store_combo = StoreCombo.objects.create(
                store=pastita_store,
                name=combo.nome,
                slug=slugify(combo.nome),
                description=combo.descricao,
                price=combo.preco,
                compare_at_price=combo.preco_original,
                is_active=combo.ativo,
                featured=combo.destaque,
                stock_quantity=combo.estoque
            )
            combo_count += 1
    
    print(f"  Migrated {combo_count} Combos")
    
    # ==========================================================================
    # 6. Migrate Pedidos (Orders)
    # ==========================================================================
    
    order_count = 0
    for pedido in Pedido.objects.all():
        # Check if already migrated by payment_id
        if pedido.payment_id:
            existing = StoreOrder.objects.filter(payment_id=pedido.payment_id).first()
            if existing:
                continue
        
        # Generate order number
        order_number = f"PAS{pedido.id:06d}"
        
        # Map status
        status_map = {
            'pendente': 'pending',
            'processando': 'processing',
            'aprovado': 'paid',
            'pago': 'paid',
            'preparando': 'preparing',
            'enviado': 'shipped',
            'entregue': 'delivered',
            'cancelado': 'cancelled',
            'falhou': 'failed',
            'reembolsado': 'refunded',
        }
        
        store_order = StoreOrder.objects.create(
            store=pastita_store,
            order_number=order_number,
            customer_id=pedido.usuario_id,
            customer_name=pedido.cliente_nome or '',
            customer_email=pedido.cliente_email or '',
            customer_phone=pedido.cliente_telefone or '',
            status=status_map.get(pedido.status, 'pending'),
            payment_status='paid' if pedido.status in ['aprovado', 'pago', 'preparando', 'enviado', 'entregue'] else 'pending',
            subtotal=pedido.subtotal,
            discount=pedido.desconto,
            coupon_code=pedido.cupom_codigo or '',
            delivery_fee=pedido.taxa_entrega,
            total=pedido.total,
            payment_id=pedido.payment_id or '',
            payment_preference_id=pedido.preference_id or '',
            delivery_method='delivery',
            delivery_address=pedido.endereco_entrega or {},
            customer_notes=pedido.observacoes or '',
            paid_at=pedido.data_pagamento
        )
        
        # Migrate order items
        for item in pedido.itens.all():
            StoreOrderItem.objects.create(
                order=store_order,
                product_name=item.nome_produto,
                unit_price=item.preco_unitario,
                quantity=item.quantidade,
                subtotal=item.preco_unitario * item.quantidade
            )
        
        # Migrate combo items
        for combo_item in pedido.combos.all():
            StoreOrderComboItem.objects.create(
                order=store_order,
                combo_name=combo_item.nome_combo,
                unit_price=combo_item.preco_unitario,
                quantity=combo_item.quantidade,
                subtotal=combo_item.preco_unitario * combo_item.quantidade
            )
        
        order_count += 1
    
    print(f"  Migrated {order_count} Orders")
    print("Pastita data migration complete!")


def reverse_migration(apps, schema_editor):
    """Reverse the migration - delete migrated data."""
    Store = apps.get_model('stores', 'Store')
    StoreProductType = apps.get_model('stores', 'StoreProductType')
    StoreProduct = apps.get_model('stores', 'StoreProduct')
    StoreCombo = apps.get_model('stores', 'StoreCombo')
    StoreOrder = apps.get_model('stores', 'StoreOrder')
    
    pastita_store = Store.objects.filter(slug='pastita').first()
    if pastita_store:
        # Delete in reverse order of dependencies
        StoreOrder.objects.filter(store=pastita_store, order_number__startswith='PAS').delete()
        StoreCombo.objects.filter(store=pastita_store).delete()
        StoreProduct.objects.filter(store=pastita_store).delete()
        StoreProductType.objects.filter(store=pastita_store, slug__in=['molho', 'carne', 'rondelli']).delete()
        print("Reversed Pastita data migration")


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0004_add_specialized_products_and_wishlist'),
    ]

    operations = [
        migrations.RunPython(migrate_pastita_data, reverse_migration),
    ]
