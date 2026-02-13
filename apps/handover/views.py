"""
Views para Handover Protocol

Endpoints:
- POST /api/v1/conversations/<id>/handover/bot/     -> Transferir para Bot
- POST /api/v1/conversations/<id>/handover/human/   -> Transferir para Humano
- GET  /api/v1/conversations/<id>/handover/status/  -> Ver status atual
- GET  /api/v1/conversations/<id>/handover/logs/    -> Ver histórico
- POST /api/v1/conversations/<id>/handover/request/ -> Solicitar handover
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q
from apps.conversations.models import Conversation
from .models import (
    ConversationHandover,
    HandoverRequest,
    HandoverLog,
    HandoverStatus,
    HandoverRequestStatus,
)
from .serializers import (
    ConversationHandoverSerializer,
    HandoverRequestSerializer,
    CreateHandoverRequestSerializer,
    ApproveHandoverRequestSerializer,
    HandoverLogSerializer,
    TransferToBotSerializer,
    TransferToHumanSerializer,
    HandoverStatusResponseSerializer,
)


class IsStoreMember(permissions.BasePermission):
    """Permissão para membros da loja."""
    
    def has_object_permission(self, request, view, obj):
        # Verificar se usuário é membro da loja da conversa
        if hasattr(obj, 'store'):
            return obj.store.members.filter(id=request.user.id).exists()
        if hasattr(obj, 'conversation'):
            return obj.conversation.store.members.filter(id=request.user.id).exists()
        return False


class HandoverViewSet(viewsets.ViewSet):
    """
    ViewSet para gerenciar handover de conversas.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_conversation(self, pk):
        """Obtém a conversa pelo ID."""
        return get_object_or_404(Conversation, pk=pk)
    
    def get_or_create_handover(self, conversation):
        """Obtém ou cria o registro de handover."""
        handover, created = ConversationHandover.objects.get_or_create(
            conversation=conversation,
            defaults={'status': HandoverStatus.BOT}
        )
        return handover

    @action(detail=True, methods=['post'])
    def bot(self, request, pk=None):
        """
        Transfere a conversa para o Bot.
        
        POST /api/v1/conversations/<id>/handover/bot/
        """
        conversation = self.get_conversation(pk)
        handover = self.get_or_create_handover(conversation)
        
        # Validar dados
        serializer = TransferToBotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Realizar transferência
        handover.transfer_to_bot(
            user=request.user,
            reason=serializer.validated_data.get('reason', '')
        )
        
        return Response({
            'success': True,
            'handover_status': handover.status,
            'status_display': handover.get_status_display(),
            'message': 'Conversa transferida para o bot'
        })

    @action(detail=True, methods=['post'])
    def human(self, request, pk=None):
        """
        Transfere a conversa para Atendimento Humano.
        
        POST /api/v1/conversations/<id>/handover/human/
        """
        conversation = self.get_conversation(pk)
        handover = self.get_or_create_handover(conversation)
        
        # Validar dados
        serializer = TransferToHumanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Obter usuário atribuído (se informado)
        assigned_to_id = serializer.validated_data.get('assigned_to_id')
        assigned_to = None
        if assigned_to_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                assigned_to = User.objects.get(id=assigned_to_id)
            except User.DoesNotExist:
                pass
        
        # Realizar transferência
        handover.transfer_to_human(
            user=request.user,
            assigned_to=assigned_to or request.user,
            reason=serializer.validated_data.get('reason', '')
        )
        
        return Response({
            'success': True,
            'handover_status': handover.status,
            'status_display': handover.get_status_display(),
            'assigned_to': str(handover.assigned_to.id) if handover.assigned_to else None,
            'assigned_to_name': handover.assigned_to.get_full_name() if handover.assigned_to else None,
            'message': 'Conversa transferida para atendimento humano'
        })

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """
        Retorna o status atual do handover.
        
        GET /api/v1/conversations/<id>/handover/status/
        """
        conversation = self.get_conversation(pk)
        handover = self.get_or_create_handover(conversation)
        
        response_data = {
            'handover_status': handover.status,
            'status_display': handover.get_status_display(),
            'assigned_to': None,
            'assigned_to_name': None,
            'last_transfer_at': handover.last_transfer_at,
            'last_transfer_reason': handover.transfer_reason,
        }
        
        if handover.assigned_to:
            response_data['assigned_to'] = str(handover.assigned_to.id)
            response_data['assigned_to_name'] = (
                handover.assigned_to.get_full_name() or 
                handover.assigned_to.username
            )
        
        return Response(response_data)

    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        """
        Retorna o histórico de transferências.
        
        GET /api/v1/conversations/<id>/handover/logs/
        """
        conversation = self.get_conversation(pk)
        logs = HandoverLog.objects.filter(conversation=conversation)[:50]
        serializer = HandoverLogSerializer(logs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def request(self, request, pk=None):
        """
        Solicita transferência para atendimento humano.
        
        POST /api/v1/conversations/<id>/handover/request/
        """
        conversation = self.get_conversation(pk)
        
        # Validar dados
        serializer = CreateHandoverRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Criar solicitação
        handover_request = HandoverRequest.objects.create(
            conversation=conversation,
            requested_by=request.user,
            reason=serializer.validated_data.get('reason', ''),
            priority=serializer.validated_data.get('priority', 'medium'),
            status=HandoverRequestStatus.PENDING
        )
        
        # Notificar operadores (via WebSocket)
        from .models import notify_handover_update
        # TODO: Implementar notificação específica para nova solicitação
        
        return Response({
            'success': True,
            'request_id': str(handover_request.id),
            'status': handover_request.status,
            'message': 'Solicitação de handover criada'
        }, status=status.HTTP_201_CREATED)


class HandoverRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciar solicitações de handover.
    """
    serializer_class = HandoverRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Retorna solicitações visíveis para o usuário."""
        user = self.request.user
        
        # Se é superusuário, vê tudo
        if user.is_superuser:
            return HandoverRequest.objects.all()
        
        # Se é operador, vê solicitações pendentes da loja
        # e solicitações atribuídas a ele
        return HandoverRequest.objects.filter(
            Q(status=HandoverRequestStatus.PENDING) |
            Q(assigned_to=user) |
            Q(requested_by=user)
        ).distinct()
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """
        Aprova uma solicitação de handover.
        
        POST /api/v1/handover-requests/<id>/approve/
        """
        handover_request = self.get_object()
        
        if handover_request.status != HandoverRequestStatus.PENDING:
            return Response(
                {'error': 'Esta solicitação já foi processada'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validar dados
        serializer = ApproveHandoverRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Obter usuário atribuído
        assigned_to = request.user
        assigned_to_id = serializer.validated_data.get('assigned_to_id')
        if assigned_to_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                assigned_to = User.objects.get(id=assigned_to_id)
            except User.DoesNotExist:
                pass
        
        # Aprovar solicitação
        handover_request.approve(user=request.user, assigned_to=assigned_to)
        
        return Response({
            'success': True,
            'message': 'Solicitação aprovada',
            'conversation_id': str(handover_request.conversation.id),
            'assigned_to': str(assigned_to.id)
        })
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """
        Rejeita uma solicitação de handover.
        
        POST /api/v1/handover-requests/<id>/reject/
        """
        handover_request = self.get_object()
        
        if handover_request.status != HandoverRequestStatus.PENDING:
            return Response(
                {'error': 'Esta solicitação já foi processada'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        handover_request.reject(user=request.user)
        
        return Response({
            'success': True,
            'message': 'Solicitação rejeitada'
        })


class HandoverLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para visualizar logs de handover.
    """
    serializer_class = HandoverLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Retorna logs visíveis para o usuário."""
        user = self.request.user
        
        if user.is_superuser:
            return HandoverLog.objects.all()
        
        # Logs de conversas da loja do usuário
        # (assumindo que o usuário tem uma loja associada)
        return HandoverLog.objects.filter(
            conversation__store__members=user
        )
