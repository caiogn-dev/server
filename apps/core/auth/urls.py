"""
URLs para autenticação WhatsApp
"""
from django.urls import path
from .views import (
    send_whatsapp_auth_code,
    verify_whatsapp_auth_code,
    resend_whatsapp_auth_code,
)

urlpatterns = [
    path('whatsapp/send/', send_whatsapp_auth_code, name='whatsapp-auth-send'),
    path('whatsapp/verify/', verify_whatsapp_auth_code, name='whatsapp-auth-verify'),
    path('whatsapp/resend/', resend_whatsapp_auth_code, name='whatsapp-auth-resend'),
]
