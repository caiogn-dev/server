"""
Base WebSocket consumer with common functionality, throttling, and caching.
"""
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from django.core.cache import cache
import hashlib

# Import cached utilities
from .consumer_cache import (
    get_cached_user_async,
    get_cached_conversation,
    get_cached_order,
    get_cached_store,
    get_cached_whatsapp_account,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class ThrottledWebSocketConsumer(AsyncJsonWebsocketConsumer):
    """
    Base WebSocket consumer with authentication, throttling, and caching.
    
    Features:
    - Token-based authentication with caching
    - Account access verification
    - Rate limiting/throttling
    - Common helper methods with cache support
    """
    
    # Throttling settings
    message_rate_limit = 100  # messages per minute
    connection_rate_limit = 10  # connections per minute
    
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
    
    async def get_user_from_token(self, token_key: str):
        """Get user from authentication token with caching."""
        return await get_cached_user_async(token_key)
    
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
    
    async def get_conversation_cached(self, conversation_id: str):
        """Get conversation with caching."""
        return await get_cached_conversation(conversation_id)
    
    async def get_order_cached(self, order_id: str):
        """Get order with caching."""
        return await get_cached_order(order_id)
    
    async def get_store_cached(self, store_id: str):
        """Get store with caching."""
        return await get_cached_store(store_id)
    
    async def get_whatsapp_account_cached(self, account_id: str):
        """Get WhatsApp account with caching."""
        return await get_cached_whatsapp_account(account_id)
    
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
    
    async def check_rate_limit(self, key: str, limit: int, window: int = 60) -> bool:
        """
        Check if operation is within rate limit.
        
        Args:
            key: Unique identifier for the rate limit (e.g., user_id + action)
            limit: Maximum number of operations
            window: Time window in seconds
        
        Returns:
            True if within limit, False if exceeded
        """
        cache_key = f"ws:ratelimit:{key}"
        current = cache.get(cache_key, 0)
        
        if current >= limit:
            return False
        
        # Use Redis INCR if available, otherwise get+set
        try:
            from django_redis import get_redis_connection
            redis = get_redis_connection("default")
            pipe = redis.pipeline()
            pipe.incr(cache_key)
            pipe.expire(cache_key, window)
            pipe.execute()
        except Exception:
            # Fallback for LocMemCache
            cache.set(cache_key, current + 1, window)
        
        return True
