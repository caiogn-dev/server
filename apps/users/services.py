"""
Service layer para UnifiedUser.

Funções utilitárias para trabalhar com usuários unificados.
"""
import logging
from typing import Optional, Dict, Any
from django.core.cache import cache

from .models import UnifiedUser

logger = logging.getLogger(__name__)


class UnifiedUserService:
    """
    Service para gerenciar UnifiedUser.
    """
    
    @staticmethod
    def get_or_create_by_phone(phone_number: str, name: str = None) -> tuple[UnifiedUser, bool]:
        """
        Busca ou cria usuário por telefone.
        Usa UnifiedUser.resolve() para evitar duplicatas por formato de telefone.
        """
        try:
            user, created = UnifiedUser.resolve(phone=phone_number, name=name or "")
            if created:
                logger.info("[UnifiedUser] Created new user: %s (%s)", user.id, phone_number)
            return user, created
        except Exception as exc:
            logger.error("[UnifiedUser] get_or_create_by_phone failed: %s", exc)
            raise
    
    @staticmethod
    def get_by_phone_cached(phone_number: str) -> Optional[UnifiedUser]:
        """
        Busca usuário com cache.
        """
        cache_key = f"unified_user:{phone_number}"
        
        # Tenta do cache
        user_id = cache.get(cache_key)
        if user_id:
            try:
                return UnifiedUser.objects.get(id=user_id)
            except UnifiedUser.DoesNotExist:
                cache.delete(cache_key)
        
        # Busca do banco
        try:
            user = UnifiedUser.objects.get(phone_number=phone_number)
            # Salva no cache (5 minutos)
            cache.set(cache_key, str(user.id), 300)
            return user
        except UnifiedUser.DoesNotExist:
            return None
    
    @staticmethod
    def get_context_for_agent(phone_number: str) -> str:
        """
        Retorna contexto formatado para o agente AI.
        Busca do cache se disponível.
        """
        cache_key = f"agent_context:{phone_number}"
        
        # Tenta do cache
        cached_context = cache.get(cache_key)
        if cached_context:
            return cached_context
        
        # Busca usuário
        user = UnifiedUserService.get_by_phone_cached(phone_number)
        
        if user:
            context = user.get_context_for_agent()
        else:
            context = "👤 CLIENTE NOVO (não cadastrado)"
        
        # Salva no cache (30 segundos - curto para sempre ter dados frescos)
        cache.set(cache_key, context, 30)
        
        return context
    
    @staticmethod
    def update_from_order(phone_number: str, order_data: Dict[str, Any]):
        """
        Atualiza dados do usuário a partir de um pedido.
        """
        try:
            user, _ = UnifiedUser.resolve(
                phone=phone_number,
                name=order_data.get('customer_name', ''),
            )
            
            # Atualiza totais
            user.total_orders += 1
            user.total_spent += order_data.get('total', 0)
            user.last_order_at = order_data.get('created_at')
            
            # Limpa carrinho abandonado se existia
            if user.has_abandoned_cart:
                user.has_abandoned_cart = False
                user.abandoned_cart_value = 0
                user.abandoned_cart_items = []
                user.abandoned_cart_since = None
            
            user.save()
            
            # Invalida cache
            cache.delete(f"agent_context:{phone_number}")
            
            logger.info(f"[UnifiedUser] Updated from order: {user.id}")
            
        except Exception as e:
            logger.error(f"[UnifiedUser] Error updating from order: {e}")
    
    @staticmethod
    def update_abandoned_cart(phone_number: str, cart_data: Dict[str, Any]):
        """
        Marca carrinho como abandonado.
        """
        try:
            user, _ = UnifiedUser.resolve(phone=phone_number)
            
            user.has_abandoned_cart = True
            user.abandoned_cart_value = cart_data.get('total', 0)
            user.abandoned_cart_items = cart_data.get('items', [])
            user.abandoned_cart_since = cart_data.get('updated_at')
            user.save()
            
            # Invalida cache
            cache.delete(f"agent_context:{phone_number}")
            
            logger.info(f"[UnifiedUser] Marked abandoned cart: {user.id}")
            
        except Exception as e:
            logger.error(f"[UnifiedUser] Error marking abandoned cart: {e}")
