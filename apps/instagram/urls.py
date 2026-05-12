from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    InstagramAccountViewSet, InstagramMediaViewSet,
    InstagramShoppingViewSet, InstagramLiveViewSet,
    InstagramConversationViewSet, InstagramMessageViewSet,
    InstagramWebhookViewSet
)
from .api.data_deletion_view import MetaDataDeletionView, MetaDataDeletionStatusView

app_name = 'instagram'

router = DefaultRouter()
router.register(r'accounts', InstagramAccountViewSet, basename='instagram-accounts')
router.register(r'media', InstagramMediaViewSet, basename='instagram-media')
router.register(r'shopping', InstagramShoppingViewSet, basename='instagram-shopping')
router.register(r'live', InstagramLiveViewSet, basename='instagram-live')
router.register(r'conversations', InstagramConversationViewSet, basename='instagram-conversations')
router.register(r'messages', InstagramMessageViewSet, basename='instagram-messages')
router.register(r'webhooks', InstagramWebhookViewSet, basename='instagram-webhooks')

urlpatterns = [
    # Meta App Review: Data Deletion Request callback
    path('data-deletion/', MetaDataDeletionView.as_view(), name='meta-data-deletion'),
    path('data-deletion/status/', MetaDataDeletionStatusView.as_view(), name='meta-data-deletion-status'),

    path('', include(router.urls)),
]
