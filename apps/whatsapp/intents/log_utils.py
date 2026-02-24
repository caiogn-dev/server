"""
Intent Log Utilities - Funções para salvar logs de intenções
"""
import logging
from typing import Optional, Dict, Any
from django.utils import timezone

from apps.whatsapp.models.intent_models import IntentLog
from apps.whatsapp.intents.detector import IntentType

logger = logging.getLogger(__name__)


def save_intent_log(
    phone_number: str,
    message_text: str,
    intent_type: str,
    method: str,
    confidence: float,
    account_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    message_id: Optional[str] = None,
    handler_used: str = '',
    response_text: str = '',
    response_type: str = 'text',
    processing_time_ms: int = 0,
    context: Optional[Dict[str, Any]] = None,
    entities: Optional[Dict[str, Any]] = None,
) -> Optional[IntentLog]:
    """
    Salva um log de detecção de intenção.
    
    Args:
        phone_number: Número de telefone do usuário
        message_text: Texto da mensagem
        intent_type: Tipo da intenção detectada
        method: Método de detecção ('regex', 'llm', 'none')
        confidence: Confiança da detecção (0-1)
        account_id: ID da conta WhatsApp (opcional)
        conversation_id: ID da conversa (opcional)
        message_id: ID da mensagem (opcional)
        handler_used: Handler utilizado para responder
        response_text: Texto da resposta
        response_type: Tipo da resposta ('text', 'buttons', 'list', 'interactive', 'template')
        processing_time_ms: Tempo de processamento em ms
        context: Contexto adicional (opcional)
        entities: Entidades extraídas (opcional)
    
    Returns:
        IntentLog criado ou None em caso de erro
    """
    try:
        log = IntentLog.objects.create(
            phone_number=phone_number,
            message_text=message_text[:1000],  # Limita tamanho
            intent_type=intent_type,
            method=method,
            confidence=confidence,
            account_id=account_id,
            conversation_id=conversation_id,
            message_id=message_id,
            handler_used=handler_used,
            response_text=response_text[:2000],  # Limita tamanho
            response_type=response_type,
            processing_time_ms=processing_time_ms,
            context=context or {},
            entities=entities or {},
        )
        
        logger.debug(f"Intent log saved: {intent_type} ({method}) - {phone_number}")
        return log
        
    except Exception as e:
        logger.error(f"Error saving intent log: {str(e)}")
        return None


def log_intent_detection(
    detection_result: Dict[str, Any],
    phone_number: str,
    message_text: str,
    account_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    message_id: Optional[str] = None,
    handler_used: str = '',
    response_text: str = '',
    response_type: str = 'text',
    processing_time_ms: int = 0,
) -> Optional[IntentLog]:
    """
    Salva log a partir do resultado da detecção.
    
    Args:
        detection_result: Resultado do detector de intenções
        phone_number: Número de telefone
        message_text: Texto da mensagem
        account_id: ID da conta
        conversation_id: ID da conversa
        message_id: ID da mensagem
        handler_used: Handler utilizado
        response_text: Texto da resposta
        response_type: Tipo da resposta
        processing_time_ms: Tempo de processamento
    
    Returns:
        IntentLog criado ou None
    """
    intent = detection_result.get('intent')
    intent_type = intent.value if isinstance(intent, IntentType) else str(intent)
    
    return save_intent_log(
        phone_number=phone_number,
        message_text=message_text,
        intent_type=intent_type,
        method=detection_result.get('method', 'none'),
        confidence=detection_result.get('confidence', 0.0),
        account_id=account_id,
        conversation_id=conversation_id,
        message_id=message_id,
        handler_used=handler_used,
        response_text=response_text,
        response_type=response_type,
        processing_time_ms=processing_time_ms,
        entities=detection_result.get('entities', {}),
    )
