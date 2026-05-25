from django.urls import path
from apps.postado.api.admin_views import AdminDashboardView

urlpatterns = [
    path('dashboard/', AdminDashboardView.as_view(), name='postado-admin-dashboard'),
]
