"""
Langchain Service for Agent management
"""
import json
import time
import uuid
from typing import List, Dict, Any, Optional

from django.conf import settings
from django.core.cache import cache
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain
from langchain_community.chat_message_histories import RedisChatMessageHistory

from apps.core.exceptions import APIError
from .models import Agent, AgentConversation, AgentMessage


class LangchainService:
    """Service for managing Langchain agents."""
    
    def __init__(self, agent: Agent):
        self.agent = agent
        self.llm = self._create_llm()
    
    def _create_llm(self) -> ChatOpenAI:
        """Create Langchain LLM instance based on agent configuration."""
        api_key = self.agent.api_key or getattr(settings, 'KIMI_API_KEY', '')
        base_url = self.agent.base_url or getattr(settings, 'KIMI_BASE_URL', 'https://api.kimi.com/coding/v1')
        
        if not api_key:
            raise APIError("API Key não configurada para o agente")
        
        return ChatOpenAI(
            model_name=self.agent.model_name,
            temperature=self.agent.temperature,
            max_tokens=self.agent.max_tokens,
            timeout=self.agent.timeout,
            api_key=api_key,
            base_url=base_url,
        )
    
    def _get_memory(self, session_id: str) -> Optional[ConversationBufferMemory]:
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
            return ConversationBufferMemory(
                chat_memory=history,
                return_messages=True
            )
        except Exception as e:
            print(f"Error creating memory: {e}")
            return None
    
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
            session_id = str(uuid.uuid4())
        
        # Get or create conversation
        conversation, created = AgentConversation.objects.get_or_create(
            session_id=session_id,
            defaults={
                'agent': self.agent,
                'phone_number': phone_number or '',
            }
        )
        
        # Build messages
        messages = []
        
        # Add system prompt
        system_prompt = self.agent.get_full_prompt()
        messages.append(SystemMessage(content=system_prompt))
        
        # Add memory/history if enabled
        memory = self._get_memory(session_id)
        if memory:
            history_messages = memory.load_memory_variables({}).get('history', [])
            messages.extend(history_messages)
        
        # Add user message
        messages.append(HumanMessage(content=message))
        
        # Call LLM
        try:
            response = self.llm.invoke(messages)
            response_text = response.content
            tokens_used = response.response_metadata.get('token_usage', {}).get('total_tokens')
        except Exception as e:
            raise APIError(f"Erro ao chamar LLM: {str(e)}")
        
        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Save to memory if enabled
        if memory:
            memory.save_context(
                {"input": message},
                {"output": response_text}
            )
        
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
            
            history = memory.load_memory_variables({}).get('history', [])
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
            raise APIError("Agente não encontrado")
        
        if agent.status != Agent.AgentStatus.ACTIVE:
            raise APIError("Agente não está ativo")
        
        service = LangchainService(agent)
        return service.process_message(message, session_id, phone_number)
