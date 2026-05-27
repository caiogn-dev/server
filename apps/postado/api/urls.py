from django.urls import path, include
from apps.postado.api.views import PostadoSignupView, PostadoMPWebhookView

urlpatterns = [
    path('signup/', PostadoSignupView.as_view(), name='postado-signup'),
    path('webhook/mp/', PostadoMPWebhookView.as_view(), name='postado-mp-webhook'),
    path('admin/', include('apps.postado.api.admin_urls')),
]
