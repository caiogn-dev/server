"""
Langchain Service for Agent management - Fixed for Kimi Coding API
"""
import json
import time
import uuid
import logging
import re
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

    def _normalize_runtime_text(self, value: str) -> str:
        if not value:
            return ''
        normalized = unicodedata.normalize('NFD', value.lower())
        normalized = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')
        return re.sub(r'[^a-z0-9\s]', ' ', normalized).strip()

    def _message_mentions_product(self, message: str, store=None) -> bool:
        if not store or not message:
            return False
        normalized_message = self._normalize_runtime_text(message)
        if len(normalized_message) < 3:
            return False
        try:
            from apps.stores.models import StoreProduct

            products = StoreProduct.objects.filter(
                store=store,
                is_active=True,
            ).exclude(tags__contains=['ingrediente']).only('name')

            for product in products:
                normalized_name = self._normalize_runtime_text(product.name)
                if not normalized_name:
                    continue
                if normalized_name in normalized_message or normalized_message in normalized_name:
                    return True
        except Exception as exc:
            logger.warning('[AGENT] Product match lookup failed: %s', exc)
        return False

    def _match_fixed_delivery_zone_from_text(self, message: str, store=None) -> Optional[Dict[str, Any]]:
        """Match store metadata fixed delivery zones from customer text."""
        if not store or not message:
            return None

        metadata = getattr(store, 'metadata', None) or {}
        zones = metadata.get('fixed_price_zones') or []
        normalized_message = self._normalize_runtime_text(message)
        for zone in zones:
            keywords = list(zone.get('keywords') or [])
            if zone.get('name'):
                keywords.append(zone['name'])
            for keyword in keywords:
                normalized_keyword = self._normalize_runtime_text(keyword)
                if normalized_keyword and normalized_keyword in normalized_message:
                    return zone
        return None

    def _looks_like_delivery_address(self, message: str) -> bool:
        """Detect address-like text before the LLM has a chance to invent a fee."""
        normalized = self._normalize_runtime_text(message)
        if not normalized:
            return False

        address_terms = (
            'quadra', ' alameda ', ' rua ', ' avenida ', ' av ', ' lote ',
            ' q ', ' qi ', ' sul', ' norte', ' cep ', ' palmas',
        )
        has_number = bool(re.search(r'\b\d{1,5}\b', normalized))
        has_address_term = any(term in f' {normalized} ' for term in address_terms)
        has_palmas_zip = bool(re.search(r'\b77\d{3}\s?\d{3}\b', normalized))
        has_plano_diretor_quadra = bool(re.search(r'\b\d{3}\s*(sul|norte)\b', normalized))
        return (has_number and has_address_term) or has_palmas_zip or has_plano_diretor_quadra

    def _format_brl(self, value: float) -> str:
        return f"R$ {float(value):.2f}".replace('.', ',')

    def _get_delivery_fee_runtime_reply(self, message: str, store=None) -> Optional[str]:
        """Resolve delivery fee questions deterministically, never by LLM prose."""
        if not store:
            return None

        normalized = self._normalize_runtime_text(message)
        if not normalized:
            return None

        mentions_delivery = any(
            term in normalized
            for term in ('taxa', 'frete', 'entrega', 'delivery', 'rota')
        )
        fixed_zone = self._match_fixed_delivery_zone_from_text(message, store=store)
        if fixed_zone and mentions_delivery:
            fee = float(fixed_zone.get('fee', getattr(store, 'default_delivery_fee', 0) or 0))
            zone_name = fixed_zone.get('name') or 'região informada'
            return f"Para {zone_name}, a taxa de entrega é fixa: {self._format_brl(fee)}."

        if self._looks_like_delivery_address(message):
            try:
                from apps.stores.services.geo import geo_service

                geo = geo_service.geocode(message, restrict_to_city=True)
                if not geo or not geo.get('lat') or not geo.get('lng'):
                    return (
                        "Não consegui localizar esse endereço em Palmas.\n"
                        "Me envie a localização pelo alfinete do WhatsApp para calcular certinho."
                    )

                fee_info = geo_service.calculate_delivery_fee(
                    store,
                    customer_lat=geo['lat'],
                    customer_lng=geo['lng'],
                    customer_address_text=message,
                )
                if not fee_info.get('is_within_area', True) or fee_info.get('fee') is None:
                    return (
                        fee_info.get('message')
                        or "Esse endereço fica fora da nossa área de entrega dinâmica."
                    )

                fee = float(fee_info['fee'])
                distance_km = fee_info.get('distance_km')
                formatted_address = geo.get('formatted_address') or message
                dist_text = f" ({float(distance_km):.1f} km)" if distance_km else ""
                return f"Para {formatted_address}, a taxa de entrega{dist_text} é {self._format_brl(fee)}."
            except Exception as exc:
                logger.error('[AGENT] Deterministic delivery fee failed: %s', exc, exc_info=True)
                return (
                    "Não consegui calcular a taxa agora.\n"
                    "Me envie a localização pelo alfinete do WhatsApp para calcular certinho."
                )

        if mentions_delivery:
            return (
                "A taxa varia conforme a localização.\n"
                "Me envie o endereço completo ou a localização pelo alfinete do WhatsApp para calcular certinho."
            )

        return None

    def _get_direct_runtime_reply(self, message: str, store=None) -> Optional[str]:
        """Short-circuit obvious ambiguous ordering before any tool loop starts."""
        normalized = self._normalize_runtime_text(message)
        if not normalized:
            return None

        delivery_reply = self._get_delivery_fee_runtime_reply(message, store=store)
        if delivery_reply:
            return delivery_reply

        generic_item_terms = (
            ' salada ', ' saladas ', ' item ', ' itens ', ' produto ', ' produtos ',
            ' pedido ', ' pedidos ', ' combo ', ' combos ',
        )
        has_quantity = bool(re.search(r'\b\d+\b', normalized))
        mentions_generic_items = any(term in f' {normalized} ' for term in generic_item_terms)
        mentions_payment = any(term in normalized for term in ('pix', 'pagar', 'pagamento'))

        if has_quantity and mentions_generic_items and not self._message_mentions_product(message, store=store):
            if mentions_payment:
                return (
                    "Claro. Primeiro me diga quais itens você quer pedir.\n"
                    "Depois eu sigo com a forma de pagamento, inclusive PIX."
                )
            return (
                "Claro. Quais itens você quer pedir?\n"
                "Se quiser, eu posso te mostrar algumas opções do cardápio."
            )

        return None

    def _resolve_allowed_tools(self, message: str) -> Optional[set]:
        """Restrict tool access for narrow consultative intents to avoid loops."""
        normalized = self._normalize_runtime_text(message)
        if not normalized:
            return None

        if any(term in normalized for term in ('taxa de entrega', 'frete', 'entrega', 'delivery')):
            return {'informacoes_entrega'}
        if any(term in normalized for term in ('pix', 'pagamento', 'codigo pix', 'copiar pix', 'qr code')):
            return {'consultar_pagamento'}
        if any(term in normalized for term in ('cardapio', 'menu', 'catalogo', 'produtos', 'opcoes')):
            return {'listar_categorias'}
        if any(term in normalized for term in ('recomenda', 'indica', 'sugere')):
            return {'buscar_produto'}
        return None

    def _get_pending_pix_payment(self, phone_number: str, store=None) -> Dict[str, Any]:
        """Return the latest pending PIX data for this customer, without LLM prose."""
        if not phone_number:
            return {'found': False, 'message': 'Telefone do cliente não disponível.'}

        try:
            from django.utils import timezone
            from apps.stores.models import StoreOrder
            from apps.automation.models import CustomerSession

            session_qs = CustomerSession.objects.filter(phone_number=phone_number)
            if store:
                from apps.automation.models import CompanyProfile as _CP
                profile_ids = _CP.objects.filter(store=store).values_list('id', flat=True)
                session_qs = session_qs.filter(company_id__in=profile_ids)

            session = session_qs.order_by('-updated_at').first()
            if session and session.pix_code:
                if session.pix_expires_at and session.pix_expires_at <= timezone.now():
                    return {
                        'found': False,
                        'expired': True,
                        'message': 'O PIX gerado expirou. Um novo pagamento precisa ser gerado.',
                    }
                return {
                    'found': True,
                    'pix_code': session.pix_code,
                    'expires_at': session.pix_expires_at,
                    'source': 'customer_session',
                }

            order = StoreOrder.objects.filter(
                customer_phone__in=[
                    phone_number,
                    phone_number.lstrip('+'),
                    f"+{phone_number.lstrip('+')}",
                ],
                payment_status='pending',
            ).exclude(pix_code='').order_by('-created_at').first()
            if order and order.pix_code:
                return {
                    'found': True,
                    'pix_code': order.pix_code,
                    'order_number': order.order_number,
                    'total': order.total,
                    'source': 'store_order',
                }

            return {
                'found': False,
                'message': 'Nenhum PIX pendente encontrado. O pagamento ainda não foi gerado.',
            }
        except Exception as exc:
            return {'found': False, 'message': f'Erro ao consultar pagamento: {exc}'}
    
    def _build_dynamic_context(self, phone_number: str, conversation_id: Optional[str] = None) -> str:
        """
        Build dynamic context with store data for the current conversation.
        This provides the agent with real-time business data.
        """
        # DEBUG: Log início da construção do contexto
        logger.info(f"[AGENT CONTEXT] Building context for phone: {phone_number}, conversation: {conversation_id}")
        
        context_parts = []
        
        # Add agent's static context prompt
        if self.agent.context_prompt:
            context_parts.append(self.agent.context_prompt)
        
        # 1. Load customer name only.
        # Do not inject order history or favorites into the system prompt:
        # that was causing the model to revive old purchases as if they were
        # part of the current order flow.
        try:
            from apps.conversations.models import Conversation
            
            # Get customer name from conversation
            if conversation_id:
                try:
                    conv = Conversation.objects.get(id=conversation_id)
                    if conv.contact_name:
                        context_parts.append(f"Nome do cliente: {conv.contact_name}")
                except Conversation.DoesNotExist:
                    pass
                        
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
            
            # Add operational guidance scoped to the current store context.
            if store:
                context_parts.append(
                    "\n🎯 CONDUTA DE ATENDIMENTO:\n"
                    "• Responda de forma curta, humana e objetiva.\n"
                    "• Na maioria dos casos, fique em até 4 linhas.\n"
                    "• Se perguntarem a taxa de entrega, diga apenas que varia conforme a localização.\n"
                    "• Para taxa de entrega, peça o endereço ou a localização pelo alfinete do WhatsApp.\n"
                    "• Nunca explique bairros, zonas, km, tabelas, regras internas ou faixas de preço.\n"
                    "• Se pedirem o cardápio, mostre no máximo 5 opções com nome e preço.\n"
                    "• Não despeje o cardápio inteiro, a menos que o cliente insista.\n"
                    "• Se o pedido estiver ambíguo, peça o nome exato dos itens antes de seguir.\n"
                    "• Nunca transforme recomendação em pedido sem confirmação explícita.\n"
                    "• Só diga que PIX foi gerado se existir um código PIX real disponível.\n"
                    "• Nunca diga que criou pedido, calculou entrega ou gerou pagamento se isso ainda não aconteceu.\n"
                )

            # Load products from store — all active, grouped by category, with stock status
            if store:
                try:
                    from apps.stores.models import StoreProduct
                    products = StoreProduct.objects.filter(
                        store=store,
                        is_active=True,
                    ).select_related('category').order_by(
                        'category__sort_order', 'category__name', 'name'
                    ).exclude(tags__contains=['ingrediente'])

                    if products:
                        menu_text = (
                            f"\n📋 CARDÁPIO INTERNO - {store.name} "
                            "(use para consultar e resumir, sem colar tudo ao cliente):\n"
                        )
                        current_category = None

                        for product in products:
                            cat_name = product.category.name if product.category else 'Outros'
                            if cat_name != current_category:
                                current_category = cat_name
                                menu_text += f"\n【{current_category}】\n"

                            stock_note = ''
                            if product.track_stock:
                                if product.stock_quantity <= 0:
                                    stock_note = ' [ESGOTADO]'
                                elif product.stock_quantity <= 3:
                                    stock_note = f' [últimas {product.stock_quantity} unidades]'

                            menu_text += f"• {product.name} - R$ {product.price}{stock_note}\n"

                        context_parts.append(menu_text)

                        # Delivery info
                        if store.delivery_enabled:
                            delivery_text = "\n🚚 ENTREGA:\n"
                            delivery_text += (
                                "• Nunca explique regras internas de taxa, zonas ou tabelas.\n"
                                "• Informe que a taxa varia conforme a localização.\n"
                                "• Para calcular a taxa exata, peça o endereço ou a localização pelo alfinete do WhatsApp.\n"
                            )
                            if store.free_delivery_threshold:
                                delivery_text += f"• Grátis acima de: R$ {store.free_delivery_threshold}\n"
                            context_parts.append(delivery_text)

                except Exception as e:
                    logger.error(f"[AGENT CONTEXT] Error loading store products: {e}")
            
        except Exception as e:
            logger.error(f"[AGENT CONTEXT] Error loading store menu: {e}")
        
        # 3. Load business hours + pickup address
        _DAY_PT = {
            'monday': 'Segunda', 'tuesday': 'Terça', 'wednesday': 'Quarta',
            'thursday': 'Quinta', 'friday': 'Sexta', 'saturday': 'Sábado', 'sunday': 'Domingo',
        }
        try:
            if store and store.operating_hours:
                hours_text = "\n⏰ HORÁRIO DE FUNCIONAMENTO:\n"
                for day, hours in store.operating_hours.items():
                    day_pt = _DAY_PT.get(day.lower(), day.capitalize())
                    hours_text += f"• {day_pt}: {hours.get('open', '--:--')} às {hours.get('close', '--:--')}\n"
                context_parts.append(hours_text)
        except Exception as e:
            logger.error(f"[AGENT CONTEXT] Error loading business hours: {e}")

        try:
            if store:
                location_parts = []
                if getattr(store, 'pickup_enabled', False):
                    address = getattr(store, 'address', '') or ''
                    city = getattr(store, 'city', '') or ''
                    full_address = ', '.join(p for p in [address, city] if p)
                    if full_address:
                        location_parts.append(f"• Endereço para retirada: {full_address}")
                if getattr(store, 'delivery_enabled', False) and not getattr(store, 'pickup_enabled', False):
                    location_parts.append("• Apenas entrega (sem retirada no local)")
                if not getattr(store, 'delivery_enabled', False) and getattr(store, 'pickup_enabled', False):
                    location_parts.append("• Apenas retirada no local (sem entrega)")
                if location_parts:
                    context_parts.append("\n📍 LOCALIZAÇÃO:\n" + "\n".join(location_parts))
        except Exception as e:
            logger.error(f"[AGENT CONTEXT] Error loading location: {e}")

        # 4. Active session state — lets the agent answer "what's in my order?" accurately
        if phone_number:
            try:
                from apps.automation.models import CustomerSession
                from apps.stores.models import StoreProduct as _SP

                session_qs = CustomerSession.objects.filter(
                    phone_number=phone_number,
                    status__in=['active', 'cart_created', 'checkout', 'payment_pending'],
                )
                if store:
                    from apps.automation.models import CompanyProfile as _CP
                    try:
                        profile_ids = _CP.objects.filter(store=store).values_list('id', flat=True)
                        session_qs = session_qs.filter(company_id__in=profile_ids)
                    except Exception:
                        pass

                session = session_qs.order_by('-updated_at').first()
                if session and session.cart_data:
                    cart_data = session.cart_data
                    session_parts = []

                    pending_items = cart_data.get('pending_items') or []
                    if pending_items:
                        item_lines = []
                        for it in pending_items:
                            try:
                                prod = _SP.objects.get(id=it['product_id'])
                                item_lines.append(f"  - {it['quantity']}x {prod.name} (R$ {prod.price})")
                            except Exception:
                                item_lines.append(f"  - {it['quantity']}x produto #{it.get('product_id','?')}")
                        session_parts.append("Itens no carrinho atual:\n" + "\n".join(item_lines))

                    delivery_method = cart_data.get('pending_delivery_method')
                    if delivery_method:
                        session_parts.append(f"Método de entrega escolhido: {delivery_method}")

                    delivery_address = cart_data.get('delivery_address')
                    if delivery_address:
                        session_parts.append(f"Endereço de entrega: {delivery_address}")

                    delivery_fee = cart_data.get('delivery_fee_calculated')
                    if delivery_fee is not None:
                        session_parts.append(f"Taxa de entrega calculada: R$ {delivery_fee:.2f}")

                    if cart_data.get('waiting_for_address'):
                        session_parts.append("Status: aguardando endereço de entrega do cliente.")

                    if session.pix_code:
                        session_parts.append(
                            f"Status: pagamento PIX gerado, aguardando confirmação.\n"
                            f"Código PIX (copia e cola): {session.pix_code}"
                        )
                        if session.pix_qr_code:
                            session_parts.append(f"QR Code PIX (base64): {session.pix_qr_code[:50]}... [truncado]")

                    if session_parts:
                        context_parts.append("\n🛒 ESTADO DO PEDIDO ATUAL:\n" + "\n".join(session_parts))

            except Exception as e:
                logger.error(f"[AGENT CONTEXT] Error loading session state: {e}")

            try:
                from apps.core.utils import normalize_phone_number
                from apps.stores.models import StoreOrder

                normalized_phone = normalize_phone_number(phone_number)
                phone_candidates = {
                    phone_number,
                    normalized_phone,
                    f"+{normalized_phone}" if normalized_phone else '',
                    ''.join(filter(str.isdigit, phone_number or '')),
                }
                phone_candidates = [value for value in dict.fromkeys(v for v in phone_candidates if v)]

                recent_order_qs = StoreOrder.objects.filter(
                    customer_phone__in=phone_candidates,
                )
                if store:
                    recent_order_qs = recent_order_qs.filter(store=store)

                recent_order = recent_order_qs.order_by('-created_at').first()
                if recent_order:
                    order_summary = [
                        f"Pedido mais recente: #{recent_order.order_number}",
                        f"Status: {recent_order.status}",
                        f"Pagamento: {recent_order.payment_status}",
                        f"Total: R$ {recent_order.total}",
                        f"Entrega: {recent_order.get_delivery_method_display()}",
                    ]
                    context_parts.append("\n🧾 ÚLTIMO PEDIDO DO CLIENTE:\n" + "\n".join(order_summary))
            except Exception as e:
                logger.error(f"[AGENT CONTEXT] Error loading recent order summary: {e}")

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
        self._last_created_order = None

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
            """Lista as categorias de produtos disponíveis para venda (saladas, molhos, combos, etc)."""
            if not store:
                return "Cardápio indisponível no momento."
            try:
                from apps.stores.models import StoreCategory
                cats = StoreCategory.objects.filter(
                    store=store, is_active=True
                ).exclude(
                    name__istartswith='Ingrediente'
                ).order_by('sort_order')
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
                info = (
                    "A taxa de entrega varia conforme a localização do cliente."
                    "\nPeça o endereço ou a localização pelo alfinete do WhatsApp para calcular certinho."
                )
                if store.free_delivery_threshold:
                    info += f"\nEntrega GRÁTIS para pedidos acima de R$ {store.free_delivery_threshold}"
                if store.min_order_value:
                    info += f"\nPedido mínimo: R$ {store.min_order_value}"
                return info
            except Exception as exc:
                return f"Erro ao consultar entrega: {exc}"

        @tool
        def consultar_pagamento() -> str:
            """Consulta o status de pagamento e retorna o código PIX do pedido pendente do cliente."""
            pix_data = self._get_pending_pix_payment(phone_number=phone_number, store=store)
            if pix_data.get('found'):
                return pix_data['pix_code']
            return pix_data.get('message') or 'Nenhum PIX pendente encontrado.'

        return [buscar_produto, listar_categorias, verificar_pedido_pendente,
                consultar_historico_pedidos, informacoes_entrega, consultar_pagamento]

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
        # Kimi doesn't handle tool loops reliably.  NVIDIA (Llama 70b+), OpenAI,
        # and Anthropic support function calling correctly.
        store = self._get_store_for_context(conversation_id)
        direct_reply = self._get_direct_runtime_reply(message, store=store)
        if direct_reply:
            processing_time = time.time() - start_time
            if memory:
                try:
                    memory.add_user_message(message)
                    memory.add_ai_message(direct_reply)
                except Exception as e:
                    logger.warning(f"Error saving memory for direct runtime reply: {e}")
            return {
                'response': direct_reply,
                'session_id': session_id,
                'processing_time': processing_time,
                'model': self.agent.model_name,
                'tokens_used': 0,
                'order_created': None,
            }

        tools = self._build_tools(phone_number=phone_number or "", store=store)
        allowed_tools = self._resolve_allowed_tools(message)
        if allowed_tools == {'consultar_pagamento'}:
            pix_data = self._get_pending_pix_payment(phone_number=phone_number or "", store=store)
            processing_time = time.time() - start_time
            if pix_data.get('found'):
                pix_code = pix_data['pix_code']
                if memory:
                    try:
                        memory.add_user_message(message)
                        memory.add_ai_message(pix_code)
                    except Exception as e:
                        logger.warning(f"Error saving memory for PIX response: {e}")
                return {
                    'response': pix_code,
                    'session_id': session_id,
                    'processing_time': processing_time,
                    'model': self.agent.model_name,
                    'tokens_used': 0,
                    'order_created': None,
                    'whatsapp_response': {
                        'type': 'template',
                        'template_name': 'codigo_verificacao',
                        'language_code': 'pt_BR',
                        'components': [
                            {
                                'type': 'body',
                                'parameters': [
                                    {'type': 'text', 'text': pix_code},
                                ],
                            },
                        ],
                    },
                }

            response_text = pix_data.get('message') or 'Nenhum PIX pendente encontrado.'
            if memory:
                try:
                    memory.add_user_message(message)
                    memory.add_ai_message(response_text)
                except Exception as e:
                    logger.warning(f"Error saving memory for PIX fallback: {e}")
            return {
                'response': response_text,
                'session_id': session_id,
                'processing_time': processing_time,
                'model': self.agent.model_name,
                'tokens_used': 0,
                'order_created': None,
            }
        if allowed_tools:
            tools = [tool for tool in tools if tool.name in allowed_tools]
        tool_map = {t.name: t for t in tools}
        _TOOL_CAPABLE_PROVIDERS = {Agent.AgentProvider.OPENAI, Agent.AgentProvider.ANTHROPIC, Agent.AgentProvider.NVIDIA}
        _use_tools = self.agent.provider in _TOOL_CAPABLE_PROVIDERS and bool(tools)
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
            max_iterations = 2 if allowed_tools else 5
            for _iteration in range(max_iterations):
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

            created_order = getattr(self, '_last_created_order', None)
            if created_order:
                order_number = created_order.get('order_number')
                if order_number and order_number not in response_text:
                    response_text = (
                        f"{response_text.strip()}\n\n"
                        f"Pedido #{order_number} criado no sistema.\n"
                        f"Total: R$ {created_order.get('total', 0):.2f}.\n"
                        f"Status: {created_order.get('status')} / pagamento {created_order.get('payment_status')}."
                    ).strip()

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
                'order_created': created_order,
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
            agent = Agent.objects.get(id=agent_id, is_active=True, status=Agent.AgentStatus.ACTIVE)
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
        notes: str = '',
        store=None,
        store_slug: str = '',
        conversation_id: Optional[str] = None,
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
        from apps.stores.models import Store, StoreProduct, StoreCart
        from apps.stores.services.cart_service import cart_service
        from apps.stores.services.checkout_service import CheckoutService
        from apps.users.models import UnifiedUser
        
        try:
            # Resolve store from explicit arg > slug > conversation > legacy fallback.
            if store is None and store_slug:
                store = Store.objects.filter(slug=store_slug).first()
            if store is None and conversation_id:
                try:
                    from apps.conversations.models import Conversation
                    from apps.automation.services.context_service import AutomationContextService
                    conversation = Conversation.objects.select_related('account').get(id=conversation_id)
                    store = AutomationContextService.resolve(conversation=conversation).store
                except Exception:
                    store = None
            if store is None:
                store = Store.objects.filter(slug='pastita').first()
            if not store:
                return {'success': False, 'error': 'Loja não encontrada'}
            
            # UnifiedUser is useful for identity metadata, but StoreCart.user expects
            # the Django auth user model, not UnifiedUser.
            unified_user = UnifiedUser.objects.filter(phone_number=phone_number).first()
            
            # Create cart
            cart = StoreCart.objects.create(
                store=store,
                user=None,
                session_key=str(uuid.uuid4()),
                metadata={
                    'source': 'whatsapp_agent',
                    'phone_number': phone_number,
                },
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
                'name': customer_name or (unified_user.name if unified_user else 'Cliente WhatsApp'),
                'phone': phone_number,
                'email': unified_user.email if unified_user and unified_user.email else f"cliente@{store.slug}.com.br"
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
