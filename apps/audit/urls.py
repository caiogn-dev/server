"""
Audit API URLs.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import AuditLogViewSet, ExportViewSet

router = DefaultRouter()
router.register(r'logs', AuditLogViewSet, basename='audit-log')
router.register(r'exports', ExportViewSet, basename='export')

urlpatterns = [
    path('', include(router.urls)),
]
