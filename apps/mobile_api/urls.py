"""
Mobile API namespace — /api/v1/mobile/

Clean, stable paths for Flutter app. No conflict with admin routes.
These are thin re-exports; all logic lives in apps.stores.api.webhooks.
"""
from django.urls import path
from apps.stores.api.webhooks import (
    OrderByTokenView,
    CustomerOrderDetailView,
    CustomerOrdersView,
    PaymentStatusView,
)

app_name = 'mobile_api'

urlpatterns = [
    # Order by access token — primary Flutter path post-checkout
    # GET /api/v1/mobile/orders/by-token/{access_token}/
    path(
        'orders/by-token/<str:access_token>/',
        OrderByTokenView.as_view(),
        name='order-by-token',
    ),

    # Order detail: auth OR ?token=<access_token>
    # GET /api/v1/mobile/orders/{order_id}/
    path(
        'orders/<uuid:order_id>/',
        CustomerOrderDetailView.as_view(),
        name='order-detail',
    ),

    # Payment status polling
    # GET /api/v1/mobile/orders/{order_id}/payment-status/
    path(
        'orders/<uuid:order_id>/payment-status/',
        PaymentStatusView.as_view(),
        name='order-payment-status',
    ),

    # Authenticated customer order list
    # GET /api/v1/mobile/orders/
    path(
        'orders/',
        CustomerOrdersView.as_view(),
        name='order-list',
    ),
]
