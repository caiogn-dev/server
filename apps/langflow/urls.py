"""
Langflow API URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import LangflowFlowViewSet, LangflowSessionViewSet

router = DefaultRouter()
router.register(r'flows', LangflowFlowViewSet, basename='langflow-flow')
router.register(r'sessions', LangflowSessionViewSet, basename='langflow-session')

urlpatterns = [
    path('', include(router.urls)),
]
