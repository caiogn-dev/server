"""
Orders app URL routing for Uber delivery endpoints.
"""
from django.urls import path
from apps.orders.views import (
    CreateDeliveryRequestView,
    DeliveryRequestStatusView,
    CancelDeliveryRequestView,
)

app_name = 'orders'

urlpatterns = [
    # Uber delivery endpoints
    # URLs are nested under stores/ in main app, so these are at:
    # /api/v1/stores/<slug>/orders/{id}/create-delivery-request/
    path(
        '<slug:store_slug>/orders/<uuid:order_id>/create-delivery-request/',
        CreateDeliveryRequestView.as_view(),
        name='create-delivery-request'
    ),
    path(
        '<slug:store_slug>/orders/<uuid:order_id>/delivery-request-status/',
        DeliveryRequestStatusView.as_view(),
        name='delivery-request-status'
    ),
    path(
        '<slug:store_slug>/orders/<uuid:order_id>/delivery-request/',
        CancelDeliveryRequestView.as_view(),
        name='cancel-delivery-request'
    ),
]
