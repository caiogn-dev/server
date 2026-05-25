from django.urls import path
from apps.postado.api.admin_views import (
    AdminDashboardView, AdminClientListView, AdminClientDetailView,
    AdminPackDetailView, AdminPostUpdateView,
    AdminPackApproveView, AdminPostRegenerateView, AdminGeneratePackView,
)

urlpatterns = [
    path('dashboard/', AdminDashboardView.as_view(), name='postado-admin-dashboard'),
    path('clients/', AdminClientListView.as_view(), name='postado-admin-clients'),
    path('clients/<uuid:client_id>/', AdminClientDetailView.as_view(), name='postado-admin-client-detail'),
    path('packs/<uuid:pack_id>/', AdminPackDetailView.as_view(), name='postado-admin-pack-detail'),
    path('packs/generate/', AdminGeneratePackView.as_view(), name='postado-admin-generate-pack'),
    path('packs/<uuid:pack_id>/approve/', AdminPackApproveView.as_view(), name='postado-admin-pack-approve'),
    path('posts/<uuid:post_id>/', AdminPostUpdateView.as_view(), name='postado-admin-post-update'),
    path('posts/<uuid:post_id>/regenerate/', AdminPostRegenerateView.as_view(), name='postado-admin-post-regenerate'),
]
