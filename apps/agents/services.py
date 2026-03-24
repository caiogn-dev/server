"""
Langchain Service for Agent management - Fixed for Kimi Coding API
"""
import json
import time
import uuid
import logging
import unicodedata
from typing import List, Dict, Any, Optional

from django.conf import settings
from django.core.cache import cache
from django.db import models
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_community.chat_message_histories import RedisChatMessageHistory

from apps.core.exceptions import BaseAPIException
from .models import Agent, AgentConversation, AgentMessage

logger = logging.getLogger(__name__)


def remove_accents(text):
    """Remove combining diacritics from text to avoid encoding issues with some LLM APIs."""
    if not text:
        return text
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )


class LangchainService:
    """Service for managing Langchain agents."""
    
    def __init__(self, agent: Agent):
        self.agent = agent
        self.llm = self._create_llm()
    
    def _create_llm(self):
        """Create Langchain LLM instance based on provider."""
        provider = self.agent.provider

        # ── Resolve API key: agent DB > provider-specific env var ─────────────
        _ENV_API_KEY = {
            Agent.AgentProvider.KIMI:     'KIMI_API_KEY',
            Agent.AgentProvider.OPENAI:   'OPENAI_API_KEY',
            Agent.AgentProvider.ANTHROPIC: 'ANTHROPIC_API_KEY',
            Agent.AgentProvider.NVIDIA:   'NVIDIA_API_KEY',
            Agent.AgentProvider.OLLAMA:   None,
        }
        env_key_name = _ENV_API_KEY.get(provider)
        api_key = self.agent.api_key or (
            getattr(settings, env_key_name, '') if env_key_name else ''
        ) or 'ollama'  # Ollama não requer key real

        # ── Resolve base URL: agent DB > provider-specific env var > hardcoded ─
        _ENV_BASE_URL = {
            Agent.AgentProvider.KIMI:     ('KIMI_BASE_URL',     'https://api.moonshot.cn/v1'),
            Agent.AgentProvider.OPENAI:   ('OPENAI_BASE_URL',   'https://api.openai.com/v1'),
            Agent.AgentProvider.ANTHROPIC: ('ANTHROPIC_BASE_URL', 'https://api.anthropic.com'),
            Agent.AgentProvider.NVIDIA:   ('NVIDIA_API_BASE_URL', 'https://integrate.api.nvidia.com/v1'),
            Agent.AgentProvider.OLLAMA:   ('OLLAMA_BASE_URL',   'http://localhost:11434/v1'),
        }
        env_url_name, default_url = _ENV_BASE_URL.get(provider, (None, ''))
        base_url = self.agent.base_url or (
            getattr(settings, env_url_name, '') if env_url_name else ''
        ) or default_url

        # Strip trailing endpoint paths that admins sometimes accidentally include.
        # ChatOpenAI appends /chat/completions automatically — if the stored base_url
        # already contains it we get a doubled path like /v1/chat/completions/chat/completions.
        for _suffix in ('/chat/completions', '/completions', '/v1/chat/completions'):
            if base_url.rstrip('/').endswith(_suffix):
                base_url = base_url.rstrip('/')[:-(len(_suffix))].rstrip('/')
                logger.warning(
                    '[LLM] base_url contained endpoint suffix — stripped to: %s', base_url
                )
                break

        if not api_key and provider != Agent.AgentProvider.OLLAMA:
            raise BaseAPIException(
                f"API Key não configurada para o agente (provider={provider}). "
                "Configure no Django Admin ou via variável de ambiente."
            )

        logger.debug(
            '[LLM] Creating %s | model=%s | base_url=%s | key_set=%s',
            provider, self.agent.model_name, base_url, bool(api_key),
        )

        # Use ChatOpenAI for Kimi (OpenAI-compatible API)
        if provider == Agent.AgentProvider.KIMI:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=self.agent.model_name,
                temperature=self.agent.temperature,
                max_tokens=self.agent.max_tokens,
                timeout=self.agent.timeout,
                api_key=api_key,
                base_url=base_url,
                default_headers={
                    'Content-Type': 'application/json; charset=utf-8',
                    'Accept': 'application/json',
                },
            )
        # Use ChatAnthropic for Anthropic API
        elif provider == Agent.AgentProvider.ANTHROPIC:
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
        elif provider == Agent.AgentProvider.OPENAI:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=self.agent.model_name,
                temperature=self.agent.temperature,
                max_tokens=self.agent.max_tokens,
                timeout=self.agent.timeout,
                api_key=api_key,
                base_url=base_url or None,
            )
        # Use ChatOpenAI for Ollama (OpenAI-compatible API)
        elif provider == Agent.AgentProvider.OLLAMA:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=self.agent.model_name,
                temperature=self.agent.temperature,
                max_tokens=self.agent.max_tokens,
                timeout=self.agent.timeout,
                api_key=api_key,
                base_url=base_url,
            )
        # Use ChatOpenAI for NVIDIA (OpenAI-compatible NIM API)
        elif provider == Agent.AgentProvider.NVIDIA:
            from langchain_openai import ChatOpenAI
            model_name = self.agent.model_name or getattr(
                settings, 'NVIDIA_MODEL_NAME', 'meta/llama-3.1-70b-instruct'
            )
            return ChatOpenAI(
                model=model_name,
                temperature=self.agent.temperature,
                max_tokens=self.agent.max_tokens,
                timeout=self.agent.timeout,
                api_key=api_key,
                base_url=base_url,
            )
        else:
            raise BaseAPIException(f"Provedor não suportado: {provider}")
    
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
                        if store:
                            logger.info(f"[AGENT CONTEXT] Found store via conversation: {store.name}")
                except Conversation.DoesNotExist:
                    logger.warning(f"[AGENT CONTEXT] Conversation {conversation_id} not found")
                except Exception as e:
                    logger.error(f"[AGENT CONTEXT] Error loading store from conversation: {e}")

            # If not found, try from agent's associated accounts
            if not store:
                try:
                    agent_accounts = self.agent.accounts.all()
                    first_account = agent_accounts.first()
                    if first_account:
                        if hasattr(first_account, 'store') and first_account.store:
                            store = first_account.store
                            logger.info(f"[AGENT CONTEXT] Found store via account.store: {store.name}")
                        elif hasattr(first_account, 'stores') and first_account.stores.exists():
                            store = first_account.stores.first()
                            logger.info(f"[AGENT CONTEXT] Found store via account.stores: {store.name}")
                except Exception as e:
                    logger.error(f"[AGENT CONTEXT] Error loading store from accounts: {e}")

            if not store:
                logger.warning("[AGENT CONTEXT] No store found — context will be incomplete")
            
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

        # 4. Load pending order / cart state for this customer (only recent ones)
        if phone_number:
            try:
                from apps.stores.models import StoreOrder
                from datetime import timedelta
                from django.utils import timezone as tz
                cutoff = tz.now() - timedelta(hours=4)
                pending = StoreOrder.objects.filter(
                    customer_phone=phone_number,
                    payment_status='pending',
                    created_at__gte=cutoff,
                ).order_by('-created_at').first()
                if pending:
                    items_preview = ", ".join(
                        f"{i.quantity}x {i.product_name}"
                        for i in pending.items.all()[:4]
                    )
                    context_parts.append(
                        f"\n🛒 PEDIDO PENDENTE DO CLIENTE:\n"
                        f"Pedido #{pending.order_number} — R$ {pending.total}\n"
                        f"Itens: {items_preview}\n"
                        f"Status pagamento: {pending.payment_status}"
                    )
            except Exception as e:
                logger.error(f"[AGENT CONTEXT] Error loading pending order: {e}")

        # Combine all context parts
        full_context = "\n\n".join(context_parts)

        # DEBUG: Log tamanho do contexto
        logger.info(f"[AGENT CONTEXT] Context built: {len(full_context)} chars, {len(context_parts)} parts")

        # Only Kimi has encoding issues with accented chars; all other providers handle UTF-8 fine.
        if self.agent.provider == Agent.AgentProvider.KIMI:
            return remove_accents(full_context)
        return full_context

    def _build_tools(self, phone_number: str = "", store=None):
        """Build Langchain tools bound to the current customer/store context."""

        @tool
        def buscar_produto(nome: str) -> str:
            """Busca um produto no cardápio pelo nome ou parte do nome."""
            if not store:
                return "Cardápio indisponível no momento."
            try:
                from apps.stores.models import StoreProduct
                products = StoreProduct.objects.filter(
                    store=store, is_active=True, name__icontains=nome
                ).select_related('category')[:6]
                if not products:
                    return f"Nenhum produto encontrado para '{nome}'."
                lines = []
                for p in products:
                    cat = p.category.name if p.category else "Geral"
                    desc = f" — {p.description[:70]}..." if p.description else ""
                    lines.append(f"[{cat}] {p.name} — R$ {p.price}{desc} (id: {p.id})")
                return "\n".join(lines)
            except Exception as exc:
                return f"Erro ao buscar produto: {exc}"

        @tool
        def listar_categorias() -> str:
            """Lista todas as categorias disponíveis no cardápio."""
            if not store:
                return "Cardápio indisponível no momento."
            try:
                from apps.stores.models import StoreCategory
                cats = StoreCategory.objects.filter(store=store, is_active=True).order_by('sort_order')
                if not cats:
                    return "Nenhuma categoria encontrada."
                return "\n".join(f"• {c.name}" for c in cats)
            except Exception as exc:
                return f"Erro ao listar categorias: {exc}"

        @tool
        def verificar_pedido_pendente() -> str:
            """Verifica se o cliente tem algum pedido pendente de pagamento."""
            if not phone_number:
                return "Telefone do cliente não disponível."
            try:
                from apps.stores.models import StoreOrder
                order = StoreOrder.objects.filter(
                    customer_phone=phone_number,
                    payment_status='pending',
                ).order_by('-created_at').first()
                if not order:
                    return "Nenhum pedido pendente encontrado."
                items = ", ".join(
                    f"{i.quantity}x {i.product_name}" for i in order.items.all()
                )
                return (
                    f"Pedido #{order.order_number}\n"
                    f"Itens: {items}\n"
                    f"Total: R$ {order.total}\n"
                    f"Status: {order.payment_status}"
                )
            except Exception as exc:
                return f"Erro ao verificar pedido: {exc}"

        @tool
        def consultar_historico_pedidos() -> str:
            """Retorna os últimos pedidos concluídos do cliente."""
            if not phone_number:
                return "Telefone do cliente não disponível."
            try:
                from apps.stores.models import StoreOrder
                orders = StoreOrder.objects.filter(
                    customer_phone=phone_number,
                    status__in=['completed', 'delivered'],
                ).order_by('-created_at')[:5]
                if not orders:
                    return "Nenhum pedido anterior encontrado."
                lines = []
                for o in orders:
                    items = ", ".join(f"{i.quantity}x {i.product_name}" for i in o.items.all()[:3])
                    lines.append(f"• {o.created_at.strftime('%d/%m/%Y')} — {items} — R$ {o.total}")
                return "\n".join(lines)
            except Exception as exc:
                return f"Erro ao consultar histórico: {exc}"

        @tool
        def informacoes_entrega() -> str:
            """Retorna a taxa de entrega e condições (frete grátis, prazo, etc)."""
            if not store:
                return "Informações de entrega não disponíveis."
            try:
                if not store.delivery_enabled:
                    return "Esta loja não faz entrega no momento. Apenas retirada no local."
                info = f"Taxa de entrega: R$ {store.default_delivery_fee}"
                if store.free_delivery_threshold:
                    info += f"\nEntrega GRÁTIS para pedidos acima de R$ {store.free_delivery_threshold}"
                if store.min_order_value:
                    info += f"\nPedido mínimo: R$ {store.min_order_value}"
                return info
            except Exception as exc:
                return f"Erro ao consultar entrega: {exc}"

        return [buscar_produto, listar_categorias, verificar_pedido_pendente,
                consultar_historico_pedidos, informacoes_entrega]

    def _get_store_for_context(self, conversation_id: Optional[str] = None):
        """Resolve the store for tool binding (same logic as _build_dynamic_context)."""
        store = None
        if conversation_id:
            try:
                from apps.conversations.models import Conversation
                conv = Conversation.objects.select_related('account').get(id=conversation_id)
                if hasattr(conv.account, 'store'):
                    store = conv.account.store
            except Exception:
                pass
        if not store:
            try:
                first_account = self.agent.accounts.first()
                if first_account:
                    store = getattr(first_account, 'store', None) or (
                        first_account.stores.first() if hasattr(first_account, 'stores') else None
                    )
            except Exception:
                pass
        return store

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
        
        # Build dynamic context - ALWAYS build to ensure store data is loaded
        dynamic_context = self._build_dynamic_context(phone_number or "", conversation_id)

        # Kimi API has encoding issues with accented chars; all other providers are fine.
        _kimi = (self.agent.provider == Agent.AgentProvider.KIMI)
        _sanitize = remove_accents if _kimi else (lambda x: x)

        # Prepare messages
        messages = []

        # Add system prompt with dynamic context — use ONLY the agent's own system_prompt
        # from the database. Never inject hardcoded behavioral rules here.
        system_prompt = self.agent.system_prompt or "Você é um assistente virtual. Responda em português."
        if dynamic_context:
            system_prompt = f"{system_prompt}\n\n{dynamic_context}"
        messages.append(SystemMessage(content=_sanitize(system_prompt)))

        # Add memory/context if available
        if memory:
            try:
                history = memory.messages
                for hist_msg in history[-self.agent.max_context_messages:]:
                    if _kimi and hasattr(hist_msg, 'content') and hist_msg.content:
                        hist_msg.content = remove_accents(hist_msg.content)
                    messages.append(hist_msg)
            except Exception as e:
                logger.warning(f"Error loading memory: {e}")

        # Add user message
        messages.append(HumanMessage(content=_sanitize(message)))
        
        # Build tools and bind to LLM (tool calling).
        # NVIDIA (Llama) and Kimi don't handle tool loops reliably — they tend to
        # call tools repeatedly even for simple greetings, ignoring the full context
        # already injected in the system prompt.  OpenAI and Anthropic handle this
        # correctly.  For other providers, fall back to context-only mode so the
        # dynamic system prompt drives the conversation.
        store = self._get_store_for_context(conversation_id)
        tools = self._build_tools(phone_number=phone_number or "", store=store)
        tool_map = {t.name: t for t in tools}
        _TOOL_CAPABLE_PROVIDERS = {Agent.AgentProvider.OPENAI, Agent.AgentProvider.ANTHROPIC}
        _use_tools = self.agent.provider in _TOOL_CAPABLE_PROVIDERS
        llm_with_tools = self.llm.bind_tools(tools) if _use_tools else self.llm

        def _clean(msg):
            """Normalize message content. For Kimi: strip accents. For others: decode bytes only."""
            if not hasattr(msg, 'content') or not msg.content:
                return msg
            content = msg.content
            if isinstance(content, bytes):
                content = content.decode('utf-8')
            if isinstance(content, str):
                if _kimi:
                    content = remove_accents(content)
                if isinstance(msg, SystemMessage):
                    return SystemMessage(content=content)
                if isinstance(msg, HumanMessage):
                    return HumanMessage(content=content)
                if isinstance(msg, AIMessage):
                    return AIMessage(content=content, tool_calls=getattr(msg, 'tool_calls', []))
            return msg

        try:
            current_messages = [_clean(m) for m in messages]

            # Agentic loop: invoke → handle tool calls → repeat (max 5 iterations)
            response_text = ""
            for _iteration in range(5):
                response = llm_with_tools.invoke(current_messages)
                tool_calls = getattr(response, 'tool_calls', [])

                if not tool_calls:
                    # Final text response
                    content = response.content
                    if isinstance(content, bytes):
                        content = content.decode('utf-8')
                    response_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                    break

                # Execute each tool and feed results back
                logger.info(f"[AGENT TOOLS] Iteration {_iteration+1}, tool calls: {[tc['name'] for tc in tool_calls]}")
                current_messages.append(response)  # AIMessage with tool_calls
                for tc in tool_calls:
                    fn = tool_map.get(tc['name'])
                    if fn:
                        try:
                            result = fn.invoke(tc['args'])
                        except Exception as exc:
                            result = f"Erro ao executar ferramenta {tc['name']}: {exc}"
                    else:
                        result = f"Ferramenta '{tc['name']}' não encontrada."
                    logger.info(f"[AGENT TOOLS] {tc['name']} → {str(result)[:120]}")
                    current_messages.append(ToolMessage(content=str(result), tool_call_id=tc['id']))
            else:
                # Loop exhausted without a text response — the model kept calling tools.
                # Force a final text response by invoking the plain LLM (no tools).
                logger.warning(
                    '[AGENT] Tool loop exhausted after 5 iterations — forcing final text call. '
                    'model=%s provider=%s',
                    self.agent.model_name, self.agent.provider,
                )
                try:
                    # Append a nudge so the model knows to respond in text now
                    current_messages.append(
                        HumanMessage(content="Com base nas informações acima, responda ao cliente agora.")
                    )
                    final_response = self.llm.invoke(current_messages)
                    content = final_response.content
                    if isinstance(content, bytes):
                        content = content.decode('utf-8')
                    response_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                except Exception as final_exc:
                    logger.error('[AGENT] Final text call also failed: %s', final_exc)
                    response_text = ""

            logger.info(f"[AGENT RESPONSE] {response_text[:120]!r}")

            # Save to memory if enabled
            if memory:
                try:
                    memory.add_user_message(message)
                    memory.add_ai_message(response_text)
                except Exception as e:
                    logger.warning(f"Error saving to memory: {e}")

            processing_time = time.time() - start_time
            return {
                'response': response_text,
                'session_id': session_id,
                'processing_time': processing_time,
                'model': self.agent.model_name,
                'tokens_used': getattr(response, 'usage_metadata', {}).get('total_tokens', 0),
            }

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            raise BaseAPIException(f"Erro ao processar mensagem: {str(e)}")

    def get_conversation_history(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Return serialized conversation history from Redis memory.
        """
        if not session_id:
            return []

        memory = self._get_memory(session_id)
        if not memory:
            return []

        try:
            messages = memory.messages[-max(1, int(limit)):]
            history: List[Dict[str, Any]] = []

            for msg in messages:
                role = 'assistant'
                if isinstance(msg, HumanMessage):
                    role = 'user'
                elif isinstance(msg, SystemMessage):
                    role = 'system'

                history.append({
                    'role': role,
                    'content': getattr(msg, 'content', '') or '',
                })

            return history
        except Exception as e:
            logger.error(f"Error retrieving conversation history for session {session_id}: {e}")
            return []

    def clear_memory(self, session_id: str) -> bool:
        """
        Clear Redis-backed memory for a specific session.
        """
        if not session_id:
            return False

        memory = self._get_memory(session_id)
        if not memory:
            return False

        try:
            memory.clear()
            return True
        except Exception as e:
            logger.error(f"Error clearing memory for session {session_id}: {e}")
            return False
    
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
        system_prompt = self.agent.system_prompt or "Você é um assistente virtual. Responda em português."
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

    @staticmethod
    def create_order_from_conversation(
        phone_number: str,
        items: List[Dict[str, Any]],
        customer_name: str = '',
        delivery_address: str = '',
        payment_method: str = 'dinheiro',
        notes: str = ''
    ) -> Dict[str, Any]:
        """
        Create an order from WhatsApp conversation.
        
        Args:
            phone_number: Customer phone number
            items: List of {'product_id': str, 'quantity': int, 'variant_id': str (optional)}
            customer_name: Customer name
            delivery_address: Delivery address
            payment_method: Payment method (dinheiro, pix, cartao)
            notes: Additional notes
            
        Returns:
            Dict with order details or error
        """
        from apps.stores.models import Store, StoreProduct, StoreCart, StoreOrder
        from apps.stores.services.cart_service import cart_service
        from apps.stores.services.checkout_service import CheckoutService
        from apps.users.models import UnifiedUser
        
        try:
            # Get store (Pastita)
            store = Store.objects.filter(slug='pastita').first()
            if not store:
                return {'success': False, 'error': 'Loja não encontrada'}
            
            # Get or create user
            user = UnifiedUser.objects.filter(phone=phone_number).first()
            
            # Create cart
            cart = StoreCart.objects.create(
                store=store,
                user=user,
                phone=phone_number,
                session_id=str(uuid.uuid4())
            )
            
            # Add items to cart
            for item_data in items:
                product_id = item_data.get('product_id')
                quantity = item_data.get('quantity', 1)
                variant_id = item_data.get('variant_id')
                
                try:
                    product = StoreProduct.objects.get(id=product_id, store=store)
                    cart_service.add_item(
                        cart=cart,
                        product_id=str(product.id),
                        variant_id=variant_id,
                        quantity=quantity
                    )
                except StoreProduct.DoesNotExist:
                    logger.warning(f"Product {product_id} not found")
                    continue
            
            if cart.items.count() == 0:
                cart.delete()
                return {'success': False, 'error': 'Nenhum produto válido no pedido'}
            
            # Prepare customer data
            customer_data = {
                'name': customer_name or 'Cliente WhatsApp',
                'phone': phone_number,
                'email': user.email if user and user.email else f"cliente@{store.slug}.com.br"
            }
            
            # Prepare delivery data
            delivery_data = None
            if delivery_address:
                delivery_data = {
                    'method': 'delivery',
                    'address': {'raw': delivery_address},
                    'notes': notes
                }
            else:
                delivery_data = {'method': 'pickup'}
            
            # Create order
            order = CheckoutService.create_order(
                cart=cart,
                customer_data=customer_data,
                delivery_data=delivery_data,
                notes=notes
            )
            
            # Clear cart after order creation
            cart.delete()
            
            return {
                'success': True,
                'order_id': str(order.id),
                'order_number': order.order_number,
                'total': float(order.total),
                'status': order.status,
                'payment_status': order.payment_status
            }
            
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return {'success': False, 'error': str(e)}
