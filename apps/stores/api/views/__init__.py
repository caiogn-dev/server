"""
Store API views - organized by domain.

This module exports all viewsets from their respective domain modules.
"""

# Base utilities and permissions
from .base import (
    IsStoreOwnerOrStaff,
    filter_by_store,
    get_user_stores_queryset,
)

# Store management
from .store_views import (
    StoreViewSet,
    StoreIntegrationViewSet,
    StoreWebhookViewSet,
)

# Product management
from .product_views import (
    StoreCategoryViewSet,
    StoreProductViewSet,
    StoreProductVariantViewSet,
    StoreComboViewSet,
    StoreProductTypeViewSet,
    StoreProductTypeAdminViewSet,
)

# Order management
from .order_views import (
    StoreOrderViewSet,
    StoreCustomerViewSet,
)

# Coupon management
from .coupon_views import (
    StoreCouponViewSet,
)

# Delivery management
from .delivery_views import (
    StoreDeliveryZoneViewSet,
)

# Storefront views (public-facing)
from .storefront_views import (
    StoreCartViewSet,
    StoreCheckoutView,
    StoreDeliveryFeeView,
    StoreCouponValidateView,
    StoreCatalogView,
    StorePublicView,
    StoreWishlistViewSet,
)

__all__ = [
    # Base
    'IsStoreOwnerOrStaff',
    'filter_by_store',
    'get_user_stores_queryset',
    # Stores
    'StoreViewSet',
    'StoreIntegrationViewSet',
    'StoreWebhookViewSet',
    # Products
    'StoreCategoryViewSet',
    'StoreProductViewSet',
    'StoreProductVariantViewSet',
    'StoreComboViewSet',
    'StoreProductTypeViewSet',
    'StoreProductTypeAdminViewSet',
    # Orders
    'StoreOrderViewSet',
    'StoreCustomerViewSet',
    # Coupons
    'StoreCouponViewSet',
    # Delivery
    'StoreDeliveryZoneViewSet',
    # Storefront
    'StoreCartViewSet',
    'StoreCheckoutView',
    'StoreDeliveryFeeView',
    'StoreCouponValidateView',
    'StoreCatalogView',
    'StorePublicView',
    'StoreWishlistViewSet',
]
