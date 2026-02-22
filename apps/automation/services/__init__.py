# -*- coding: utf-8 -*-
from .session_manager import SessionManager, SessionContext, get_session_manager

# Import existing AutomationService
from .automation_service import AutomationService

# Unified LLM Orchestrator Service
from .unified_service import LLMOrchestratorService, ResponseSource

# Flow Builder (POC)
from .flow_executor import FlowExecutor

# Unified Messaging Service (consolidates campaigns, automation, scheduled messages)
from .unified_messaging import UnifiedMessagingService

__all__ = [
    'SessionManager',
    'SessionContext',
    'get_session_manager',
    'AutomationService',
    'LLMOrchestratorService',
    'ResponseSource',
    'FlowExecutor',
    # Unified messaging
    'UnifiedMessagingService',
]
