"""
Langchain Service for Agent management - Fixed for Kimi Coding API
"""
import json
import time
import uuid
from typing import List, Dict, Any, Optional

from django.conf import settings
from django.core.cache import cache
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
        
        # Add system prompt
        system_prompt = self.agent.get_full_prompt()
        messages.append(SystemMessage(content=system_prompt))
        
        # Add memory/history if enabled
        memory = self._get_memory(session_id)
        if memory:
            history_messages = memory.messages
            messages.extend(history_messages)
        
        # Add user message
        messages.append(HumanMessage(content=message))
        
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
