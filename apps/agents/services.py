"""
Langchain Service for Agent management - Fixed for Kimi Coding API
"""
import json
import time
import uuid
import logging
from typing import List, Dict, Any, Optional

from django.conf import settings
from django.core.cache import cache
from django.db import models
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_community.chat_message_histories import RedisChatMessageHistory

from apps.core.exceptions import BaseAPIException
from .models import Agent, AgentConversation, AgentMessage

logger = logging.getLogger(__name__)


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
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=self.agent.model_name,
                temperature=self.agent.temperature,
                max_tokens=self.agent.max_tokens,
                timeout=self.agent.timeout,
                api_key=api_key,
                base_url=base_url if base_url else None,
            )
        # Use ChatOpenAI for Ollama (OpenAI-compatible API)
        elif self.agent.provider == Agent.AgentProvider.OLLAMA:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=self.agent.model_name,
                temperature=self.agent.temperature,
                max_tokens=self.agent.max_tokens,
                timeout=self.agent.timeout,
                api_key=api_key or "ollama",
                base_url=base_url,
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
            logger.error(f"Error creating memory: {e}")
            return None
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        return str(uuid.uuid4())
    
    def _build_dynamic_context(self, phone_number: str, conversation_id: Optional[str] = None) -> str:
        """
        Build dynamic context with menu, customer info, order history, etc.
        This provides the agent with real-time business data.
        """
        # DEBUG: Log início da construção do contexto
        logger.info(f"[AGENT CONTEXT] Building context for phone: {phone_number}, conversation: {conversation_id}")
        
        context_parts = []
        
        # Add agent's static context prompt
        if self.agent.context_prompt:
            context_parts.append(self.agent.context_prompt)
        
        # 1. Load customer info and order history
        try:
            from apps.conversations.models import Conversation
            from apps.stores.models import StoreOrder
            
            # Get customer name from conversation
            customer_name = ""
            if conversation_id:
                try:
                    conv = Conversation.objects.get(id=conversation_id)
                    if conv.contact_name:
                        customer_name = conv.contact_name
                        context_parts.append(f"Nome do cliente: {customer_name}")
                except Conversation.DoesNotExist:
                    pass
            
            # Get recent orders from this customer
            if phone_number:
                recent_orders = StoreOrder.objects.filter(
                    customer_phone=phone_number,
                    status__in=['completed', 'delivered', 'paid']
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
            logger.error(f"[AGENT CONTEXT] Error loading customer/order data: {e}")
        
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
                    logger.info(f"[AGENT CONTEXT] Agent accounts count: {agent_accounts.count()}")
                    if agent_accounts:
                        first_account = agent_accounts.first()
                        logger.info(f"[AGENT CONTEXT] First account: {first_account}")
                        if hasattr(first_account, 'store') and first_account.store:
                            store = first_account.store
                            logger.info(f"[AGENT CONTEXT] Found store via account.store: {store.name}")
                        # Try stores many-to-many relation
                        elif hasattr(first_account, 'stores') and first_account.stores.exists():
                            store = first_account.stores.first()
                            logger.info(f"[AGENT CONTEXT] Found store via account.stores: {store.name}")
                except Exception as e:
                    logger.error(f"[AGENT CONTEXT] Error loading store from accounts: {e}")
            
            # FALLBACK: If no store found, use 'pastita' store
            if not store:
                try:
                    from apps.stores.models import Store
                    store = Store.objects.filter(slug='pastita').first()
                    if store:
                        logger.info(f"[AGENT CONTEXT] Using fallback store: {store.name}")
                    else:
                        logger.warning("[AGENT CONTEXT] Fallback store 'pastita' not found!")
                except Exception as e:
                    logger.error(f"[AGENT CONTEXT] Error loading fallback store: {e}")
            
            # Load products from store
            if store:
                try:
                    from apps.stores.models import StoreProduct
                    products = StoreProduct.objects.filter(
                        store=store,
                        is_active=True
                    ).select_related('category')[:20]
                    
                    if products:
                        menu_text = f"\n📋 CARDÁPIO - {store.name}:\n"
                        current_category = None
                        
                        for product in products:
                            if product.category and product.category.name != current_category:
                                current_category = product.category.name
                                menu_text += f"\n【{current_category}】\n"
                            
                            price = product.price
                            menu_text += f"• {product.name} - R$ {price}"
                            if product.description:
                                desc = product.description[:60] + "..." if len(product.description) > 60 else product.description
                                menu_text += f" ({desc})"
                            menu_text += "\n"
                        
                        context_parts.append(menu_text)
                        
                        # Add delivery info
                        if store.delivery_enabled:
                            delivery_text = f"\n🚚 ENTREGA:\n"
                            delivery_text += f"• Taxa de entrega: R$ {store.default_delivery_fee}\n"
                            if store.free_delivery_threshold:
                                delivery_text += f"• Grátis acima de: R$ {store.free_delivery_threshold}\n"
                            context_parts.append(delivery_text)
                            
                except Exception as e:
                    logger.error(f"[AGENT CONTEXT] Error loading store products: {e}")
            
        except Exception as e:
            logger.error(f"[AGENT CONTEXT] Error loading store menu: {e}")
        
        # 3. Load business hours
        try:
            if store and store.operating_hours:
                hours_text = "\n⏰ HORÁRIO DE FUNCIONAMENTO:\n"
                for day, hours in store.operating_hours.items():
                    hours_text += f"• {day}: {hours.get('open', '--:--')} - {hours.get('close', '--:--')}\n"
                context_parts.append(hours_text)
        except Exception as e:
            logger.error(f"[AGENT CONTEXT] Error loading business hours: {e}")
        
        # Combine all context parts
        full_context = "\n\n".join(context_parts)
        
        # DEBUG: Log tamanho do contexto
        logger.info(f"[AGENT CONTEXT] Context built: {len(full_context)} chars, {len(context_parts)} parts")
        
        return full_context
    
    def process_message(
        self,
        message: str,
        session_id: Optional[str] = None,
        phone_number: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a message through the agent.
        
        Args:
            message: The user's message
            session_id: Optional session ID for memory
            phone_number: Optional phone number for context
            conversation_id: Optional conversation ID for context
            
        Returns:
            Dict with response text and metadata
        """
        start_time = time.time()
        
        # Generate or use session ID
        if not session_id:
            session_id = self._generate_session_id()
        
        # Get memory
        memory = self._get_memory(session_id)
        
        # Build dynamic context
        dynamic_context = ""
        if phone_number or conversation_id:
            dynamic_context = self._build_dynamic_context(phone_number, conversation_id)
        
        # Prepare messages
        messages = []
        
        # Add system prompt with dynamic context
        system_prompt = self.agent.system_prompt or "Você é um assistente virtual útil."
        if dynamic_context:
            system_prompt = f"{system_prompt}\n\n{dynamic_context}"
        messages.append(SystemMessage(content=system_prompt))
        
        # Add memory/context if available
        if memory:
            try:
                history = memory.messages
                messages.extend(history[-self.agent.max_context_messages:])
            except Exception as e:
                logger.warning(f"Error loading memory: {e}")
        
        # Add user message
        messages.append(HumanMessage(content=message))
        
        try:
            # Call LLM
            response = self.llm.invoke(messages)
            
            # Extract response text
            response_text = response.content
            
            # Save to memory if enabled
            if memory:
                try:
                    memory.add_user_message(message)
                    memory.add_ai_message(response_text)
                except Exception as e:
                    logger.warning(f"Error saving to memory: {e}")
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            return {
                'response': response_text,
                'session_id': session_id,
                'processing_time': processing_time,
                'model': self.agent.model_name,
                'tokens_used': getattr(response, 'usage', {}).get('total_tokens', 0),
            }
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            raise BaseAPIException(f"Erro ao processar mensagem: {str(e)}")
    
    def process_message_stream(
        self,
        message: str,
        session_id: Optional[str] = None,
        phone_number: Optional[str] = None,
        conversation_id: Optional[str] = None
    ):
        """
        Process a message with streaming response.
        
        Yields chunks of the response as they arrive.
        """
        start_time = time.time()
        
        # Generate or use session ID
        if not session_id:
            session_id = self._generate_session_id()
        
        # Get memory
        memory = self._get_memory(session_id)
        
        # Build dynamic context
        dynamic_context = ""
        if phone_number or conversation_id:
            dynamic_context = self._build_dynamic_context(phone_number, conversation_id)
        
        # Prepare messages
        messages = []
        
        # Add system prompt with dynamic context
        system_prompt = self.agent.system_prompt or "Você é um assistente virtual útil."
        if dynamic_context:
            system_prompt = f"{system_prompt}\n\n{dynamic_context}"
        messages.append(SystemMessage(content=system_prompt))
        
        # Add memory/context if available
        if memory:
            try:
                history = memory.messages
                messages.extend(history[-self.agent.max_context_messages:])
            except Exception as e:
                logger.warning(f"Error loading memory: {e}")
        
        # Add user message
        messages.append(HumanMessage(content=message))
        
        try:
            # Call LLM with streaming
            full_response = ""
            for chunk in self.llm.stream(messages):
                if chunk.content:
                    full_response += chunk.content
                    yield {
                        'type': 'chunk',
                        'content': chunk.content,
                        'session_id': session_id,
                    }
            
            # Save to memory if enabled
            if memory:
                try:
                    memory.add_user_message(message)
                    memory.add_ai_message(full_response)
                except Exception as e:
                    logger.warning(f"Error saving to memory: {e}")
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Yield final message
            yield {
                'type': 'final',
                'response': full_response,
                'session_id': session_id,
                'processing_time': processing_time,
                'model': self.agent.model_name,
            }
            
        except Exception as e:
            logger.error(f"Error processing message stream: {e}")
            yield {
                'type': 'error',
                'error': str(e),
                'session_id': session_id,
            }


class AgentService:
    """Service for agent management operations."""
    
    @staticmethod
    def get_agent_response(
        agent_id: str,
        message: str,
        session_id: Optional[str] = None,
        phone_number: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get response from an agent.
        
        This is the main entry point for agent interactions.
        """
        try:
            agent = Agent.objects.get(id=agent_id, is_active=True)
        except Agent.DoesNotExist:
            raise BaseAPIException("Agente não encontrado ou inativo")
        
        service = LangchainService(agent)
        return service.process_message(
            message=message,
            session_id=session_id,
            phone_number=phone_number,
            conversation_id=conversation_id
        )
    
    @staticmethod
    def create_conversation(
        agent_id: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> AgentConversation:
        """Create a new conversation with an agent."""
        agent = Agent.objects.get(id=agent_id)
        
        conversation = AgentConversation.objects.create(
            agent=agent,
            user_id=user_id,
            session_id=str(uuid.uuid4()),
            metadata=metadata or {}
        )
        
        return conversation
    
    @staticmethod
    def add_message(
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> AgentMessage:
        """Add a message to a conversation."""
        conversation = AgentConversation.objects.get(id=conversation_id)
        
        message = AgentMessage.objects.create(
            conversation=conversation,
            role=role,
            content=content,
            metadata=metadata or {}
        )
        
        # Update conversation timestamp
        conversation.save()
        
        return message
