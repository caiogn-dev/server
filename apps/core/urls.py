"""
Core URLs - Health check, system endpoints, dashboard, auth, and export.
"""
from django.urls import path
from .api import HealthCheckView, SystemInfoView
from .dashboard_views import DashboardOverviewView, DashboardActivityView, DashboardChartsView
from .auth_views import (
    LoginView, LogoutView, CurrentUserView, ChangePasswordView,
    RegisterView, CSRFTokenView, ProfileView
)
from .export_views import (
    export_messages, export_orders, export_sessions,
    export_automation_logs, export_conversations, export_payments
)

urlpatterns = [
    # Health & System
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('system/', SystemInfoView.as_view(), name='system-info'),
    
    # CSRF Token (for frontend)
    path('csrf/', CSRFTokenView.as_view(), name='csrf-token'),
    
    # Authentication
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/me/', CurrentUserView.as_view(), name='auth-me'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
    
    # User Profile (extended fields)
    path('users/profile/', ProfileView.as_view(), name='user-profile'),
    
    # Dashboard
    path('dashboard/overview/', DashboardOverviewView.as_view(), name='dashboard-overview'),
    path('dashboard/activity/', DashboardActivityView.as_view(), name='dashboard-activity'),
    path('dashboard/charts/', DashboardChartsView.as_view(), name='dashboard-charts'),
    
    # Export
    path('export/messages/', export_messages, name='export-messages'),
    path('export/orders/', export_orders, name='export-orders'),
    path('export/sessions/', export_sessions, name='export-sessions'),
    path('export/automation-logs/', export_automation_logs, name='export-automation-logs'),
    path('export/conversations/', export_conversations, name='export-conversations'),
    path('export/payments/', export_payments, name='export-payments'),
]
