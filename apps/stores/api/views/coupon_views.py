"""
Coupon management API views.
"""
import uuid as uuid_module
from decimal import Decimal, InvalidOperation
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum
from django.utils import timezone

from apps.stores.models import StoreCoupon
from apps.core.permissions import StoreQuerysetMixin
from ..serializers import StoreCouponSerializer, StoreCouponCreateSerializer
from .base import IsStoreOwnerOrStaff


class StoreCouponViewSet(StoreQuerysetMixin, viewsets.ModelViewSet):
    """ViewSet for managing store coupons."""

    queryset = StoreCoupon.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]
    store_field = 'store'

    def get_queryset(self):
        qs = super().get_queryset()  # StoreQuerysetMixin handles owner/staff scoping
        store_param = self.kwargs.get('store_pk') or self.request.query_params.get('store')

        if store_param:
            try:
                uuid_module.UUID(store_param)
                qs = qs.filter(store_id=store_param)
            except (ValueError, AttributeError):
                qs = qs.filter(store__slug=store_param)

        return qs.select_related('store').order_by('-created_at')
    
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
        """Validate a coupon code.

        Segurança: o cupom é resolvido via self.get_queryset(), que escopa pela
        loja do query param E pelas lojas acessíveis ao usuário (StoreQuerysetMixin).
        Isso evita IDOR cross-tenant (validar cupom de loja alheia pelo ?store=).
        """
        code = request.query_params.get('code')
        store_id = request.query_params.get('store')
        subtotal_raw = request.query_params.get('subtotal', 0)

        if not code or not store_id:
            return Response(
                {'valid': False, 'error': 'code and store are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            subtotal = Decimal(str(subtotal_raw or 0))
        except (InvalidOperation, ValueError, TypeError):
            return Response(
                {'valid': False, 'error': 'subtotal inválido'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            coupon = self.get_queryset().get(code__iexact=code)
        except StoreCoupon.DoesNotExist:
            return Response({'valid': False, 'error': 'Cupom não encontrado'})

        # Validação delegada ao modelo (nomes de campo corretos: usage_limit,
        # min_purchase, etc.) — evita AttributeError de campos inexistentes.
        valid, error = coupon.is_valid(subtotal=subtotal)
        if not valid:
            return Response({'valid': False, 'error': error})

        discount = coupon.calculate_discount(subtotal)

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
