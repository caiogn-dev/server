"""
Global webhook URLs for Mercado Pago.
Routes: /webhooks/payments/mercadopago/
"""
from django.urls import path
from .api.webhooks import MercadoPagoWebhookView

urlpatterns = [
    path('', MercadoPagoWebhookView.as_view(), name='global-webhook-mercadopago'),
]
