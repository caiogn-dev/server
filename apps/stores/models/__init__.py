"""
Store models - Re-export all models for backward compatibility.

This module structure divides the original 1854-line models.py into smaller,
more manageable files while maintaining full backward compatibility.
"""

# Base models
from .base import Store, StoreIntegration, StoreWebhook

# Category
from .category import StoreCategory

# Product models
from .product import (
    StoreProductType,
    StoreProduct,
    StoreProductVariant,
    StoreWishlist,
)

# Customer
from .customer import StoreCustomer

# Order models
from .order import StoreOrder, StoreOrderItem, StoreOrderComboItem

# Cart models
from .cart import StoreCart, StoreCartItem, StoreCartComboItem

# Combo models
from .combo import StoreCombo, StoreComboItem

# Coupon
from .coupon import StoreCoupon

# Delivery
from .delivery import StoreDeliveryZone


__all__ = [
    # Base
    'Store',
    'StoreIntegration',
    'StoreWebhook',
    # Category
    'StoreCategory',
    # Product
    'StoreProductType',
    'StoreProduct',
    'StoreProductVariant',
    'StoreWishlist',
    # Customer
    'StoreCustomer',
    # Order
    'StoreOrder',
    'StoreOrderItem',
    'StoreOrderComboItem',
    # Cart
    'StoreCart',
    'StoreCartItem',
    'StoreCartComboItem',
    # Combo
    'StoreCombo',
    'StoreComboItem',
    # Coupon
    'StoreCoupon',
    # Delivery
    'StoreDeliveryZone',
]
