"""
Utility functions for WebSocket consumers with caching support.
"""
import hashlib
import logging
from functools import wraps
from asgiref.sync import sync_to_async
from django.core.cache import cache
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()

# Cache TTL em segundos
CACHE_TTL_USER = 300  # 5 minutos
CACHE_TTL_CONVERSATION = 60  # 1 minuto
CACHE_TTL_ORDER = 120  # 2 minutos
CACHE_TTL_ACCOUNT = 300  # 5 minutos


def get_cache_key_for_token(token_key: str) -> str:
    """Generate cache key for token (using hash for security)."""
    token_hash = hashlib.sha256(token_key.encode()).hexdigest()[:16]
    return f"ws:user_token:{token_hash}"


def get_cached_user(token_key: str):
    """Get user from cache or database."""
    cache_key = get_cache_key_for_token(token_key)
    
    # Tentar cache
    cached_user_id = cache.get(cache_key)
    if cached_user_id:
        try:
            return User.objects.get(id=cached_user_id)
        except User.DoesNotExist:
            cache.delete(cache_key)
    
    # Buscar no banco
    try:
        token = Token.objects.select_related('user').get(key=token_key)
        user = token.user
        # Cache apenas o ID
        cache.set(cache_key, user.id, CACHE_TTL_USER)
        return user
    except Token.DoesNotExist:
        # Cache negativo para evitar ataques de força bruta
        cache.set(cache_key, None, 60)
        return None


get_cached_user_async = sync_to_async(get_cached_user, thread_sensitive=True)


def cache_user_query(cache_key: str, ttl: int = CACHE_TTL_USER):
    """Decorator to cache user queries."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Try cache first
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            if result is not None:
                cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


async def get_cached_conversation(conversation_id: str):
    """Get conversation with caching."""
    from apps.whatsapp.models import Conversation
    
    cache_key = f"ws:conversation:{conversation_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    try:
        conversation = await sync_to_async(Conversation.objects.get)(id=conversation_id)
        cache.set(cache_key, conversation, CACHE_TTL_CONVERSATION)
        return conversation
    except Conversation.DoesNotExist:
        return None


async def get_cached_order(order_id: str):
    """Get order with caching."""
    from apps.stores.models import StoreOrder
    
    cache_key = f"ws:order:{order_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    try:
        order = await sync_to_async(StoreOrder.objects.get)(id=order_id)
        cache.set(cache_key, order, CACHE_TTL_ORDER)
        return order
    except StoreOrder.DoesNotExist:
        return None


async def get_cached_store(store_id: str):
    """Get store with caching."""
    from apps.stores.models import Store
    
    cache_key = f"ws:store:{store_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    try:
        store = await sync_to_async(Store.objects.get)(id=store_id)
        cache.set(cache_key, store, CACHE_TTL_ACCOUNT)
        return store
    except Store.DoesNotExist:
        return None


async def get_cached_whatsapp_account(account_id: str):
    """Get WhatsApp account with caching."""
    from apps.whatsapp.models import WhatsAppAccount
    
    cache_key = f"ws:whatsapp_account:{account_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    try:
        account = await sync_to_async(WhatsAppAccount.objects.get)(id=account_id)
        cache.set(cache_key, account, CACHE_TTL_ACCOUNT)
        return account
    except WhatsAppAccount.DoesNotExist:
        return None


def invalidate_cache_pattern(pattern: str):
    """Invalidate cache keys matching pattern (Redis only)."""
    try:
        # Try Redis pattern delete
        from django_redis import get_redis_connection
        redis = get_redis_connection("default")
        keys = redis.keys(pattern)
        if keys:
            redis.delete(*keys)
            logger.debug(f"Invalidated {len(keys)} cache keys matching {pattern}")
    except Exception:
        # Fallback: individual delete
        logger.warning("Redis pattern delete not available, cache invalidation skipped")


class CachedAsyncMixin:
    """Mixin to add caching to WebSocket consumers."""
    
    async def get_user_from_token_cached(self, token_key: str):
        """Get user from token with caching."""
        return await get_cached_user_async(token_key)
