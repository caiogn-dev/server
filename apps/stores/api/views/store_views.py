"""
Store management API views.
"""
import logging
import uuid as uuid_module
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from django.db.models import Subquery, OuterRef, Count, Avg, IntegerField, FloatField
from django.db.models.functions import Coalesce
from apps.stores.models import (
    Store, StoreIntegration, StoreWebhook, StoreReview, StoreProduct, StoreOrder,
)
from apps.stores.services import store_service, webhook_service
from apps.core.permissions import accessible_store_ids


def _count_sq(model, **filters):
    """Subquery de COUNT por loja (isolada — não cria JOIN cartesiano)."""
    return Coalesce(
        Subquery(
            model.objects.filter(store=OuterRef('pk'), **filters)
            .order_by().values('store').annotate(c=Count('*')).values('c')[:1],
            output_field=IntegerField(),
        ),
        0,
    )


def _annotate_store_counts(qs):
    """Anota os 5 contadores do StoreSerializer (anno_*) numa query só."""
    return qs.annotate(
        anno_reviews_count=_count_sq(StoreReview, is_public=True),
        anno_integrations_count=_count_sq(StoreIntegration, is_active=True),
        anno_products_count=_count_sq(StoreProduct, status='active'),
        anno_orders_count=_count_sq(StoreOrder),
        anno_avg_rating=Subquery(
            StoreReview.objects.filter(store=OuterRef('pk'), is_public=True)
            .order_by().values('store').annotate(a=Avg('rating')).values('a')[:1],
            output_field=FloatField(),
        ),
    )
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
        if user.is_superuser:
            qs = Store.objects.all()
        else:
            qs = Store.objects.filter(id__in=accessible_store_ids(user))
        return _annotate_store_counts(qs)
    
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

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Explicitly activate a store."""
        store = self.get_object()
        store.status = 'active'
        store.save(update_fields=['status', 'updated_at'])
        return Response({'status': store.status})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Explicitly deactivate a store."""
        store = self.get_object()
        store.status = 'inactive'
        store.save(update_fields=['status', 'updated_at'])
        return Response({'status': store.status})

    @action(detail=True, methods=['post'], url_path='sync_pastita')
    def sync_pastita(self, request, pk=None):
        """Sync Pastita template catalog into the target store."""
        store = self.get_object()
        result = store_service.sync_pastita_to_store(store)
        return Response({
            'message': 'Sincronizacao concluida com sucesso',
            'synced': {
                'products': result.get('products_synced', 0),
                'categories': result.get('categories_synced', 0),
            },
            'source_store': result.get('source_store'),
        })


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
        store_ids = accessible_store_ids(user)
        return StoreIntegration.objects.filter(store_id__in=store_ids)
    
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
        store_ids = accessible_store_ids(user)
        return StoreWebhook.objects.filter(store_id__in=store_ids)
    
    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Send a test webhook."""
        webhook = self.get_object()
        result = webhook_service.test_webhook(webhook)
        return Response(result)
