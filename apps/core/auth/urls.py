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
    RequestPasswordResetView,
    VerifyPasswordResetView,
)

urlpatterns = [
    # Standard auth
    path('login/', LoginView.as_view(), name='api-login'),
    path('logout/', LogoutView.as_view(), name='api-logout'),
    path('register/', RegisterView.as_view(), name='api-register'),
    path('me/', CurrentUserView.as_view(), name='api-current-user'),
    path('change-password/', ChangePasswordView.as_view(), name='api-change-password'),
    
    # Password reset
    path('password-reset/request/', RequestPasswordResetView.as_view(), name='api-password-reset-request'),
    path('password-reset/verify/', VerifyPasswordResetView.as_view(), name='api-password-reset-verify'),
]

