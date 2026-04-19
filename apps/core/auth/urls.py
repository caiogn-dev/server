"""
Authentication URLs - Login, logout, register, password reset
"""
from django.urls import path
from ..auth_views import (
    LoginView, 
    LogoutView, 
    RegisterView,
    CurrentUserView,
    ChangePasswordView,
)
from .views import (
    send_whatsapp_auth_code,
    verify_whatsapp_auth_code,
    resend_whatsapp_auth_code,
)

urlpatterns = [
    # Standard auth
    path('login/', LoginView.as_view(), name='api-login'),
    path('logout/', LogoutView.as_view(), name='api-logout'),
    path('register/', RegisterView.as_view(), name='api-register'),
    path('me/', CurrentUserView.as_view(), name='api-current-user'),
    path('change-password/', ChangePasswordView.as_view(), name='api-change-password'),
    # WhatsApp OTP auth
    path('whatsapp/send/', send_whatsapp_auth_code, name='api-whatsapp-send'),
    path('whatsapp/verify/', verify_whatsapp_auth_code, name='api-whatsapp-verify'),
    path('whatsapp/resend/', resend_whatsapp_auth_code, name='api-whatsapp-resend'),
]
