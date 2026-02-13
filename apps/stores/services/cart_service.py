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
        notes: str = ''
    ) -> StoreCartItem:
        """Add an item to the cart by product_id."""
        product = StoreProduct.objects.get(id=product_id, store=cart.store)
        variant = None
        if variant_id:
            variant = StoreProductVariant.objects.get(id=variant_id, product=product)
        return CartService.add_product(cart, product, quantity, variant, notes=notes)
    
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
        
        # Validate stock
        if product.track_stock:
            available = product.stock_quantity
            if variant and variant.stock_quantity is not None:
                available = variant.stock_quantity
            
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
    
    @staticmethod
    @transaction.atomic
    def add_combo(
        cart: StoreCart,
        combo: StoreCombo,
        quantity: int = 1,
        customizations: dict = None,
        notes: str = ''
    ) -> StoreCartComboItem:
        """Add a combo to the cart."""
        
        # Check stock if tracked
        if combo.track_stock and combo.stock_quantity < quantity:
            raise ValueError(f"Estoque insuficiente para o combo. Disponível: {combo.stock_quantity}")
        
        # Add or update combo item
        existing = cart.combo_items.filter(combo=combo).first()
        if existing:
            existing.quantity += quantity
            if customizations:
                existing.customizations = {**existing.customizations, **customizations}
            if notes:
                existing.notes = notes
            existing.save()
            return existing
        else:
            return StoreCartComboItem.objects.create(
                cart=cart,
                combo=combo,
                quantity=quantity,
                customizations=customizations or {},
                notes=notes
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
        
        if item.combo.track_stock and quantity > item.combo.stock_quantity:
            raise ValueError(f"Estoque insuficiente. Disponível: {item.combo.stock_quantity}")
        
        item.quantity = quantity
        item.save()
        return item
    
    @staticmethod
    def remove_item(cart_or_item, item_id=None):
        """
        Remove an item from the cart.
        
        Supports two calling conventions:
        - remove_item(item) - direct item deletion
        - remove_item(cart, item_id) - lookup item by ID and delete
        """
        if isinstance(cart_or_item, StoreCartItem):
            # Old style: remove_item(item)
            item = cart_or_item
        else:
            # New style: remove_item(cart, item_id)
            cart = cart_or_item
            try:
                item = StoreCartItem.objects.get(id=item_id, cart=cart)
            except StoreCartItem.DoesNotExist:
                return  # Item already removed or doesn't exist
        item.delete()
    
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
        
        # Combo items
        for item in cart.combo_items.select_related('combo').all():
            item_data = {
                'id': str(item.id),
                'type': 'combo',
                'combo_id': str(item.combo.id),
                'combo_name': item.combo.name,
                'quantity': item.quantity,
                'unit_price': float(item.combo.price),
                'subtotal': float(item.subtotal),
                'customizations': item.customizations,
                'notes': item.notes,
                'image_url': item.combo.get_image_url(),
            }
            items.append(item_data)
            subtotal += item.subtotal
        
        return {
            'id': str(cart.id),
            'store_id': str(cart.store.id),
            'store_name': cart.store.name,
            'items': items,
            'item_count': cart.item_count + sum(ci.quantity for ci in cart.combo_items.all()),
            'subtotal': float(subtotal),
            'is_empty': len(items) == 0,
        }
    
    @staticmethod
    @transaction.atomic
    def validate_stock_for_checkout(cart: StoreCart) -> list:
        """
        Validate all items have sufficient stock for checkout.
        Returns list of errors if any.
        """
        errors = []
        
        for item in cart.items.select_related('product', 'variant').all():
            product = item.product
            
            if not product.is_in_stock:
                errors.append({
                    'item_id': str(item.id),
                    'product_name': product.name,
                    'error': 'Produto fora de estoque'
                })
                continue
            
            if product.track_stock:
                available = product.stock_quantity
                if item.variant and item.variant.stock_quantity is not None:
                    available = item.variant.stock_quantity
                
                if item.quantity > available:
                    errors.append({
                        'item_id': str(item.id),
                        'product_name': product.name,
                        'error': f'Estoque insuficiente. Disponível: {available}',
                        'available': available,
                        'requested': item.quantity
                    })
        
        for item in cart.combo_items.select_related('combo').all():
            if item.combo.track_stock and item.quantity > item.combo.stock_quantity:
                errors.append({
                    'item_id': str(item.id),
                    'combo_name': item.combo.name,
                    'error': f'Estoque insuficiente. Disponível: {item.combo.stock_quantity}',
                    'available': item.combo.stock_quantity,
                    'requested': item.quantity
                })
        
        return errors


# Singleton instance
cart_service = CartService()
