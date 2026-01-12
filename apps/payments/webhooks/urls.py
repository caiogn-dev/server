"""
Payment webhook URLs.
"""
from django.urls import path
from .views import PaymentWebhookView

urlpatterns = [
    path('<uuid:gateway_id>/', PaymentWebhookView.as_view(), name='payment-webhook'),
]
