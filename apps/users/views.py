"""
Views para UnifiedUser API.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.db.models import Q

from .models import UnifiedUser, UnifiedUserActivity
from .serializers import (
    UnifiedUserSerializer,
    UnifiedUserListSerializer,
    UnifiedUserActivitySerializer,
)


def _phones_for_user(request_user):
    """Return a Q filter scoping UnifiedUser to contacts of this tenant's stores/accounts."""
    from apps.stores.models import StoreOrder
    from apps.conversations.models import Conversation

    order_phones = StoreOrder.objects.filter(
        store__owner=request_user
    ).values_list('customer_phone', flat=True)

    wa_phones = Conversation.objects.filter(
        account__owner=request_user
    ).values_list('phone_number', flat=True)

    return Q(phone_number__in=order_phones) | Q(phone_number__in=wa_phones)


class UnifiedUserViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciar usuários unificados.
    """
    queryset = UnifiedUser.objects.all()

    def get_permissions(self):
        # Writes are admin-only; reads are scoped to the tenant via get_queryset
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'list':
            return UnifiedUserListSerializer
        return UnifiedUserSerializer

    def get_queryset(self):
        """Filtra por tenant e por query params."""
        user = self.request.user
        if user.is_staff or user.is_superuser:
            base_qs = UnifiedUser.objects.all()
        else:
            base_qs = UnifiedUser.objects.filter(_phones_for_user(user))

        # Filtro por telefone
        phone = self.request.query_params.get('phone')
        if phone:
            base_qs = base_qs.filter(phone_number__icontains=phone)

        # Filtro por email
        email = self.request.query_params.get('email')
        if email:
            base_qs = base_qs.filter(email__icontains=email)

        # Filtro por nome
        name = self.request.query_params.get('name')
        if name:
            base_qs = base_qs.filter(name__icontains=name)

        # Filtro: tem carrinho abandonado
        has_cart = self.request.query_params.get('has_abandoned_cart')
        if has_cart:
            base_qs = base_qs.filter(has_abandoned_cart=True)

        return base_qs

    @action(detail=True, methods=['get'])
    def activities(self, request, pk=None):
        """Retorna atividades do usuário."""
        user = self.get_object()
        activities = user.activities.all()[:50]
        serializer = UnifiedUserActivitySerializer(activities, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def context(self, request, pk=None):
        """Retorna contexto formatado para o agente."""
        user = self.get_object()
        return Response({
            'context': user.get_context_for_agent(),
        })

    @action(detail=False, methods=['get'])
    def by_phone(self, request):
        """Busca usuário por telefone."""
        phone = request.query_params.get('phone')
        if not phone:
            return Response(
                {'error': 'phone parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = self.get_queryset().filter(phone_number=phone).first()
        if not user:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def get_or_create(self, request):
        """Busca ou cria usuário por telefone."""
        phone = request.data.get('phone_number')
        name = request.data.get('name', 'Desconhecido')

        if not phone:
            return Response(
                {'error': 'phone_number required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user, created = UnifiedUser.objects.get_or_create(
            phone_number=phone,
            defaults={'name': name}
        )

        serializer = self.get_serializer(user)
        return Response({
            'user': serializer.data,
            'created': created,
        })


class UnifiedUserActivityViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para atividades (somente leitura)."""
    queryset = UnifiedUserActivity.objects.all()
    serializer_class = UnifiedUserActivitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtra por tenant, usuário e tipo."""
        user = self.request.user
        if user.is_staff or user.is_superuser:
            base_qs = UnifiedUserActivity.objects.all()
        else:
            allowed_users = UnifiedUser.objects.filter(_phones_for_user(user))
            base_qs = UnifiedUserActivity.objects.filter(user__in=allowed_users)

        user_id = self.request.query_params.get('user_id')
        if user_id:
            base_qs = base_qs.filter(user_id=user_id)

        activity_type = self.request.query_params.get('type')
        if activity_type:
            base_qs = base_qs.filter(activity_type=activity_type)

        return base_qs
