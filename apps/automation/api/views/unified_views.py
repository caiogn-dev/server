"""
API Views for Unified Automation System

Endpoints para o sistema unificado de automação que integra:
- Templates (AutoMessages)
- Handlers (Intents)
- Agents (LLM)
"""
import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter

from apps.automation.services import LLMOrchestratorService, ResponseSource
from apps.whatsapp.models import WhatsAppAccount
from apps.conversations.models import Conversation

logger = logging.getLogger(__name__)


class UnifiedProcessView(APIView):
    """
    Endpoint para processar mensagens usando o sistema unificado.
    
    O sistema decide automaticamente qual abordagem usar:
    1. Template (se houver template para o evento)
    2. Handler (se intent tiver handler configurado)
    3. Agent (fallback para LLM com contexto)
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Processar mensagem com sistema unificado",
        description="""
        Processa uma mensagem usando o sistema unificado que orquestra entre:
        - Templates (respostas rápidas)
        - Handlers (lógica específica)
        - Agent (LLM com contexto)
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'account_id': {'type': 'string', 'description': 'ID da conta WhatsApp'},
                    'message': {'type': 'string', 'description': 'Mensagem do usuário'},
                    'phone_number': {'type': 'string', 'description': 'Número do telefone'},
                    'use_llm': {'type': 'boolean', 'default': True},
                    'enable_templates': {'type': 'boolean', 'default': True},
                    'enable_handlers': {'type': 'boolean', 'default': True},
                },
                'required': ['account_id', 'message', 'phone_number']
            }
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'content': {'type': 'string'},
                    'source': {'type': 'string', 'enum': ['template', 'handler', 'agent', 'fallback']},
                    'buttons': {'type': 'array', 'items': {'type': 'object'}},
                    'metadata': {'type': 'object'},
                }
            }
        }
    )
    def post(self, request):
        """Processa mensagem usando o sistema unificado."""
        data = request.data
        
        account_id = data.get('account_id')
        message = data.get('message')
        phone_number = data.get('phone_number')
        
        if not all([account_id, message, phone_number]):
            return Response(
                {'error': 'account_id, message e phone_number são obrigatórios'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            account = WhatsAppAccount.objects.get(id=account_id, is_active=True)
        except WhatsAppAccount.DoesNotExist:
            return Response(
                {'error': 'Conta WhatsApp não encontrada'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Busca ou cria conversa
        conversation, _ = Conversation.objects.get_or_create(
            account=account,
            phone_number=phone_number,
            defaults={
                'contact_name': 'Cliente',
                'status': Conversation.ConversationStatus.OPEN
            }
        )
        
        try:
            service = LLMOrchestratorService(
                account=account,
                conversation=conversation,
                use_llm=data.get('use_llm', True),
                debug=True
            )
            response = service.process_message(message)
            
            return Response({
                'content': response.content,
                'source': response.source.value,
                'buttons': response.buttons,
                'metadata': response.metadata,
            })
            
        except Exception as e:
            logger.error(f"[UnifiedAPI] Error processing message: {e}", exc_info=True)
            return Response(
                {'error': f'Erro ao processar mensagem: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UnifiedStatsView(APIView):
    """
    Endpoint para obter estatísticas do sistema unificado.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Estatísticas do sistema unificado",
        parameters=[
            OpenApiParameter(
                name='account_id',
                type=str,
                location=OpenApiParameter.QUERY,
                description='ID da conta WhatsApp'
            ),
        ],
    )
    def get(self, request):
        """Retorna estatísticas do sistema unificado."""
        account_id = request.query_params.get('account_id')
        
        if not account_id:
            return Response(
                {'error': 'account_id é obrigatório'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            account = WhatsAppAccount.objects.get(id=account_id, is_active=True)
        except WhatsAppAccount.DoesNotExist:
            return Response(
                {'error': 'Conta WhatsApp não encontrada'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Retorna estatísticas básicas (em produção, isso viria do cache/banco)
        return Response({
            'templates_used': 0,
            'handlers_used': 0,
            'agent_used': 0,
            'fallbacks': 0,
            'session_context': {
                'account_id': str(account.id),
                'account_name': account.name,
            }
        })
