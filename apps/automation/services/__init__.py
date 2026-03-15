# -*- coding: utf-8 -*-
from .context_service import AutomationContext, AutomationContextService
from .session_manager import SessionManager, SessionContext, get_session_manager

# Import existing AutomationService
from .automation_service import AutomationService

# Unified LLM Orchestrator Service
from .unified_service import (
    LLMOrchestratorService,
    ResponseSource,
    UnifiedResponse,
    UnifiedService,
)

# Flow Builder (POC)
from .flow_executor import FlowExecutor

# Unified Messaging Service (consolidates campaigns, automation, scheduled messages)
from .unified_messaging import UnifiedMessagingService

__all__ = [
    'SessionManager',
    'SessionContext',
    'get_session_manager',
    'AutomationContext',
    'AutomationContextService',
    'AutomationService',
    'LLMOrchestratorService',
    'ResponseSource',
    'UnifiedResponse',
    'UnifiedService',
    'FlowExecutor',
    # Unified messaging
    'UnifiedMessagingService',
]
