# -*- coding: utf-8 -*-
<<<<<<< HEAD
from .context_service import AutomationContext, AutomationContextService
=======
"""
Pastita Automation Services

Orquestradores e serviços de automação para WhatsApp.
"""

# Orquestrador Legacy (estável)
from .pastita_orchestrator import (
    PastitaOrchestrator,
    IntentType,
    ResponseSource,
    OrchestratorResponse,
    IntentDetector,
)

# LangGraph Orchestrator (Novo - Completo)
from .pastita_langgraph_orchestrator import (
    LangGraphOrchestrator,
    ContextRouter,
    process_whatsapp_message_langgraph,
    get_orchestrator,
)

# Tools do sistema
from .pastita_tools import (
    PASTITA_TOOLS,
    get_menu,
    get_product_info,
    add_to_cart,
    remove_from_cart,
    view_cart,
    clear_cart,
    calculate_delivery_fee,
    create_order,
    generate_pix,
    check_order_status,
    get_automessage_for_status,
    send_whatsapp_message,
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
    # Orquestrador Legacy
    'PastitaOrchestrator',
    'IntentType',
    'ResponseSource',
    'OrchestratorResponse',
    'IntentDetector',
    # LangGraph Orchestrator
    'LangGraphOrchestrator',
    'ContextRouter',
    'process_whatsapp_message_langgraph',
    'get_orchestrator',
    # Tools
    'PASTITA_TOOLS',
    'get_menu',
    'get_product_info',
    'add_to_cart',
    'remove_from_cart',
    'view_cart',
    'clear_cart',
    'calculate_delivery_fee',
    'create_order',
    'generate_pix',
    'check_order_status',
    'get_automessage_for_status',
    'send_whatsapp_message',
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
