"""
Messaging URLs - LEGACY.

DEPRECATED: Use messaging_v2 para a versão unificada.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    MessengerAccountViewSet,
    MessengerConversationViewSet,
    MessengerMessageViewSet,
)

app_name = 'messaging'

router = DefaultRouter()
router.register(r'messenger/accounts', MessengerAccountViewSet, basename='messenger-accounts')
router.register(r'messenger/conversations', MessengerConversationViewSet, basename='messenger-conversations')
router.register(r'messenger/messages', MessengerMessageViewSet, basename='messenger-messages')

urlpatterns = [
    path('', include(router.urls)),
]
