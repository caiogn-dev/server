"""
URL configuration for the stores app.
Unified API for all stores including cart, checkout, catalog, maps, and webhooks.

This is the UNIFIED e-commerce API that all frontends should use.
All frontends must use /api/v1/stores/{store_slug}/ endpoints.
"""
from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers as nested_routers

from .api.views import (
    StoreViewSet, StoreIntegrationViewSet, StoreWebhookViewSet,
    StoreCategoryViewSet, StoreProductViewSet, StoreProductVariantViewSet,
    StoreOrderViewSet, StoreCustomerViewSet,
    StorePrintAgentViewSet, StorePrintJobViewSet,
    # Unified storefront views
    StoreCartViewSet, StoreCheckoutView, StoreDeliveryFeeView,
    StoreCouponValidateView, StoreCatalogView, StorePublicView,
    StoreAppConfigView, StoreCustomerProfileView,
    StoreComboViewSet, StoreProductTypeViewSet,
    # Coupon and Delivery Zone views
    StoreCouponViewSet, StoreDeliveryZoneViewSet,
    # Wishlist views
    StoreWishlistViewSet,
    # Combo views
    AddComboToCartView,
    # Customer address management
    MyAddressViewSet,
    # Admin views for full CRUD
    StoreProductTypeAdminViewSet,
    PrintAgentHeartbeatView, PrintAgentClaimNextJobView,
    PrintAgentCompleteJobView, PrintAgentFailJobView, PrintAgentWatchJobsView,
)

# Wrapper functions to pass store_slug to viewset kwargs
def store_orders_list(request, store_slug):
    """Wrapper to inject store_slug as store_pk for order list/create."""
    # Inject into resolver_match.kwargs so viewset can access it
    if request.resolver_match:
        request.resolver_match.kwargs['store_pk'] = store_slug

    view = StoreOrderViewSet.as_view({'get': 'list', 'post': 'create'})
    return view(request, store_pk=store_slug)

def store_order_detail(request, store_slug, pk):
    """Wrapper to inject store_slug as store_pk for order detail."""
    if request.resolver_match:
        request.resolver_match.kwargs['store_pk'] = store_slug
        request.resolver_match.kwargs['pk'] = pk

    view = StoreOrderViewSet.as_view({
        'get': 'retrieve',
        'patch': 'partial_update',
        'put': 'update',
        'delete': 'destroy',
    })
    return view(request, store_pk=store_slug, pk=pk)

def store_order_adjust(request, store_slug, pk):
    """Wrapper para POST /orders/{pk}/adjust/ — injeta store_slug como store_pk."""
    if request.resolver_match:
        request.resolver_match.kwargs['store_pk'] = store_slug
        request.resolver_match.kwargs['pk'] = pk

    view = StoreOrderViewSet.as_view({'post': 'adjust'})
    return view(request, store_pk=store_slug, pk=pk)

def store_order_generate_payment(request, store_slug, pk):
    """Wrapper para POST /orders/{pk}/generate_payment/ — injeta store_slug."""
    if request.resolver_match:
        request.resolver_match.kwargs['store_pk'] = store_slug
        request.resolver_match.kwargs['pk'] = pk

    view = StoreOrderViewSet.as_view({'post': 'generate_payment'})
    return view(request, store_pk=store_slug, pk=pk)

def my_addresses_list(request, store_slug):
    """Wrapper to inject store_slug for address list/create."""
    if request.resolver_match:
        request.resolver_match.kwargs['store_slug'] = store_slug

    view = MyAddressViewSet.as_view({'get': 'list', 'post': 'create'})
    return view(request, store_slug=store_slug)

def my_addresses_detail(request, store_slug, id):
    """Wrapper to inject store_slug for address detail."""
    if request.resolver_match:
        request.resolver_match.kwargs['store_slug'] = store_slug
        request.resolver_match.kwargs['id'] = id

    view = MyAddressViewSet.as_view({
        'get': 'retrieve',
        'patch': 'partial_update',
        'delete': 'destroy',
    })
    return view(request, store_slug=store_slug, id=id)

def my_addresses_set_default(request, store_slug, id):
    """Wrapper to inject store_slug for set-default action."""
    if request.resolver_match:
        request.resolver_match.kwargs['store_slug'] = store_slug
        request.resolver_match.kwargs['id'] = id

    view = MyAddressViewSet.as_view({'patch': 'set_default'})
    return view(request, store_slug=store_slug, id=id)

from .api.webhooks import (
    MercadoPagoWebhookView, PaymentStatusView, OrderByTokenView,
    CustomerOrdersView, CustomerOrderDetailView, OrderWhatsAppView,
    OrderReceiptView,
)
from .api.views.review_views import OrderReviewByTokenView, StoreReviewListView
from .api.views.subscription_views import (
    StoreSubscribeView,
    StoreSubscriptionDetailView,
    StoreSubscriptionCancelView,
    StoreSubscriptionChangePlanView,
)
from .api.views.onboarding_views import StoreOnboardingChecklistView
from .api.views.cash_views import CashOpenView, CashCurrentView, CashMovementView, CashCloseView
from .api.maps_views import (
    StoreGeocodeView, StoreReverseGeocodeView, StoreRouteView,
    StoreValidateDeliveryView, StoreDeliveryZonesView, StoreAutosuggestView
)
from .api.export_views import (
    OrdersExportView, RevenueReportView, ProductsReportView,
    StockReportView, CustomersReportView, StoreDashboardStatsView,
    SaladasReportView,
)
from .api.payment_views import (
    StorePaymentViewSet, StorePaymentGatewayViewSet, StorePaymentWebhookEventViewSet
)
from .api.views.loyalty_views import LoyaltyStatusView, LoyaltyRedeemCheckView
from .api.views.crm_views import (
    CustomerSearchView,
    CustomerAddressViewSet,
    TeamMemberViewSet,
    places_search_view,
)

# Orders app routes (Uber delivery integration)
from apps.orders.urls import urlpatterns as orders_urlpatterns


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
router.register(r'print-agents', StorePrintAgentViewSet, basename='print-agent')
router.register(r'print-jobs', StorePrintJobViewSet, basename='print-job')
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
stores_router.register(r'combos', StoreComboViewSet, basename='store-combos')
stores_router.register(r'orders', StoreOrderViewSet, basename='store-orders')
stores_router.register(r'customers', StoreCustomerViewSet, basename='store-customers')
stores_router.register(r'print-agents', StorePrintAgentViewSet, basename='store-print-agents')
stores_router.register(r'print-jobs', StorePrintJobViewSet, basename='store-print-jobs')

# Nested router for product variants
products_router = nested_routers.NestedDefaultRouter(router, r'products', lookup='product')
products_router.register(r'variants', StoreProductVariantViewSet, basename='product-variants')

store_frontend_patterns = [
    path('', StorePublicView.as_view(), name='store-public'),
    path('reviews/', StoreReviewListView.as_view(), name='store-reviews'),
    # Caixa (PDV)
    path('cash/open/', CashOpenView.as_view(), name='store-cash-open'),
    path('cash/current/', CashCurrentView.as_view(), name='store-cash-current'),
    path('cash/movement/', CashMovementView.as_view(), name='store-cash-movement'),
    path('cash/close/', CashCloseView.as_view(), name='store-cash-close'),
    path('app-config/', StoreAppConfigView.as_view(), name='store-app-config'),
    path('catalog/', StoreCatalogView.as_view(), name='store-catalog'),
    path('customer/profile/', StoreCustomerProfileView.as_view(), name='store-customer-profile'),
    path('cart/', StoreCartViewSet.as_view({'get': 'get_cart_by_store'}), name='store-cart'),
    path('cart/add/', StoreCartViewSet.as_view({'post': 'add_item'}), name='store-cart-add'),
    path('cart/add-combo/', AddComboToCartView.as_view(), name='add-combo-to-cart'),
    path('cart/item/<uuid:item_id>/', StoreCartViewSet.as_view({
        'patch': 'update_item',
        'delete': 'remove_item',
    }), name='store-cart-item'),
    path('cart/clear/', StoreCartViewSet.as_view({'delete': 'clear_cart'}), name='store-cart-clear'),
    path('checkout/', StoreCheckoutView.as_view(), name='store-checkout'),
    path('delivery-fee/', StoreDeliveryFeeView.as_view(), name='store-delivery-fee'),
    path('subscribe/', StoreSubscribeView.as_view(), name='store-subscribe'),
    path('subscription/', StoreSubscriptionDetailView.as_view(), name='store-subscription-detail'),
    path('subscription/cancel/', StoreSubscriptionCancelView.as_view(), name='store-subscription-cancel'),
    path('subscription/change-plan/', StoreSubscriptionChangePlanView.as_view(), name='store-subscription-change-plan'),
    path('onboarding/checklist/', StoreOnboardingChecklistView.as_view(), name='store-onboarding-checklist'),
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
    path('loyalty/', LoyaltyStatusView.as_view(), name='store-loyalty-status'),
    path('loyalty/redeem-check/', LoyaltyRedeemCheckView.as_view(), name='store-loyalty-redeem-check'),

    # Customer-facing address management — using re_path to capture store_slug from parent include()
    re_path(r'^customer/my-addresses/$', my_addresses_list, name='my-addresses'),
    re_path(r'^customer/my-addresses/(?P<id>[0-9a-f\-]+)/$', my_addresses_detail, name='my-address-detail'),
    re_path(r'^customer/my-addresses/(?P<id>[0-9a-f\-]+)/set-default/$', my_addresses_set_default, name='my-address-set-default'),

    # Orders CRUD (for slug-based access)
    # Wrapper injects store_slug as store_pk for viewset kwargs
    path('orders/', store_orders_list, name='store-orders-list'),
    path('orders/<uuid:pk>/', store_order_detail, name='store-order-detail'),
    path('orders/<uuid:pk>/adjust/', store_order_adjust, name='store-order-adjust'),
    path('orders/<uuid:pk>/generate_payment/', store_order_generate_payment, name='store-order-generate-payment'),

    # CRM
    path('crm/customers/search/', CustomerSearchView.as_view(), name='store-crm-customer-search'),
    path('crm/customers/<uuid:user_id>/addresses/', CustomerAddressViewSet.as_view({
        'get': 'list',
        'post': 'create',
    }), name='store-crm-customer-addresses'),
    path('crm/customers/<uuid:user_id>/addresses/<uuid:pk>/', CustomerAddressViewSet.as_view({
        'get': 'retrieve',
        'patch': 'partial_update',
        'put': 'update',
        'delete': 'destroy',
    }), name='store-crm-customer-address-detail'),

    # Team
    path('team/', TeamMemberViewSet.as_view({
        'get': 'list',
        'post': 'create',
    }), name='store-team-list'),
    path('team/<uuid:pk>/', TeamMemberViewSet.as_view({
        'get': 'retrieve',
        'patch': 'partial_update',
        'put': 'update',
        'delete': 'destroy',
    }), name='store-team-detail'),
]
app_name = 'stores'

urlpatterns = [
    # ==========================================================================
    # ADMIN/MANAGEMENT ENDPOINTS (require auth)
    # ==========================================================================
    path('', include(router.urls)),
    path('', include(stores_router.urls)),
    path('', include(products_router.urls)),

    # Orders delivery (Uber integration)
    *orders_urlpatterns,

    # ==========================================================================
    # PAYMENT WEBHOOKS
    # ==========================================================================
    
    # Global webhook (finds store from order)
    path('webhooks/mercadopago/', MercadoPagoWebhookView.as_view(), name='webhook-mercadopago'),
    
    # Payment status check (requires token for security)
    path('orders/<str:order_id>/payment-status/', PaymentStatusView.as_view(), name='order-payment-status'),
    
    # SECURE: Get order by access token (public endpoint)
    path('orders/by-token/<str:access_token>/', OrderByTokenView.as_view(), name='order-by-token'),
    # Avaliação do pedido pelo cliente (público via token)
    path('orders/by-token/<str:access_token>/review/', OrderReviewByTokenView.as_view(), name='order-review-by-token'),
    
    # ==========================================================================
    # CUSTOMER ORDER ENDPOINTS (public/authenticated)
    # ==========================================================================
    
    # Customer orders list (requires auth)
    path('customer/orders/', CustomerOrdersView.as_view(), name='customer-orders'),
    # Flutter mobile: use this path with ?token= for unauthenticated customer detail
    path('customer/orders/<uuid:order_id>/', CustomerOrderDetailView.as_view(), name='customer-order-detail'),

    # WhatsApp confirmation link
    path('orders/<uuid:order_id>/whatsapp/', OrderWhatsAppView.as_view(), name='order-whatsapp'),
    path('orders/<uuid:order_id>/receipt/', OrderReceiptView.as_view(), name='order-receipt'),
    
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
    path('reports/saladas/', SaladasReportView.as_view(), name='saladas-report'),
    
    # Dashboard stats overview
    path('reports/dashboard/', StoreDashboardStatsView.as_view(), name='store-dashboard-stats'),
    
    # ==========================================================================
    # PAYMENT ENDPOINTS (require auth)
    # ==========================================================================
    
    # Payments CRUD + actions
    path('payments/', include(payment_router.urls)),
    
    # Payment Gateways CRUD
    path('payments/gateways/', include(gateway_router.urls)),
    
    # Payment Webhook Events (read-only)
    path('payments/webhook-events/', include(webhook_event_router.urls)),

    # ==========================================================================
    # LOCAL PRINT AGENT ENDPOINTS
    # ==========================================================================
    path('print/agent/heartbeat/', PrintAgentHeartbeatView.as_view(), name='print-agent-heartbeat'),
    path('print/agent/claim-next/', PrintAgentClaimNextJobView.as_view(), name='print-agent-claim-next'),
    path('print/agent/watch/', PrintAgentWatchJobsView.as_view(), name='print-agent-watch'),
    path('print/jobs/<uuid:job_id>/complete/', PrintAgentCompleteJobView.as_view(), name='print-job-complete'),
    path('print/jobs/<uuid:job_id>/fail/', PrintAgentFailJobView.as_view(), name='print-job-fail'),

    # ==========================================================================
    # ADMIN UTILITY ENDPOINTS
    # ==========================================================================
    path('admin/places-search/', places_search_view, name='admin-places-search'),

    # ==========================================================================
    # PUBLIC STOREFRONT ENDPOINTS (by store slug)
    # Base: /api/v1/stores/{store_slug}/
    # Keep these last so catch-all slug routes do not shadow global endpoints.
    # ==========================================================================

    # Legacy alias kept for backwards compatibility with older frontends
    path('s/<slug:store_slug>/', include(store_frontend_patterns)),
    # Store-specific storefront endpoints (canonical)
    path('<slug:store_slug>/', include(store_frontend_patterns)),
]
