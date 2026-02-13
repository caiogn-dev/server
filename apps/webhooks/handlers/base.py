"""
Base handler for webhooks.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from django.http import HttpResponse

from ..models import WebhookEvent


class BaseHandler(ABC):
    """
    Abstract base class for webhook handlers.
    """
    
    @abstractmethod
    def handle(self, event: WebhookEvent, payload: dict, headers: dict) -> Dict[str, Any]:
        """
        Handle a webhook event.
        
        Args:
            event: The webhook event record
            payload: Parsed webhook payload
            headers: Request headers
        
        Returns:
            Dict with handler result
        """
        pass
    
    def handle_verification(self, request) -> HttpResponse:
        """
        Handle verification challenge.
        Default implementation returns 403.
        Override for providers that need challenge-response.
        """
        return HttpResponse("Verification not implemented", status=403)
    
    def validate_payload(self, payload: dict) -> bool:
        """
        Validate webhook payload.
        Default implementation returns True.
        """
        return True
    
    def extract_store(self, payload: dict) -> Optional['Store']:
        """
        Extract store context from payload.
        Default implementation returns None.
        """
        return None
