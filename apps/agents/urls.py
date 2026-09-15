"""
URLs for Agents API
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AgentViewSet, AgentConversationViewSet

router = DefaultRouter()
router.register(r'conversations', AgentConversationViewSet, basename='agent-conversation')
# `r''` por ÚLTIMO: o detalhe dele (`^<pk>/$`) engolia `conversations/`.
router.register(r'', AgentViewSet, basename='agent')

urlpatterns = [
    path('', include(router.urls)),
]
