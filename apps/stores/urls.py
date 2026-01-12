"""
URL configuration for the stores app.
Unified API for all stores including cart, checkout, catalog, maps, and webhooks.

This is the UNIFIED e-commerce API that all frontends should use.
Pastita-3D and other store frontends should use /api/v1/stores/s/{store_slug}/ endpoints.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers as nested_routers

from .api.views import (
    StoreViewSet, StoreIntegrationViewSet, StoreWebhookViewSet,
    StoreCategoryViewSet, StoreProductViewSet, StoreProductVariantViewSet,
    StoreOrderViewSet, StoreCustomerViewSet,
    # Unified storefront views
    StoreCartViewSet, StoreCheckoutView, StoreDeliveryFeeView,
    StoreCouponValidateView, StoreCatalogView, StorePublicView,
    StoreComboViewSet, StoreProductTypeViewSet,
    # Coupon and Delivery Zone views
    StoreCouponViewSet, StoreDeliveryZoneViewSet,
    # Wishlist views
    StoreWishlistViewSet,
    # Admin views for full CRUD
    StoreProductTypeAdminViewSet
)
from .api.webhooks import (
    MercadoPagoWebhookView, PaymentStatusView,
    CustomerOrdersView, CustomerOrderDetailView, OrderWhatsAppView
)
from .api.maps_views import (
    StoreGeocodeView, StoreReverseGeocodeView, StoreRouteView,
    StoreValidateDeliveryView, StoreDeliveryZonesView, StoreAutosuggestView
)

# Main router for admin/management endpoints
router = DefaultRouter()
router.register(r'stores', StoreViewSet, basename='store')
router.register(r'integrations', StoreIntegrationViewSet, basename='integration')
router.register(r'webhooks', StoreWebhookViewSet, basename='webhook')
router.register(r'categories', StoreCategoryViewSet, basename='category')
router.register(r'products', StoreProductViewSet, basename='product')
router.register(r'variants', StoreProductVariantViewSet, basename='variant')
router.register(r'orders', StoreOrderViewSet, basename='order')
router.register(r'customers', StoreCustomerViewSet, basename='customer')
router.register(r'combos', StoreComboViewSet, basename='combo')
router.register(r'product-types', StoreProductTypeViewSet, basename='product-type')
router.register(r'coupons', StoreCouponViewSet, basename='coupon')
router.register(r'delivery-zones', StoreDeliveryZoneViewSet, basename='delivery-zone')
# Admin viewset for product types (full CRUD)
router.register(r'admin/product-types', StoreProductTypeAdminViewSet, basename='admin-product-type')

# Nested routers for store-specific resources
stores_router = nested_routers.NestedDefaultRouter(router, r'stores', lookup='store')
stores_router.register(r'integrations', StoreIntegrationViewSet, basename='store-integrations')
stores_router.register(r'webhooks', StoreWebhookViewSet, basename='store-webhooks')
stores_router.register(r'categories', StoreCategoryViewSet, basename='store-categories')
stores_router.register(r'products', StoreProductViewSet, basename='store-products')
stores_router.register(r'orders', StoreOrderViewSet, basename='store-orders')
stores_router.register(r'customers', StoreCustomerViewSet, basename='store-customers')

# Nested router for product variants
products_router = nested_routers.NestedDefaultRouter(router, r'products', lookup='product')
products_router.register(r'variants', StoreProductVariantViewSet, basename='product-variants')

app_name = 'stores'

urlpatterns = [
    # ==========================================================================
    # ADMIN/MANAGEMENT ENDPOINTS (require auth)
    # ==========================================================================
    path('', include(router.urls)),
    path('', include(stores_router.urls)),
    path('', include(products_router.urls)),
    
    # ==========================================================================
    # PUBLIC STOREFRONT ENDPOINTS (by store slug)
    # Base: /api/v1/stores/s/{store_slug}/
    # ==========================================================================
    
    # Store info (public)
    path('s/<slug:store_slug>/', StorePublicView.as_view(), name='store-public'),
    
    # Catalog - GET /stores/s/{store_slug}/catalog/
    path('s/<slug:store_slug>/catalog/', StoreCatalogView.as_view(), name='store-catalog'),
    
    # Cart endpoints
    path('s/<slug:store_slug>/cart/', StoreCartViewSet.as_view({
        'get': 'get_cart_by_store',
    }), name='store-cart'),
    path('s/<slug:store_slug>/cart/add/', StoreCartViewSet.as_view({
        'post': 'add_item',
    }), name='store-cart-add'),
    path('s/<slug:store_slug>/cart/item/<uuid:item_id>/', StoreCartViewSet.as_view({
        'patch': 'update_item',
        'delete': 'remove_item',
    }), name='store-cart-item'),
    path('s/<slug:store_slug>/cart/clear/', StoreCartViewSet.as_view({
        'delete': 'clear_cart',
    }), name='store-cart-clear'),
    
    # Checkout
    path('s/<slug:store_slug>/checkout/', StoreCheckoutView.as_view(), name='store-checkout'),
    
    # Delivery & Coupons
    path('s/<slug:store_slug>/delivery-fee/', StoreDeliveryFeeView.as_view(), name='store-delivery-fee'),
    path('s/<slug:store_slug>/validate-coupon/', StoreCouponValidateView.as_view(), name='store-validate-coupon'),
    
    # Wishlist endpoints
    path('s/<slug:store_slug>/wishlist/', StoreWishlistViewSet.as_view({
        'get': 'list',
    }), name='store-wishlist'),
    path('s/<slug:store_slug>/wishlist/add/', StoreWishlistViewSet.as_view({
        'post': 'add',
    }), name='store-wishlist-add'),
    path('s/<slug:store_slug>/wishlist/remove/', StoreWishlistViewSet.as_view({
        'post': 'remove',
    }), name='store-wishlist-remove'),
    path('s/<slug:store_slug>/wishlist/toggle/', StoreWishlistViewSet.as_view({
        'post': 'toggle',
    }), name='store-wishlist-toggle'),
    
    # ==========================================================================
    # HERE MAPS ENDPOINTS
    # ==========================================================================
    
    # Global maps endpoints
    path('maps/geocode/', StoreGeocodeView.as_view(), name='maps-geocode'),
    path('maps/reverse-geocode/', StoreReverseGeocodeView.as_view(), name='maps-reverse-geocode'),
    path('maps/autosuggest/', StoreAutosuggestView.as_view(), name='maps-autosuggest'),
    
    # Store-specific maps endpoints
    path('s/<slug:store_slug>/route/', StoreRouteView.as_view(), name='store-route'),
    path('s/<slug:store_slug>/validate-delivery/', StoreValidateDeliveryView.as_view(), name='store-validate-delivery'),
    path('s/<slug:store_slug>/delivery-zones/', StoreDeliveryZonesView.as_view(), name='store-delivery-zones'),
    path('s/<slug:store_slug>/autosuggest/', StoreAutosuggestView.as_view(), name='store-autosuggest'),
    
    # ==========================================================================
    # PAYMENT WEBHOOKS
    # ==========================================================================
    
    # Global webhook (finds store from order)
    path('webhooks/mercadopago/', MercadoPagoWebhookView.as_view(), name='webhook-mercadopago'),
    
    # Store-specific webhook
    path('s/<slug:store_slug>/webhooks/mercadopago/', MercadoPagoWebhookView.as_view(), name='store-webhook-mercadopago'),
    
    # Payment status check (accepts UUID or order_number)
    path('orders/<str:order_id>/payment-status/', PaymentStatusView.as_view(), name='order-payment-status'),
    
    # ==========================================================================
    # CUSTOMER ORDER ENDPOINTS (public/authenticated)
    # ==========================================================================
    
    # Customer orders list (requires auth)
    path('orders/', CustomerOrdersView.as_view(), name='customer-orders'),
    
    # Single order detail (public - by order ID)
    path('orders/<uuid:order_id>/', CustomerOrderDetailView.as_view(), name='customer-order-detail'),
    
    # WhatsApp confirmation link
    path('orders/<uuid:order_id>/whatsapp/', OrderWhatsAppView.as_view(), name='order-whatsapp'),
]
