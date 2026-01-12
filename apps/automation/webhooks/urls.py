"""
Webhook URLs for automation.
"""
from django.urls import path
from .views import (
    CartWebhookView,
    PaymentWebhookView,
    OrderWebhookView,
    WebhookStatusView,
)

urlpatterns = [
    path('cart/', CartWebhookView.as_view(), name='automation-cart-webhook'),
    path('payment/', PaymentWebhookView.as_view(), name='automation-payment-webhook'),
    path('order/', OrderWebhookView.as_view(), name='automation-order-webhook'),
    path('status/', WebhookStatusView.as_view(), name='automation-webhook-status'),
]
