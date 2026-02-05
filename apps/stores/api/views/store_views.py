"""
Store management API views.
"""
import logging
import uuid as uuid_module
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q

from apps.stores.models import Store, StoreIntegration, StoreWebhook
from apps.stores.services import store_service, webhook_service
from ..serializers import (
    StoreSerializer, StoreCreateSerializer,
    StoreIntegrationSerializer, StoreIntegrationCreateSerializer,
    StoreWebhookSerializer,
    StoreStatsSerializer
)
from .base import IsStoreOwnerOrStaff

logger = logging.getLogger(__name__)


class StoreViewSet(viewsets.ModelViewSet):
    """ViewSet for managing stores."""
    
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    lookup_field = 'pk'
    
    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Store.objects.all()
        return Store.objects.filter(
            Q(owner=user) | Q(staff=user)
        ).distinct()
    
    def get_object(self):
        """Override to support both UUID and slug lookups."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]
        
        try:
            uuid_module.UUID(lookup_value)
            filter_kwargs = {'pk': lookup_value}
        except (ValueError, AttributeError):
            filter_kwargs = {'slug': lookup_value}
        
        obj = get_object_or_404(queryset, **filter_kwargs)
        self.check_object_permissions(self.request, obj)
        return obj
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StoreCreateSerializer
        return StoreSerializer
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get store statistics."""
        store = self.get_object()
        stats = store_service.get_store_stats(store)
        return Response(StoreStatsSerializer(stats).data)
    
    @action(detail=True, methods=['post'])
    def toggle_status(self, request, pk=None):
        """Toggle store active/inactive status."""
        store = self.get_object()
        if store.status == 'active':
            store.status = 'inactive'
        else:
            store.status = 'active'
        store.save(update_fields=['status', 'updated_at'])
        return Response({'status': store.status})


class StoreIntegrationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store integrations."""
    
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        store_id = self.kwargs.get('store_pk')
        if store_id:
            return StoreIntegration.objects.filter(store_id=store_id)
        
        user = self.request.user
        if user.is_staff:
            return StoreIntegration.objects.all()
        return StoreIntegration.objects.filter(
            Q(store__owner=user) | Q(store__staff=user)
        ).distinct()
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return StoreIntegrationCreateSerializer
        return StoreIntegrationSerializer
    
    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """Toggle integration enabled/disabled."""
        integration = self.get_object()
        integration.is_enabled = not integration.is_enabled
        integration.save(update_fields=['is_enabled', 'updated_at'])
        return Response({'is_enabled': integration.is_enabled})
    
    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Test integration connection."""
        integration = self.get_object()
        result = store_service.test_integration(integration)
        return Response(result)


class StoreWebhookViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store webhooks."""
    
    serializer_class = StoreWebhookSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        store_id = self.kwargs.get('store_pk')
        if store_id:
            return StoreWebhook.objects.filter(store_id=store_id)
        
        user = self.request.user
        if user.is_staff:
            return StoreWebhook.objects.all()
        return StoreWebhook.objects.filter(
            Q(store__owner=user) | Q(store__staff=user)
        ).distinct()
    
    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Send a test webhook."""
        webhook = self.get_object()
        result = webhook_service.test_webhook(webhook)
        return Response(result)
