"""
API Views for Agents
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.conf import settings
from drf_spectacular.utils import extend_schema, extend_schema_view

from .models import Agent, AgentConversation, AgentMessage
from .services import LangchainService, AgentService
from .serializers import (
    AgentListSerializer,
    AgentDetailSerializer,
    AgentCreateUpdateSerializer,
    AgentConversationSerializer,
    ProcessMessageSerializer,
    ProcessMessageResponseSerializer,
    AgentStatsSerializer,
)


@extend_schema_view(
    list=extend_schema(summary="Listar agentes"),
    retrieve=extend_schema(summary="Detalhes do agente"),
    create=extend_schema(summary="Criar agente"),
    update=extend_schema(summary="Atualizar agente"),
    destroy=extend_schema(summary="Excluir agente"),
)
class AgentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing AI Agents."""
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'provider']
    
    def get_queryset(self):
        return Agent.objects.filter(is_active=True)
    
    def get_serializer_class(self):
        if self.action == 'list':
            return AgentListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return AgentCreateUpdateSerializer
        return AgentDetailSerializer
    
    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()
    
    @extend_schema(
        summary="Processar mensagem",
        request=ProcessMessageSerializer,
        responses={200: ProcessMessageResponseSerializer}
    )
    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """Process a message through the agent."""
        agent = self.get_object()
        
        serializer = ProcessMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            service = LangchainService(agent)
            result = service.process_message(
                message=serializer.validated_data['message'],
                session_id=serializer.validated_data.get('session_id'),
                phone_number=serializer.validated_data.get('phone_number'),
            )
            return Response(result)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(summary="Estatísticas do agente")
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get agent statistics."""
        agent = self.get_object()
        
        conversations = AgentConversation.objects.filter(agent=agent)
        messages = AgentMessage.objects.filter(conversation__agent=agent)
        
        total_conversations = conversations.count()
        total_messages = messages.count()
        
        # Calculate average response time
        from django.db.models import Avg
        avg_time = messages.filter(response_time_ms__isnull=False).aggregate(
            avg=Avg('response_time_ms')
        )['avg'] or 0
        
        # Active sessions (conversations with recent messages)
        from django.utils import timezone
        from datetime import timedelta
        active_sessions = conversations.filter(
            last_message_at__gte=timezone.now() - timedelta(hours=24)
        ).count()
        
        return Response({
            'total_conversations': total_conversations,
            'total_messages': total_messages,
            'avg_response_time_ms': round(avg_time, 2),
            'active_sessions': active_sessions,
        })
    
    @extend_schema(summary="Conversas do agente")
    @action(detail=True, methods=['get'])
    def conversations(self, request, pk=None):
        """Get agent conversations."""
        agent = self.get_object()
        conversations = AgentConversation.objects.filter(agent=agent).order_by('-last_message_at')
        
        page = self.paginate_queryset(conversations)
        if page is not None:
            serializer = AgentConversationSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = AgentConversationSerializer(conversations, many=True)
        return Response(serializer.data)
    
    @extend_schema(summary="Listar modelos disponíveis por provider")
    @action(detail=False, methods=['get'])
    def available_models(self, request):
        """Get available models for each provider."""
        models = {
            'kimi': [
                {'value': 'kimi-for-coding', 'label': 'Kimi for Coding'},
                {'value': 'kimi-k2', 'label': 'Kimi K2'},
                {'value': 'kimi-k2.5', 'label': 'Kimi K2.5'},
            ],
            'openai': [
                {'value': 'gpt-4o', 'label': 'GPT-4o'},
                {'value': 'gpt-4o-mini', 'label': 'GPT-4o Mini'},
                {'value': 'gpt-4-turbo', 'label': 'GPT-4 Turbo'},
            ],
            'anthropic': [
                {'value': 'claude-opus-4', 'label': 'Claude Opus 4'},
                {'value': 'claude-sonnet-4', 'label': 'Claude Sonnet 4'},
                {'value': 'claude-haiku-4', 'label': 'Claude Haiku 4'},
            ],
            'ollama': [
                {'value': 'llama3', 'label': 'Llama 3'},
                {'value': 'mistral', 'label': 'Mistral'},
                {'value': 'codellama', 'label': 'Code Llama'},
            ]
        }
        return Response(models)

    
    @extend_schema(summary="Configuração dos providers (base URLs do backend)")
    @action(detail=False, methods=['get'])
    def provider_config(self, request):
        """Get provider configuration including base URLs from backend."""
        config = {
            'kimi': {
                'base_url': getattr(settings, 'KIMI_BASE_URL', 'https://api.kimi.com/coding/'),
                'model_name': getattr(settings, 'KIMI_MODEL_NAME', 'kimi-for-coding'),
                'api_style': 'anthropic',
            },
            'openai': {
                'base_url': getattr(settings, 'OPENAI_BASE_URL', 'https://api.openai.com/v1'),
                'model_name': getattr(settings, 'OPENAI_MODEL_NAME', 'gpt-4o-mini'),
                'api_style': 'openai',
            },
            'anthropic': {
                'base_url': getattr(settings, 'ANTHROPIC_BASE_URL', 'https://api.anthropic.com/v1'),
                'model_name': getattr(settings, 'ANTHROPIC_MODEL_NAME', 'claude-3-5-sonnet-20241022'),
                'api_style': 'anthropic',
            },
            'ollama': {
                'base_url': getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434'),
                'model_name': getattr(settings, 'OLLAMA_MODEL_NAME', 'llama3'),
                'api_style': 'openai',
            },
        }
        return Response(config)


class AgentConversationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for agent conversations."""
    serializer_class = AgentConversationSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'session_id'
    
    def get_queryset(self):
        return AgentConversation.objects.filter(
            agent__is_active=True
        ).order_by('-last_message_at')
    
    @extend_schema(summary="Histórico da conversa")
    @action(detail=True, methods=['get'])
    def history(self, request, session_id=None):
        """Get conversation history from memory."""
        conversation = self.get_object()
        service = LangchainService(conversation.agent)
        history = service.get_conversation_history(str(session_id))
        return Response(history)
    
    @extend_schema(summary="Limpar memória da conversa")
    @action(detail=True, methods=['post'])
    def clear_memory(self, request, session_id=None):
        """Clear conversation memory."""
        conversation = self.get_object()
        service = LangchainService(conversation.agent)
        success = service.clear_memory(str(session_id))
        return Response({'success': success})
