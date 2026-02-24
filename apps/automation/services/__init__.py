# -*- coding: utf-8 -*-
<<<<<<< HEAD
from .context_service import AutomationContext, AutomationContextService
=======
"""
Pastita Automation Services

Novo orquestrador 100% - sem compatibilidade legada.
"""

# Novo Orquestrador Completo
from .pastita_orchestrator import (
    PastitaOrchestrator,
    IntentType,
    ResponseSource,
    OrchestratorResponse,
    IntentDetector,
)

# Serviços de sessão
>>>>>>> 51b7318 (feat: implementa novo orquestrador WhatsApp com PIX)
from .session_manager import SessionManager, SessionContext, get_session_manager

# Mensagens unificadas
from .unified_messaging import UnifiedMessagingService

# Legacy - lazy import to avoid AppRegistryNotReady
def AutomationService():
    """Lazy import for AutomationService to avoid AppRegistryNotReady."""
    from .automation_service import AutomationService as _AutomationService
    return _AutomationService()

__all__ = [
    # Novo Orquestrador
    'PastitaOrchestrator',
    'IntentType',
    'ResponseSource',
    'OrchestratorResponse',
    'IntentDetector',
    # Sessão
    'SessionManager',
    'SessionContext',
    'get_session_manager',
<<<<<<< HEAD
    'AutomationContext',
    'AutomationContextService',
=======
    # Legacy
>>>>>>> 51b7318 (feat: implementa novo orquestrador WhatsApp com PIX)
    'AutomationService',
    # Messaging
    'UnifiedMessagingService',
]
