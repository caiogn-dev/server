"""
Langchain Service for Agent management - Fixed for Kimi Coding API
"""
import json
import time
import uuid
from typing import List, Dict, Any, Optional

from django.conf import settings
from django.core.cache import cache
from django.db import models
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_community.chat_message_histories import RedisChatMessageHistory

from apps.core.exceptions import BaseAPIException
from .models import Agent, AgentConversation, AgentMessage


class LangchainService:
    """Service for managing Langchain agents."""
    
    def __init__(self, agent: Agent):
        self.agent = agent
        self.llm = self._create_llm()
    
    def _create_llm(self):
        """Create Langchain LLM instance based on provider."""
        api_key = self.agent.api_key or getattr(settings, 'KIMI_API_KEY', '')
        base_url = self.agent.base_url or getattr(settings, 'KIMI_BASE_URL', 'https://api.kimi.com/coding/')
        
        if not api_key:
            raise BaseAPIException("API Key não configurada para o agente")
        
        # Use ChatAnthropic for Kimi (Anthropic-compatible API)
        if self.agent.provider == Agent.AgentProvider.KIMI:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=self.agent.model_name,  # "kimi-for-coding" or "kimi-k2"
                temperature=self.agent.temperature,
                max_tokens=self.agent.max_tokens,
                timeout=self.agent.timeout,
                api_key=api_key,
                anthropic_api_url=base_url,
            )
        # Use ChatAnthropic for Anthropic API
        elif self.agent.provider == Agent.AgentProvider.ANTHROPIC:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=self.agent.model_name,
                temperature=self.agent.temperature,
                max_tokens=self.agent.max_tokens,
                timeout=self.agent.timeout,
                api_key=api_key,
                anthropic_api_url=base_url,
            )
        # Use ChatOpenAI for OpenAI
        elif self.agent.provider == Agent.AgentProvider.OPENAI:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=self.agent.model_name,
                temperature=self.agent.temperature,
                max_tokens=self.agent.max_tokens,
                timeout=self.agent.timeout,
                api_key=api_key,
                base_url=base_url if base_url else None,
            )
        else:
            raise BaseAPIException(f"Provedor não suportado: {self.agent.provider}")
    
    def _get_memory(self, session_id: str) -> Optional[RedisChatMessageHistory]:
        """Get conversation memory from Redis."""
        if not self.agent.use_memory:
            return None
        
        try:
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
            history = RedisChatMessageHistory(
                session_id=f"agent_{self.agent.id}_{session_id}",
                url=redis_url,
                ttl=self.agent.memory_ttl
            )
            return history
        except Exception as e:
            print(f"Error creating memory: {e}")
            return None
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        return str(uuid.uuid4())
    
    def _build_dynamic_context(self, phone_number: str, conversation_id: Optional[str] = None) -> str:
        """
        Build dynamic context with menu, customer info, order history, etc.
        This provides the agent with real-time business data.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # DEBUG: Log início da construção do contexto
        logger.info(f"[AGENT CONTEXT DEBUG] Building context for phone: {phone_number}, conversation: {conversation_id}")
        
        context_parts = []
        
        # Add agent's static context prompt
        if self.agent.context_prompt:
            context_parts.append(self.agent.context_prompt)
        
        # NOVO: Carregar contexto do UnifiedUser
        try:
            from apps.users.services import UnifiedUserService
            user_context = UnifiedUserService.get_context_for_agent(phone_number)
            if user_context:
                context_parts.append("═══ DADOS DO CLIENTE ═══")
                context_parts.append(user_context)
                context_parts.append("═══════════════════════════")
                logger.info(f"[AGENT CONTEXT DEBUG] UnifiedUser context loaded: {len(user_context)} chars")
            else:
                logger.warning(f"[AGENT CONTEXT DEBUG] No UnifiedUser found for phone: {phone_number}")
        except Exception as e:
            logger.error(f"[AGENT CONTEXT DEBUG] Error loading UnifiedUser context: {e}")
        
        # 1. Load customer info and order history (fallback se UnifiedUser não existir)
        try:
            from apps.conversations.models import Conversation
            from apps.orders.models import Order
            
            # Get customer name from conversation
            customer_name = ""
            if conversation_id:
                try:
                    conv = Conversation.objects.get(id=conversation_id)
                    if conv.contact_name:
                        customer_name = conv.contact_name
                        if not any("CLIENTE:" in part for part in context_parts):
                            context_parts.append(f"Nome do cliente: {customer_name}")
                except Conversation.DoesNotExist:
                    pass
            
            # Get recent orders from this customer (se não veio do UnifiedUser)
            if phone_number and not any("HISTÓRICO DE PEDIDOS" in part for part in context_parts):
                recent_orders = Order.objects.filter(
                    customer_phone=phone_number,
                    status__in=['completed', 'delivered']
                ).select_related('store').prefetch_related('items')[:3]
                
                if recent_orders:
                    orders_text = "📦 HISTÓRICO DE PEDIDOS RECENTES:\n"
                    for order in recent_orders:
                        items = order.items.all()[:3]
                        items_text = ", ".join([f"{item.quantity}x {item.product_name}" for item in items])
                        if len(order.items.all()) > 3:
                            items_text += " e mais..."
                        orders_text += f"- {order.created_at.strftime('%d/%m/%Y')}: {items_text} - Total: R$ {order.total}\n"
                    context_parts.append(orders_text)
                    
                    # Add favorite products based on order history
                    from collections import Counter
                    all_items = []
                    for order in recent_orders:
                        for item in order.items.all():
                            all_items.append(item.product_name)
                    
                    if all_items:
                        favorites = Counter(all_items).most_common(3)
                        fav_text = "❤️ PRODUTOS FAVORITOS DO CLIENTE: " + ", ".join([f[0] for f in favorites])
                        context_parts.append(fav_text)
                        
        except Exception as e:
            logger.error(f"Error loading customer/order data: {e}")
        
        # 2. Load store menu/catalog
        try:
            # Try to get store from conversation or agent accounts
            store = None
            
            # First try from conversation
            if conversation_id:
                try:
                    from apps.conversations.models import Conversation
                    conv = Conversation.objects.select_related('account').get(id=conversation_id)
                    if hasattr(conv.account, 'store'):
                        store = conv.account.store
                except:
                    pass
            
            # If not found, try from agent's associated accounts
            if not store:
                try:
                    from apps.stores.models import Store
                    # Get first store from agent's accounts
                    agent_accounts = self.agent.accounts.all()
                    if agent_accounts:
                        first_account = agent_accounts.first()
                        if hasattr(first_account, 'store'):
                            store = first_account.store
                except:
                    pass
            
            # Load products from store
            if store:
                try:
                    from apps.catalog.models import Product
                    products = Product.objects.filter(
                        store=store,
                        is_active=True,
                        is_available=True
                    )[:15]
                    
                    if products:
                        menu_text = f"🍽️ CARDÁPIO ATUAL - {store.name}:\n"
                        for p in products:
                            price_display = f"R$ {p.price:.2f}"
                            if p.compare_at_price and p.compare_at_price > p.price:
                                price_display += f" (de R$ {p.compare_at_price:.2f})"
                            menu_text += f"- {p.name}: {price_display}\n"
                            if p.description:
                                menu_text += f"  {p.description[:80]}...\n"
                        context_parts.append(menu_text)
                        
                        # Add promotional info if exists
                        promos = products.filter(compare_at_price__gt=models.F('price'))[:5]
                        if promos:
                            promo_text = "🔥 PROMOÇÕES ATIVAS: " + ", ".join([p.name for p in promos])
                            context_parts.append(promo_text)
                            
                except Exception as e:
                    logger.error(f"Error loading products: {e}")
                    
        except Exception as e:
            logger.error(f"Error loading store/menu data: {e}")
        
        # 3. Add current time context
        from datetime import datetime
        now = datetime.now()
        time_context = f"📅 Data e hora atual: {now.strftime('%d/%m/%Y %H:%M')}"
        context_parts.append(time_context)
        
        # Join all context parts
        return "\n\n".join(context_parts)

    
    def process_message(
        self,
        message: str,
        session_id: Optional[str] = None,
        phone_number: Optional[str] = None,
        save_to_db: bool = True
    ) -> Dict[str, Any]:
        """
        Process a message through the agent.
        
        Returns:
            Dict with 'response', 'session_id', 'tokens_used', etc.
        """
        start_time = time.time()
        
        # Generate or use existing session_id
        if not session_id:
            session_id = self._generate_session_id()
        
        # Get or create conversation
        try:
            conversation, created = AgentConversation.objects.get_or_create(
                session_id=session_id,
                defaults={
                    'agent': self.agent,
                    'phone_number': phone_number or '',
                }
            )
        except AgentConversation.DoesNotExist:
            # Se não existe, cria uma nova
            conversation = AgentConversation.objects.create(
                session_id=session_id,
                agent=self.agent,
                phone_number=phone_number or '',
            )
            created = True
        
        # Build messages
        messages = []
        
        # Add system prompt with dynamic context
        system_prompt = self.agent.get_full_prompt()
        dynamic_context = self._build_dynamic_context(phone_number, session_id)
        
        # Combine system prompt with dynamic context
        full_system_prompt = f"{system_prompt}\n\n{dynamic_context}"
        messages.append(SystemMessage(content=full_system_prompt))
        
        # Add memory/history if enabled
        memory = self._get_memory(session_id)
        if memory:
            history_messages = memory.messages
            if history_messages:
                print(f"[AGENT DEBUG] Loaded {len(history_messages)} messages from memory for session {session_id}")
                messages.extend(history_messages)
            else:
                print(f"[AGENT DEBUG] No history found in memory for session {session_id}")
        else:
            print(f"[AGENT DEBUG] Memory not available for session {session_id}")
        
        # Add user message
        messages.append(HumanMessage(content=message))
        
        print(f"[AGENT DEBUG] Sending {len(messages)} messages to LLM (session: {session_id})")
        
        # Call LLM
        try:
            response = self.llm.invoke(messages)
            response_text = response.content
            # Try to get token usage from response metadata
            try:
                tokens_used = response.response_metadata.get('usage', {}).get('total_tokens')
            except (AttributeError, KeyError):
                tokens_used = None
        except Exception as e:
            raise BaseAPIException(f"Erro ao chamar LLM: {str(e)}")
        
        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Save to memory if enabled
        if memory:
            memory.add_user_message(message)
            memory.add_ai_message(response_text)
        
        # Save to database
        if save_to_db:
            AgentMessage.objects.create(
                conversation=conversation,
                role=AgentMessage.MessageRole.USER,
                content=message
            )
            AgentMessage.objects.create(
                conversation=conversation,
                role=AgentMessage.MessageRole.ASSISTANT,
                content=response_text,
                tokens_used=tokens_used,
                response_time_ms=response_time_ms
            )
            
            # Update conversation metrics
            conversation.message_count += 2
            conversation.save()
        
        return {
            'response': response_text,
            'session_id': session_id,
            'tokens_used': tokens_used,
            'response_time_ms': response_time_ms,
        }
    
    def clear_memory(self, session_id: str) -> bool:
        """Clear conversation memory for a session."""
        if not self.agent.use_memory:
            return False
        
        try:
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
            history = RedisChatMessageHistory(
                session_id=f"agent_{self.agent.id}_{session_id}",
                url=redis_url
            )
            history.clear()
            return True
        except Exception as e:
            print(f"Error clearing memory: {e}")
            return False
    
    def get_conversation_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get conversation history from memory."""
        if not self.agent.use_memory:
            return []
        
        try:
            memory = self._get_memory(session_id)
            if not memory:
                return []
            
            history = memory.messages
            return [
                {
                    'role': 'user' if isinstance(msg, HumanMessage) else 'assistant',
                    'content': msg.content
                }
                for msg in history
            ]
        except Exception as e:
            print(f"Error getting history: {e}")
            return []


class AgentService:
    """Service for managing agents and their operations."""
    
    def __init__(self, agent: Optional[Agent] = None):
        """Initialize with an optional agent."""
        self.agent = agent
        self._langchain_service = None
        
        if agent:
            self._langchain_service = LangchainService(agent)
    
    def process_message(
        self,
        message: str,
        session_id: Optional[str] = None,
        phone_number: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        save_to_db: bool = True
    ) -> str:
        """
        Process a message with the configured agent.
        
        Returns the response text or empty string if no response.
        """
        if not self.agent or not self._langchain_service:
            return ''
        
        try:
            result = self._langchain_service.process_message(
                message=message,
                session_id=session_id,
                phone_number=phone_number,
                save_to_db=save_to_db
            )
            return result.get('response', '')
        except Exception as e:
            print(f"Error processing message: {e}")
            return ''
    
    @staticmethod
    def get_active_agents(account_id: Optional[str] = None):
        """Get all active agents, optionally filtered by account."""
        queryset = Agent.objects.filter(
            status=Agent.AgentStatus.ACTIVE,
            is_active=True
        )
        
        if account_id:
            queryset = queryset.filter(accounts__id=account_id)
        
        return queryset
    
    @staticmethod
    def process_with_agent(
        agent_id: str,
        message: str,
        session_id: Optional[str] = None,
        phone_number: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process a message with a specific agent."""
        try:
            agent = Agent.objects.get(id=agent_id, is_active=True)
        except Agent.DoesNotExist:
            raise BaseAPIException("Agente não encontrado")
        
        if agent.status != Agent.AgentStatus.ACTIVE:
            raise BaseAPIException("Agente não está ativo")
        
        service = LangchainService(agent)
        return service.process_message(message, session_id, phone_number)
