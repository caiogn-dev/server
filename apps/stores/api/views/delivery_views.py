"""
Delivery zone management API views.
"""
import uuid as uuid_module
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q, Avg

from apps.stores.models import Store, StoreDeliveryZone
from ..serializers import StoreDeliveryZoneSerializer, StoreDeliveryZoneCreateSerializer
from .base import IsStoreOwnerOrStaff


class StoreDeliveryZoneViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store delivery zones."""
    
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        user = self.request.user
        store_param = self.request.query_params.get('store')
        
        if user.is_staff:
            queryset = StoreDeliveryZone.objects.all()
        else:
            user_stores = Store.objects.filter(
                Q(owner=user) | Q(staff=user)
            ).values_list('id', flat=True)
            queryset = StoreDeliveryZone.objects.filter(store_id__in=user_stores)
        
        if store_param:
            try:
                uuid_module.UUID(store_param)
                queryset = queryset.filter(store_id=store_param)
            except (ValueError, AttributeError):
                queryset = queryset.filter(store__slug=store_param)
        
        return queryset.select_related('store').order_by('sort_order', 'distance_band', 'min_km')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return StoreDeliveryZoneCreateSerializer
        return StoreDeliveryZoneSerializer
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle zone active status."""
        zone = self.get_object()
        zone.is_active = not zone.is_active
        zone.save(update_fields=['is_active', 'updated_at'])
        return Response({
            'id': str(zone.id),
            'is_active': zone.is_active,
            'message': f"Zona {'ativada' if zone.is_active else 'desativada'}"
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get delivery zone statistics."""
        store_id = request.query_params.get('store')
        queryset = self.get_queryset()
        
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        
        active_zones = queryset.filter(is_active=True)
        aggregates = active_zones.aggregate(
            avg_fee=Avg('delivery_fee'),
            avg_days=Avg('estimated_days')
        )
        
        stats = {
            'total': queryset.count(),
            'active': active_zones.count(),
            'inactive': queryset.filter(is_active=False).count(),
            'avg_fee': float(aggregates['avg_fee'] or 0),
            'avg_days': float(aggregates['avg_days'] or 0),
            'by_type': {}
        }
        
        for zone_type, _ in StoreDeliveryZone.ZoneType.choices:
            stats['by_type'][zone_type] = queryset.filter(zone_type=zone_type).count()
        
        return Response(stats)
    
    @action(detail=False, methods=['post'])
    def calculate_fee(self, request):
        """Calculate delivery fee for a given location."""
        store_id = request.data.get('store')
        distance_km = request.data.get('distance_km')
        zip_code = request.data.get('zip_code')
        
        if not store_id:
            return Response({'error': 'store is required'}, status=400)
        
        zones = StoreDeliveryZone.objects.filter(
            store_id=store_id,
            is_active=True
        ).order_by('sort_order')
        
        for zone in zones:
            if distance_km and zone.matches_distance(distance_km):
                return Response({
                    'fee': str(zone.calculate_fee(distance_km)),
                    'zone_id': str(zone.id),
                    'zone_name': zone.name,
                    'estimated_minutes': zone.estimated_minutes,
                    'available': True
                })
            elif zip_code and zone.matches_zip_code(zip_code):
                return Response({
                    'fee': str(zone.delivery_fee),
                    'zone_id': str(zone.id),
                    'zone_name': zone.name,
                    'estimated_minutes': zone.estimated_minutes,
                    'available': True
                })
        
        store = get_object_or_404(Store, id=store_id)
        return Response({
            'fee': str(store.default_delivery_fee),
            'zone_id': None,
            'zone_name': 'Padrão',
            'estimated_minutes': 45,
            'available': True
        })
