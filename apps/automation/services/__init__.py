# -*- coding: utf-8 -*-
from .session_manager import SessionManager, SessionContext, get_session_manager

# Import existing AutomationService to avoid breaking imports
from .automation_service import AutomationService

# Flow Builder (POC)
from .flow_executor import FlowExecutor

__all__ = [
    'SessionManager',
    'SessionContext',
    'get_session_manager',
    'AutomationService',
    'FlowExecutor',
]
