"""
URLs for Agents API
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AgentViewSet, AgentConversationViewSet

router = DefaultRouter()
router.register(r'agents', AgentViewSet, basename='agent')
router.register(r'conversations', AgentConversationViewSet, basename='agent-conversation')

urlpatterns = [
    path('', include(router.urls)),
]
