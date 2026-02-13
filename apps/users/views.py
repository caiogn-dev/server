"""
Views para UnifiedUser API.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from .models import UnifiedUser, UnifiedUserActivity
from .serializers import (
    UnifiedUserSerializer,
    UnifiedUserListSerializer,
    UnifiedUserActivitySerializer,
)


class UnifiedUserViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciar usuários unificados.
    """
    queryset = UnifiedUser.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return UnifiedUserListSerializer
        return UnifiedUserSerializer
    
    def get_queryset(self):
        """Filtra por query params."""
        queryset = super().get_queryset()
        
        # Filtro por telefone
        phone = self.request.query_params.get('phone')
        if phone:
            queryset = queryset.filter(phone_number__icontains=phone)
        
        # Filtro por email
        email = self.request.query_params.get('email')
        if email:
            queryset = queryset.filter(email__icontains=email)
        
        # Filtro por nome
        name = self.request.query_params.get('name')
        if name:
            queryset = queryset.filter(name__icontains=name)
        
        # Filtro: tem carrinho abandonado
        has_cart = self.request.query_params.get('has_abandoned_cart')
        if has_cart:
            queryset = queryset.filter(has_abandoned_cart=True)
        
        return queryset
    
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
        
        user = get_object_or_404(UnifiedUser, phone_number=phone)
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
        """Filtra por usuário se especificado."""
        queryset = super().get_queryset()
        
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        activity_type = self.request.query_params.get('type')
        if activity_type:
            queryset = queryset.filter(activity_type=activity_type)
        
        return queryset
