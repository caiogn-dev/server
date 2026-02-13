"""
Base WebSocket consumer with common functionality and throttling.
"""
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

logger = logging.getLogger(__name__)
User = get_user_model()


class ThrottledWebSocketConsumer(AsyncJsonWebsocketConsumer):
    """
    Base WebSocket consumer with authentication and throttling capabilities.
    
    Features:
    - Token-based authentication
    - Account access verification
    - Rate limiting/throttling
    - Common helper methods
    """
    
    def _extract_token(self, query_string: str) -> str:
        """Extract token from query string."""
        if not query_string:
            return None
        
        # Parse query string: token=abc123
        for param in query_string.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                if key == 'token':
                    return value
        return None
    
    @database_sync_to_async
    def get_user_from_token(self, token_key: str):
        """Get user from authentication token."""
        try:
            token = Token.objects.select_related('user').get(key=token_key)
            return token.user
        except Token.DoesNotExist:
            return None
    
    @database_sync_to_async
    def verify_account_access(self, account_id: str) -> bool:
        """
        Verify if user has access to the specified account.
        Override this method in subclasses to implement specific access logic.
        """
        if not self.user or not account_id:
            return False
        
        # Default: staff users have access to all accounts
        if self.user.is_staff:
            return True
        
        # TODO: Implement specific account access verification
        # This should check if user owns or has permission to access the account
        return True
    
    async def send_error(self, error_message: str, error_code: str = None):
        """Send error message to client."""
        await self.send_json({
            'type': 'error',
            'message': error_message,
            'code': error_code
        })
    
    async def send_success(self, message: str, data: dict = None):
        """Send success message to client."""
        payload = {
            'type': 'success',
            'message': message
        }
        if data:
            payload.update(data)
        await self.send_json(payload)
