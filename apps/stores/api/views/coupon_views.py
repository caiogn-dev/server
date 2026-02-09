"""
Coupon management API views.
"""
import uuid as uuid_module
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Sum
from django.utils import timezone

from apps.stores.models import Store, StoreCoupon
from ..serializers import StoreCouponSerializer, StoreCouponCreateSerializer
from .base import IsStoreOwnerOrStaff


class StoreCouponViewSet(viewsets.ModelViewSet):
    """ViewSet for managing store coupons."""
    
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    
    def get_queryset(self):
        user = self.request.user
        store_param = self.request.query_params.get('store')
        
        if user.is_staff:
            queryset = StoreCoupon.objects.all()
        else:
            user_stores = Store.objects.filter(
                Q(owner=user) | Q(staff=user)
            ).values_list('id', flat=True)
            queryset = StoreCoupon.objects.filter(store_id__in=user_stores)
        
        if store_param:
            try:
                uuid_module.UUID(store_param)
                queryset = queryset.filter(store_id=store_param)
            except (ValueError, AttributeError):
                queryset = queryset.filter(store__slug=store_param)
        
        return queryset.select_related('store').order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return StoreCouponCreateSerializer
        return StoreCouponSerializer
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """Toggle coupon active status."""
        coupon = self.get_object()
        coupon.is_active = not coupon.is_active
        coupon.save(update_fields=['is_active', 'updated_at'])
        return Response({
            'id': str(coupon.id),
            'is_active': coupon.is_active,
            'message': f"Cupom {'ativado' if coupon.is_active else 'desativado'}"
        })
    
    @action(detail=False, methods=['get'])
    def validate(self, request):
        """Validate a coupon code."""
        code = request.query_params.get('code')
        store_id = request.query_params.get('store')
        subtotal = request.query_params.get('subtotal', 0)
        
        if not code or not store_id:
            return Response(
                {'valid': False, 'error': 'code and store are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            coupon = StoreCoupon.objects.get(
                code__iexact=code,
                store_id=store_id
            )
        except StoreCoupon.DoesNotExist:
            return Response({'valid': False, 'error': 'Cupom não encontrado'})
        
        # Check if coupon is valid
        now = timezone.now()
        
        if not coupon.is_active:
            return Response({'valid': False, 'error': 'Cupom inativo'})
        
        if coupon.valid_from and now < coupon.valid_from:
            return Response({'valid': False, 'error': 'Cupom ainda não é válido'})
        
        if coupon.valid_until and now > coupon.valid_until:
            return Response({'valid': False, 'error': 'Cupom expirado'})
        
        if coupon.max_uses and coupon.used_count >= coupon.max_uses:
            return Response({'valid': False, 'error': 'Limite de uso atingido'})
        
        if coupon.min_order_value and float(subtotal) < float(coupon.min_order_value):
            return Response({
                'valid': False, 
                'error': f'Valor mínimo: R$ {coupon.min_order_value}'
            })
        
        # Calculate discount
        discount = coupon.calculate_discount(float(subtotal))
        
        return Response({
            'valid': True,
            'coupon': StoreCouponSerializer(coupon).data,
            'discount': discount,
            'discount_formatted': f'R$ {discount:.2f}'
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get coupon statistics."""
        store_param = request.query_params.get('store')
        queryset = self.get_queryset()
        
        # Handle store filtering by UUID or slug (same logic as get_queryset)
        if store_param:
            try:
                # Try to parse as UUID
                uuid_module.UUID(store_param)
                queryset = queryset.filter(store_id=store_param)
            except (ValueError, AttributeError):
                # If not UUID, treat as slug
                queryset = queryset.filter(store__slug=store_param)
        
        now = timezone.now()
        stats = {
            'total': queryset.count(),
            'active': queryset.filter(
                is_active=True, 
                valid_from__lte=now, 
                valid_until__gte=now
            ).count(),
            'expired': queryset.filter(valid_until__lt=now).count(),
            'total_usage': queryset.aggregate(total=Sum('used_count'))['total'] or 0,
        }
        
        return Response(stats)
