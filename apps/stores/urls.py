"""
URL configuration for the stores app.
Unified API for all stores including cart, checkout, catalog, maps, and webhooks.

This is the UNIFIED e-commerce API that all frontends should use.
Pastita-3D and other store frontends should use /api/v1/stores/{store_slug}/ endpoints (legacy /stores/s/{store_slug}/ paths remain for backward compatibility).
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
    MercadoPagoWebhookView, PaymentStatusView, OrderByTokenView,
    CustomerOrdersView, CustomerOrderDetailView, OrderWhatsAppView
)
from .api.maps_views import (
    StoreGeocodeView, StoreReverseGeocodeView, StoreRouteView,
    StoreValidateDeliveryView, StoreDeliveryZonesView, StoreAutosuggestView
)
from .api.export_views import (
    OrdersExportView, RevenueReportView, ProductsReportView,
    StockReportView, CustomersReportView, DashboardStatsView
)
from .api.payment_views import (
    StorePaymentViewSet, StorePaymentGatewayViewSet, StorePaymentWebhookEventViewSet
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

# Payment routers
payment_router = DefaultRouter()
payment_router.register(r'', StorePaymentViewSet, basename='payment')

gateway_router = DefaultRouter()
gateway_router.register(r'', StorePaymentGatewayViewSet, basename='payment-gateway')

webhook_event_router = DefaultRouter()
webhook_event_router.register(r'', StorePaymentWebhookEventViewSet, basename='payment-webhook-event')

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

store_frontend_patterns = [
    path('', StorePublicView.as_view(), name='store-public'),
    path('catalog/', StoreCatalogView.as_view(), name='store-catalog'),
    path('cart/', StoreCartViewSet.as_view({'get': 'get_cart_by_store'}), name='store-cart'),
    path('cart/add/', StoreCartViewSet.as_view({'post': 'add_item'}), name='store-cart-add'),
    path('cart/item/<uuid:item_id>/', StoreCartViewSet.as_view({
        'patch': 'update_item',
        'delete': 'remove_item',
    }), name='store-cart-item'),
    path('cart/clear/', StoreCartViewSet.as_view({'delete': 'clear_cart'}), name='store-cart-clear'),
    path('checkout/', StoreCheckoutView.as_view(), name='store-checkout'),
    path('delivery-fee/', StoreDeliveryFeeView.as_view(), name='store-delivery-fee'),
    path('validate-coupon/', StoreCouponValidateView.as_view(), name='store-validate-coupon'),
    path('wishlist/', StoreWishlistViewSet.as_view({'get': 'list'}), name='store-wishlist'),
    path('wishlist/add/', StoreWishlistViewSet.as_view({'post': 'add'}), name='store-wishlist-add'),
    path('wishlist/remove/', StoreWishlistViewSet.as_view({'post': 'remove'}), name='store-wishlist-remove'),
    path('wishlist/toggle/', StoreWishlistViewSet.as_view({'post': 'toggle'}), name='store-wishlist-toggle'),
    path('route/', StoreRouteView.as_view(), name='store-route'),
    path('validate-delivery/', StoreValidateDeliveryView.as_view(), name='store-validate-delivery'),
    path('delivery-zones/', StoreDeliveryZonesView.as_view(), name='store-delivery-zones'),
    path('autosuggest/', StoreAutosuggestView.as_view(), name='store-autosuggest'),
    path('webhooks/mercadopago/', MercadoPagoWebhookView.as_view(), name='store-webhook-mercadopago'),
]
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
    # Base: /api/v1/stores/{store_slug}/ (legacy /stores/s/{store_slug}/ kept for compatibility)
    # ==========================================================================
    
    # Store-specific storefront endpoints (use the /stores/{store_slug}/ base)
    path('s/<slug:store_slug>/', include(store_frontend_patterns)),
    path('<slug:store_slug>/', include(store_frontend_patterns)),
    
    # ========================================================================== 
    # HERE MAPS ENDPOINTS
    # ==========================================================================
    
    # Global maps endpoints
    path('maps/geocode/', StoreGeocodeView.as_view(), name='maps-geocode'),
    path('maps/reverse-geocode/', StoreReverseGeocodeView.as_view(), name='maps-reverse-geocode'),
    path('maps/autosuggest/', StoreAutosuggestView.as_view(), name='maps-autosuggest'),
    
    # ==========================================================================
    # PAYMENT WEBHOOKS
    # ==========================================================================
    
    # Global webhook (finds store from order)
    path('webhooks/mercadopago/', MercadoPagoWebhookView.as_view(), name='webhook-mercadopago'),
    
    # Payment status check (requires token for security)
    path('orders/<str:order_id>/payment-status/', PaymentStatusView.as_view(), name='order-payment-status'),
    
    # SECURE: Get order by access token (public endpoint)
    path('orders/by-token/<str:access_token>/', OrderByTokenView.as_view(), name='order-by-token'),
    
    # ==========================================================================
    # CUSTOMER ORDER ENDPOINTS (public/authenticated)
    # ==========================================================================
    
    # Customer orders list (requires auth)
    path('orders/', CustomerOrdersView.as_view(), name='customer-orders'),
    
    # Single order detail (public - by order ID)
    path('orders/<uuid:order_id>/', CustomerOrderDetailView.as_view(), name='customer-order-detail'),
    
    # WhatsApp confirmation link
    path('orders/<uuid:order_id>/whatsapp/', OrderWhatsAppView.as_view(), name='order-whatsapp'),
    
    # ==========================================================================
    # REPORTS & EXPORT ENDPOINTS (require auth)
    # ==========================================================================
    
    # Export orders as CSV
    path('reports/orders/export/', OrdersExportView.as_view(), name='orders-export'),
    
    # Revenue report (JSON)
    path('reports/revenue/', RevenueReportView.as_view(), name='revenue-report'),
    
    # Products performance report
    path('reports/products/', ProductsReportView.as_view(), name='products-report'),
    
    # Stock/inventory report
    path('reports/stock/', StockReportView.as_view(), name='stock-report'),
    
    # Customers report
    path('reports/customers/', CustomersReportView.as_view(), name='customers-report'),
    
    # Dashboard stats overview
    path('reports/dashboard/', DashboardStatsView.as_view(), name='dashboard-stats'),
    
    # ==========================================================================
    # PAYMENT ENDPOINTS (require auth)
    # ==========================================================================
    
    # Payments CRUD + actions
    path('payments/', include(payment_router.urls)),
    
    # Payment Gateways CRUD
    path('payments/gateways/', include(gateway_router.urls)),
    
    # Payment Webhook Events (read-only)
    path('payments/webhook-events/', include(webhook_event_router.urls)),
]
