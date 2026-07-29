"""
Bio link (Link na Bio) management API views.
"""
import uuid as uuid_module
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.stores import billing
from apps.stores.models import Store, StoreBioLink
from apps.core.permissions import StoreQuerysetMixin
from ..serializers import BioLinkSerializer
from .base import IsStoreOwnerOrStaff

UPGRADE_MSG = 'Links personalizados são exclusivos dos planos Pro e Premium. Faça upgrade do plano.'


def _resolve_store(store_param):
    """Resolve a store by UUID or slug, following the coupon view's idiom."""
    if not store_param:
        return None
    try:
        uuid_module.UUID(store_param)
        return Store.objects.filter(id=store_param).first()
    except (ValueError, AttributeError):
        return Store.objects.filter(slug=store_param).first()


class BioLinkViewSet(StoreQuerysetMixin, viewsets.ModelViewSet):
    """ViewSet for managing a store's Link na Bio entries."""

    queryset = StoreBioLink.objects.all()
    serializer_class = BioLinkSerializer
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

        return qs.select_related('store').order_by('sort_order', 'created_at')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        store = serializer.validated_data['store']
        if not billing.plan_allows(store, 'bio_custom_links'):
            return Response({'detail': UPGRADE_MSG}, status=status.HTTP_403_FORBIDDEN)
        serializer.save()
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        if not billing.plan_allows(instance.store, 'bio_custom_links'):
            return Response({'detail': UPGRADE_MSG}, status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        store_param = request.data.get('store')
        order = request.data.get('order') or []

        store = _resolve_store(store_param)
        if not store:
            return Response({'detail': 'Loja não encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        # Escopo por acesso do usuário (mesma queryset usada em list/retrieve).
        links = {str(link.id): link for link in self.get_queryset().filter(store_id=store.id)}
        if not links:
            return Response({'detail': 'Loja não encontrada ou sem links.'}, status=status.HTTP_404_NOT_FOUND)

        for pos, link_id in enumerate(order):
            link = links.get(str(link_id))
            if link and link.sort_order != pos:
                link.sort_order = pos
                link.save(update_fields=['sort_order'])

        return Response({'ok': True})
