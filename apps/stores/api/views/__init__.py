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

# Printing
from .print_views import (
    StorePrintAgentViewSet,
    StorePrintJobViewSet,
    PrintAgentHeartbeatView,
    PrintAgentClaimNextJobView,
    PrintAgentCompleteJobView,
    PrintAgentFailJobView,
    PrintAgentWatchJobsView,
)

# Coupon management
from .coupon_views import (
    StoreCouponViewSet,
)

# Bio link management (Link na Bio)
from .bio_views import (
    BioLinkViewSet,
)

# Delivery management
from .delivery_views import (
    StoreDeliveryZoneViewSet,
)

# Combo views
from .combo_views import (
    AddComboToCartView,
)

# Storefront views (public-facing)
from .storefront_views import (
    StoreCartViewSet,
    StoreCheckoutView,
    StoreDeliveryFeeView,
    StoreSharedLocationView,
    StoreCouponValidateView,
    StoreCatalogView,
    StorePublicView,
    StoreAppConfigView,
    TemplateCatalogView,
    StoreCustomerProfileView,
    StoreWishlistViewSet,
    MyAddressViewSet,
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
    # Printing
    'StorePrintAgentViewSet',
    'StorePrintJobViewSet',
    'PrintAgentHeartbeatView',
    'PrintAgentClaimNextJobView',
    'PrintAgentCompleteJobView',
    'PrintAgentFailJobView',
    'PrintAgentWatchJobsView',
    # Coupons
    'StoreCouponViewSet',
    # Bio links
    'BioLinkViewSet',
    # Delivery
    'StoreDeliveryZoneViewSet',
    # Combos
    'AddComboToCartView',
    # Storefront
    'StoreCartViewSet',
    'StoreCheckoutView',
    'StoreDeliveryFeeView',
    'StoreSharedLocationView',
    'StoreCouponValidateView',
    'StoreCatalogView',
    'StorePublicView',
    'StoreAppConfigView',
    'TemplateCatalogView',
    'StoreCustomerProfileView',
    'StoreWishlistViewSet',
    'MyAddressViewSet',
]
