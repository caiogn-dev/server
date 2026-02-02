"""
Base provider interface for all messaging channels.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.messaging.models import Message
    from apps.stores.models import Store


@dataclass
class ProviderResult:
    """Result of a message send operation."""
    success: bool
    external_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw_response: Optional[Dict] = None


class BaseProvider(ABC):
    """
    Abstract base class for all messaging providers.
    """
    
    channel: str = ''
    
    @abstractmethod
    def send(self, message: 'Message', store: Optional['Store'] = None) -> ProviderResult:
        """
        Send a message.
        
        Args:
            message: The message to send
            store: Optional store context
        
        Returns:
            ProviderResult with send status
        """
        pass
    
    @abstractmethod
    def validate_recipient(self, recipient: str) -> bool:
        """
        Validate a recipient address.
        
        Args:
            recipient: Recipient address (phone, email, etc.)
        
        Returns:
            True if valid, False otherwise
        """
        pass
    
    def format_recipient(self, recipient: str) -> str:
        """
        Format recipient address for this provider.
        Default implementation returns as-is.
        """
        return recipient
    
    def get_status(self, external_id: str) -> Optional[str]:
        """
        Get message status from provider.
        Default implementation returns None.
        """
        return None
    
    def cancel(self, external_id: str) -> bool:
        """
        Cancel a message if possible.
        Default implementation returns False.
        """
        return False
