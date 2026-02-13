from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    MessengerAccountViewSet, MessengerProfileViewSet,
    MessengerConversationViewSet, MessengerBroadcastViewSet,
    MessengerSponsoredViewSet, MessengerWebhookViewSet
)

app_name = 'messaging'

router = DefaultRouter()
router.register(r'messenger/accounts', MessengerAccountViewSet, basename='messenger-accounts')
router.register(r'messenger/profile', MessengerProfileViewSet, basename='messenger-profile')
router.register(r'messenger/conversations', MessengerConversationViewSet, basename='messenger-conversations')
router.register(r'messenger/broadcasts', MessengerBroadcastViewSet, basename='messenger-broadcasts')
router.register(r'messenger/sponsored', MessengerSponsoredViewSet, basename='messenger-sponsored')
router.register(r'messenger/webhooks', MessengerWebhookViewSet, basename='messenger-webhooks')

urlpatterns = [
    path('', include(router.urls)),
]
