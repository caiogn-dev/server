"""
CRM API Views:
  - CustomerSearchView        GET  /stores/{slug}/crm/customers/search/?q=
  - CustomerAddressViewSet    CRUD /stores/{slug}/crm/customers/{user_id}/addresses/
  - TeamMemberViewSet         CRUD /stores/{slug}/team/
  - places_search_view        GET  /stores/admin/places-search/?q=
"""
import logging
import uuid as uuid_module

from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stores.models import Store, StoreTeamMember, StoreOrder
from apps.stores.permissions import has_store_permission, get_member_role
from apps.users.models import UnifiedUser, UserAddress
from ..crm_serializers import (
    CustomerSearchSerializer,
    UserAddressSerializer,
    TeamMemberSerializer,
    TeamMemberCreateSerializer,
)
from .base import IsStoreOwnerOrStaff

logger = logging.getLogger(__name__)


def _get_store(store_slug: str) -> Store:
    """Resolve store by slug or UUID."""
    try:
        uuid_module.UUID(store_slug)
        return get_object_or_404(Store, pk=store_slug)
    except (ValueError, AttributeError):
        return get_object_or_404(Store, slug=store_slug)


# ---------------------------------------------------------------------------
# Customer Search
# ---------------------------------------------------------------------------

class CustomerSearchView(APIView):
    """
    Busca clientes por nome ou telefone.

    GET /api/v1/stores/{store_slug}/crm/customers/search/?q=<texto>&limit=8
    """
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]

    def get(self, request, store_slug):
        store = _get_store(store_slug)

        # Verify the user actually has access to this store
        perm = IsStoreOwnerOrStaff()
        if not perm._user_can_access_store(request.user, store):
            return Response({'detail': 'Sem permissão.'}, status=status.HTTP_403_FORBIDDEN)

        q = request.query_params.get('q', '').strip()
        if len(q) < 2:
            return Response([])

        try:
            limit = min(int(request.query_params.get('limit', 8)), 20)
        except (ValueError, TypeError):
            limit = 8

        users = (
            UnifiedUser.objects
            .filter(Q(name__icontains=q) | Q(phone_number__icontains=q))
            .filter(
                Q(addresses__tenant=store)
                | Q(django_user__store_orders__store=store)
            )
            .distinct()
            .prefetch_related(
                Prefetch(
                    'addresses',
                    queryset=UserAddress.objects.filter(tenant=store),
                    to_attr='_store_addresses',
                )
            )[:limit]
        )

        serializer = CustomerSearchSerializer(
            users,
            many=True,
            context={'store': store, 'request': request},
        )
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Customer Address ViewSet
# ---------------------------------------------------------------------------

class CustomerAddressViewSet(viewsets.ModelViewSet):
    """
    CRUD de endereços de um cliente para uma loja específica.

    URLs geradas manualmente em urls.py:
      GET/POST    /stores/{slug}/crm/customers/{user_id}/addresses/
      GET/PATCH/DELETE  /stores/{slug}/crm/customers/{user_id}/addresses/{id}/
    """
    serializer_class = UserAddressSerializer
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]

    def _get_store(self):
        return _get_store(self.kwargs['store_slug'])

    def _get_unified_user(self):
        return get_object_or_404(UnifiedUser, pk=self.kwargs['user_id'])

    def get_queryset(self):
        store = self._get_store()
        user = self._get_unified_user()
        return UserAddress.objects.filter(unified_user=user, tenant=store)

    def perform_create(self, serializer):
        store = self._get_store()
        # Minimum permission: operator (can do 'orders')
        if not has_store_permission(self.request.user, store, 'orders'):
            raise PermissionDenied("Permissão insuficiente para gerenciar endereços.")
        unified_user = self._get_unified_user()
        serializer.save(
            unified_user=unified_user,
            tenant=store,
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        store = self._get_store()
        if not has_store_permission(self.request.user, store, 'orders'):
            raise PermissionDenied("Permissão insuficiente para gerenciar endereços.")
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        store = self._get_store()
        if not has_store_permission(self.request.user, store, 'orders'):
            raise PermissionDenied("Permissão insuficiente para gerenciar endereços.")
        instance.delete()


# ---------------------------------------------------------------------------
# Team Member ViewSet
# ---------------------------------------------------------------------------

class TeamMemberViewSet(viewsets.ModelViewSet):
    """
    CRUD de membros da equipe de uma loja.

    Somente usuários com permissão 'team' (owner) podem criar/deletar.
    DELETE faz soft delete (is_active=False) — não deleta o owner.

    URLs via urls.py:
      GET/POST  /stores/{slug}/team/
      GET/PATCH/DELETE  /stores/{slug}/team/{id}/
    """
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]

    def _get_store(self):
        return _get_store(self.kwargs['store_slug'])

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return TeamMemberCreateSerializer
        return TeamMemberSerializer

    def get_queryset(self):
        store = self._get_store()
        return StoreTeamMember.objects.filter(
            tenant=store,
            is_active=True,
        ).select_related('user', 'invited_by')

    def perform_create(self, serializer):
        store = self._get_store()
        if not has_store_permission(self.request.user, store, 'team'):
            raise PermissionDenied("Apenas o dono ou gerente pode gerenciar a equipe.")
        serializer.save(
            tenant=store,
            invited_by=self.request.user,
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        store = self._get_store()
        if not has_store_permission(self.request.user, store, 'team'):
            raise PermissionDenied("Apenas o dono ou gerente pode gerenciar a equipe.")
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        store = self._get_store()
        if not has_store_permission(self.request.user, store, 'team'):
            raise PermissionDenied("Apenas o dono ou gerente pode gerenciar a equipe.")
        # Não deletar o dono
        if instance.role == StoreTeamMember.Role.OWNER:
            raise PermissionDenied("Não é possível remover o dono da loja.")
        # Soft delete
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])


# ---------------------------------------------------------------------------
# Admin Places Search
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def places_search_view(request):
    """
    Busca estabelecimentos via Google Places Text Search.
    Uso exclusivo do admin para configurar coordenadas de uma nova loja.

    GET /api/v1/stores/admin/places-search/?q=<texto>
    """
    q = request.query_params.get('q', '').strip()
    if len(q) < 3:
        return Response([])
    from apps.stores.services.geo.google_provider import GoogleMapsProvider
    results = GoogleMapsProvider().search_places(q)
    return Response(results)
