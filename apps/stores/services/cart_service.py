"""
Cart Service - Unified cart management for all stores.
Handles cart operations with stock validation and atomic updates.
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import F

from apps.stores.models import (
    Store, StoreCart, StoreCartItem, StoreCartComboItem,
    StoreProduct, StoreProductVariant, StoreCombo
)

logger = logging.getLogger(__name__)


class CartService:
    """Service for managing store carts."""
    
    @staticmethod
    def get_cart(store: Store, user=None, session_key=None) -> StoreCart:
        """Get or create a cart for a user or session."""
        if user and user.is_authenticated:
            cart = StoreCart.get_or_create_for_user(store, user)
            
            # Merge any session cart if exists
            if session_key:
                session_cart = StoreCart.objects.filter(
                    store=store,
                    session_key=session_key,
                    user__isnull=True,
                    is_active=True
                ).first()
                
                if session_cart and session_cart.items.exists():
                    cart.merge_with(session_cart)
            
            return cart
        elif session_key:
            return StoreCart.get_or_create_for_session(store, session_key)
        else:
            raise ValueError("Either user or session_key must be provided")
    
    @staticmethod
    def get_or_create_cart(store: Store, user=None, session_key=None) -> StoreCart:
        """Alias for get_cart - get or create a cart for a user or session."""
        return CartService.get_cart(store, user, session_key)
    
    @staticmethod
    @transaction.atomic
    def add_item(
        cart: StoreCart,
        product_id,
        quantity: int = 1,
        variant_id=None,
        options: dict = None,
        notes: str = ''
    ) -> StoreCartItem:
        """Add an item to the cart by product_id."""
        product = StoreProduct.objects.get(id=product_id, store=cart.store)
        variant = None
        if variant_id:
            variant = StoreProductVariant.objects.get(id=variant_id, product=product)
        elif product.variants.filter(is_active=True).exists():
            # Produto com sabores/variantes exige a escolha — sem isto o pedido
            # chegava na loja como "Molho" sem dizer qual (CE-2607306092).
            raise ValueError(
                f'Escolha uma opção de "{product.name}" antes de adicionar ao carrinho.'
            )
        return CartService.add_product(cart, product, quantity, variant, options=options, notes=notes)
    
    @staticmethod
    @transaction.atomic
    def add_product(
        cart: StoreCart,
        product: StoreProduct,
        quantity: int = 1,
        variant: StoreProductVariant = None,
        options: dict = None,
        notes: str = ''
    ) -> StoreCartItem:
        """Add a product to the cart with stock validation."""
        
        # Validate stock with row locking to prevent race conditions
        if product.track_stock:
            # Lock the product row to prevent concurrent modifications
            locked_product = StoreProduct.objects.select_for_update().get(id=product.id)
            available = locked_product.stock_quantity
            
            if variant and variant.stock_quantity is not None:
                # Lock the variant row as well
                locked_variant = StoreProductVariant.objects.select_for_update().get(id=variant.id)
                available = locked_variant.stock_quantity
            
            # Check existing quantity in cart
            existing_item = cart.items.filter(product=product, variant=variant).first()
            existing_qty = existing_item.quantity if existing_item else 0
            
            if existing_qty + quantity > available:
                raise ValueError(
                    f"Estoque insuficiente. Disponível: {available}, "
                    f"No carrinho: {existing_qty}, Solicitado: {quantity}"
                )
        
        # Add or update item
        if existing_item := cart.items.filter(product=product, variant=variant).first():
            existing_item.quantity += quantity
            if options:
                existing_item.options = {**existing_item.options, **options}
            if notes:
                existing_item.notes = notes
            existing_item.save()
            return existing_item
        else:
            return StoreCartItem.objects.create(
                cart=cart,
                product=product,
                variant=variant,
                quantity=quantity,
                options=options or {},
                notes=notes
            )
    
    # Slug do combo que define o preço-base da salada montada. Mesmo contrato do
    # storefront (BUILDER_COMBO_SLUG em Cardapio.jsx).
    BUILDER_COMBO_SLUG = 'monte-sua-salada'
    # Papel cujos itens não somam ao preço (molho é cortesia) — espelha a regra do
    # front em CartContext.addSaladToCart.
    FREE_INGREDIENT_ROLES = {'molho'}

    @staticmethod
    def price_custom_salad(store, customizations: dict) -> Decimal:
        """Preço da salada montada, derivado SÓ do banco.

        base (preço do combo `monte-sua-salada` da loja, 0 se não existir)
        + soma de StoreProduct.price de cada ingrediente cujo papel não é gratuito.

        Ingredientes são resolvidos por id E filtrados por loja: id de produto de
        outro tenant é descartado em vez de somar o preço dele.
        """
        base = Decimal('0.00')
        builder = StoreCombo.objects.filter(
            store=store, slug=CartService.BUILDER_COMBO_SLUG
        ).values_list('price', flat=True).first()
        if builder is not None:
            base = Decimal(str(builder))

        ingredientes = (customizations or {}).get('ingredients') or []
        cobraveis = []
        for item in ingredientes:
            if not isinstance(item, dict):
                continue  # formato legado (string): sem id, não dá para precificar
            if str(item.get('role') or '').strip().lower() in CartService.FREE_INGREDIENT_ROLES:
                continue
            pid = item.get('id') or item.get('product_id')
            if pid:
                cobraveis.append(str(pid))

        if not cobraveis:
            return base

        # Uma query só. A chave é str(id) para casar com o que veio no payload,
        # e a lista preserva repetições (2x tomate soma duas vezes).
        mapa = {
            str(pid): preco
            for pid, preco in StoreProduct.objects.filter(
                store=store, id__in=cobraveis
            ).values_list('id', 'price')
        }
        total = base
        for pid in cobraveis:
            preco = mapa.get(pid)
            if preco is None:
                logger.warning(
                    "Ingrediente %s não pertence à loja %s — ignorado no preço", pid, store.slug
                )
                continue
            total += Decimal(str(preco))
        return total

    @staticmethod
    @transaction.atomic
    def add_combo(
        cart: StoreCart,
        combo,  # StoreCombo | None — None means virtual combo (e.g. salad builder)
        quantity: int = 1,
        customizations: dict = None,
        notes: str = '',
        combo_name: str = '',
        unit_price=None,
        group_selections: dict = None,
    ) -> StoreCartComboItem:
        """Add a combo to the cart.

        Supports real combos (combo FK) and virtual combos (combo=None,
        combo_name and unit_price required).  Virtual combos are identified
        by the ``is_virtual`` flag in customizations.
        """

        if combo is not None:
            # Real combo — validate stock
            if combo.track_stock and combo.stock_quantity < quantity:
                raise ValueError(f"Estoque insuficiente para o combo. Disponível: {combo.stock_quantity}")
            effective_name = combo_name or combo.name
            # PREÇO É DERIVADO, NUNCA ACEITO DO CLIENTE. Antes esta linha era
            # `unit_price if unit_price is not None else combo.price`, o que deixava
            # o corpo da requisição sobrescrever o preço cadastrado do combo.
            if unit_price is not None and Decimal(str(unit_price)) != combo.price:
                logger.warning(
                    "Combo %s: unit_price do cliente (%s) ignorado; usando o cadastrado (%s)",
                    combo.id, unit_price, combo.price,
                )
            effective_price = combo.price
        else:
            # Virtual combo (salad builder, etc.)
            if not combo_name:
                raise ValueError("combo_name is required for virtual combos")
            # Recalcula a partir dos ingredientes persistidos. O unit_price que vem
            # do cliente serve só para detectar divergência (UI desatualizada ou
            # adulteração) — nunca para definir o valor cobrado.
            effective_price = CartService.price_custom_salad(cart.store, customizations)
            if unit_price is not None:
                try:
                    esperado = Decimal(str(unit_price))
                    if abs(esperado - effective_price) > Decimal('0.01'):
                        logger.warning(
                            "price_mismatch store=%s enviado=%s servidor=%s customizations=%s",
                            cart.store.slug, esperado, effective_price, customizations,
                        )
                except (TypeError, ValueError, ArithmeticError):
                    logger.warning("unit_price ilegível do cliente: %r", unit_price)
            if effective_price <= 0:
                raise ValueError("Não foi possível calcular o preço da salada montada")
            effective_name = combo_name

        customizations = customizations or {}
        group_selections = group_selections or customizations.get('selections') or customizations.get('group_selections') or {}

        # For real combos try to merge with existing entry; virtual combos always create new
        existing = None
        if combo is not None:
            existing = cart.combo_items.filter(
                combo=combo,
                group_selections=group_selections,
            ).first()

        if existing:
            existing.quantity += quantity
            if customizations:
                existing.customizations = {**existing.customizations, **customizations}
            if group_selections:
                existing.group_selections = group_selections
            if notes:
                existing.notes = notes
            existing.save()
            return existing
        else:
            return StoreCartComboItem.objects.create(
                cart=cart,
                combo=combo,
                combo_name=effective_name,
                unit_price=effective_price,
                quantity=quantity,
                group_selections=group_selections,
                customizations=customizations,
                notes=notes,
            )
    
    @staticmethod
    @transaction.atomic
    def update_item_quantity(cart_or_item, item_id_or_quantity=None, quantity=None) -> StoreCartItem:
        """
        Update item quantity with stock validation.
        
        Supports two calling conventions:
        - update_item_quantity(item, quantity) - direct item update
        - update_item_quantity(cart, item_id, quantity) - lookup item by ID
        """
        # Determine calling convention
        if isinstance(cart_or_item, StoreCartItem):
            # Old style: update_item_quantity(item, quantity)
            item = cart_or_item
            qty = item_id_or_quantity
        else:
            # New style: update_item_quantity(cart, item_id, quantity)
            cart = cart_or_item
            item_id = item_id_or_quantity
            qty = quantity
            try:
                item = StoreCartItem.objects.get(id=item_id, cart=cart)
            except StoreCartItem.DoesNotExist:
                raise ValueError(f"Item {item_id} not found in cart")
        
        if qty <= 0:
            item.delete()
            return None
        
        product = item.product
        if product.track_stock:
            available = product.stock_quantity
            if item.variant and item.variant.stock_quantity is not None:
                available = item.variant.stock_quantity
            
            if qty > available:
                raise ValueError(f"Estoque insuficiente. Disponível: {available}")
        
        item.quantity = qty
        item.save()
        return item
    
    @staticmethod
    @transaction.atomic
    def update_combo_quantity(item: StoreCartComboItem, quantity: int) -> StoreCartComboItem:
        """Update combo item quantity."""
        if quantity <= 0:
            item.delete()
            return None
        
        if item.combo and item.combo.track_stock and quantity > item.combo.stock_quantity:
            raise ValueError(f"Estoque insuficiente. Disponível: {item.combo.stock_quantity}")
        
        item.quantity = quantity
        item.save()
        return item
    
    @staticmethod
    def remove_item(cart_or_item, item_id=None):
        """
        Remove an item from the cart (product or combo).

        Supports two calling conventions:
        - remove_item(item) - direct item deletion (StoreCartItem or StoreCartComboItem)
        - remove_item(cart, item_id) - lookup item by ID and delete; tries
          StoreCartItem first, then StoreCartComboItem as fallback so a single
          endpoint handles both types.
        """
        if isinstance(cart_or_item, (StoreCartItem, StoreCartComboItem)):
            # Old style: remove_item(item)
            cart_or_item.delete()
            return

        # New style: remove_item(cart, item_id)
        cart = cart_or_item
        try:
            StoreCartItem.objects.get(id=item_id, cart=cart).delete()
            return
        except StoreCartItem.DoesNotExist:
            pass

        # Fallback: try combo item
        try:
            StoreCartComboItem.objects.get(id=item_id, cart=cart).delete()
        except StoreCartComboItem.DoesNotExist:
            pass  # Already removed or invalid id
    
    @staticmethod
    def remove_combo(item: StoreCartComboItem):
        """Remove a combo from the cart."""
        item.delete()
    
    @staticmethod
    def clear_cart(cart: StoreCart):
        """Clear all items from the cart."""
        cart.items.all().delete()
        cart.combo_items.all().delete()
    
    @staticmethod
    def get_cart_summary(cart: StoreCart) -> dict:
        """Get cart summary with totals."""
        items = []
        subtotal = Decimal('0.00')
        item_count = 0

        # Regular items
        for item in cart.items.select_related('product', 'variant').all():
            item_data = {
                'id': str(item.id),
                'type': 'product',
                'product_id': str(item.product.id),
                'product_name': item.product.name,
                'variant_id': str(item.variant.id) if item.variant else None,
                'variant_name': item.variant.name if item.variant else None,
                'quantity': item.quantity,
                'unit_price': float(item.unit_price),
                'subtotal': float(item.subtotal),
                'options': item.options,
                'notes': item.notes,
                'image_url': item.product.get_main_image_url(),
            }
            items.append(item_data)
            subtotal += item.subtotal
            item_count += item.quantity

        # Combo items
        for item in cart.combo_items.select_related('combo').all():
            item_data = {
                'id': str(item.id),
                'type': 'combo',
                'combo_id': str(item.combo.id) if item.combo else None,
                'combo_name': item.effective_name,
                'quantity': item.quantity,
                'unit_price': float(item.effective_price),
                'subtotal': float(item.subtotal),
                'customizations': item.customizations,
                'notes': item.notes,
                'image_url': item.combo.get_image_url() if item.combo else None,
            }
            items.append(item_data)
            subtotal += item.subtotal
            item_count += item.quantity

        return {
            'id': str(cart.id),
            'store_id': str(cart.store.id),
            'store_name': cart.store.name,
            'items': items,
            'item_count': item_count,
            'subtotal': float(subtotal),
            'is_empty': len(items) == 0,
        }
    
    @staticmethod
    @transaction.atomic
    def validate_stock_for_checkout(cart: StoreCart) -> list:
        """
        Validate all items have sufficient stock for checkout.
        Returns list of errors if any.
        
        IMPORTANT: Uses select_for_update() to prevent race conditions.
        This locks the product/variant rows until the transaction completes,
        preventing overselling when multiple checkouts happen simultaneously.
        """
        errors = []

        # Load items once to avoid redundant queries
        cart_items = list(cart.items.all())
        product_ids = [item.product_id for item in cart_items]
        variant_ids = [item.variant_id for item in cart_items if item.variant_id]
        combo_ids = [item.combo_id for item in cart.combo_items.all() if item.combo_id]
        
        # Lock products for update to prevent race conditions
        locked_products = {
            p.id: p for p in StoreProduct.objects.select_for_update().filter(id__in=product_ids)
        }
        locked_variants = {
            v.id: v for v in StoreProductVariant.objects.select_for_update().filter(id__in=variant_ids)
        } if variant_ids else {}
        locked_combos = {
            c.id: c for c in StoreCombo.objects.select_for_update().filter(id__in=combo_ids)
        } if combo_ids else {}
        
        for item in cart.items.select_related('product', 'variant').all():
            # Use the locked product to check stock
            product = locked_products.get(item.product_id) or item.product
            
            if not product.is_in_stock:
                errors.append({
                    'item_id': str(item.id),
                    'product_name': product.name,
                    'error': 'Produto fora de estoque'
                })
                continue
            
            if product.track_stock:
                # Check variant stock if exists
                if item.variant_id and item.variant_id in locked_variants:
                    variant = locked_variants[item.variant_id]
                    if variant.stock_quantity is not None:
                        available = variant.stock_quantity
                    else:
                        available = product.stock_quantity
                else:
                    available = product.stock_quantity
                
                if item.quantity > available:
                    errors.append({
                        'item_id': str(item.id),
                        'product_name': product.name,
                        'error': f'Estoque insuficiente. Disponível: {available}',
                        'available': available,
                        'requested': item.quantity
                    })
        
        for item in cart.combo_items.select_related('combo').all():
            combo = locked_combos.get(item.combo_id) or item.combo
            # Skip virtual combos (no real combo FK — no stock to check)
            if combo is None:
                continue
            if combo.track_stock and item.quantity > combo.stock_quantity:
                errors.append({
                    'item_id': str(item.id),
                    'combo_name': combo.name,
                    'error': f'Estoque insuficiente. Disponível: {combo.stock_quantity}',
                    'available': combo.stock_quantity,
                    'requested': item.quantity
                })
        
        return errors


# Singleton instance
cart_service = CartService()
