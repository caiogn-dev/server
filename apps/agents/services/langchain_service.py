"""
Langchain Service for Agent management - Fixed for Kimi Coding API
"""
import json
import time
import uuid
import logging
import re
import unicodedata
from decimal import Decimal
from typing import List, Dict, Any, Optional

from django.conf import settings
from django.core.cache import cache
from django.db import models
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_community.chat_message_histories import RedisChatMessageHistory

from apps.core.exceptions import BaseAPIException
from ..models import Agent, AgentConversation, AgentMessage
from .llm_cost import accumulate_usage, estimate_cost_brl

logger = logging.getLogger(__name__)

_MENU_CTX_TTL = 60 * 30  # 30 min; invalidação por signal garante frescor


def menu_context_cache_key(store_id) -> str:
    return f"agent:menu_ctx:{store_id}"


def invalidate_menu_context(store_id) -> None:
    if store_id:
        cache.delete(menu_context_cache_key(store_id))


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
        self.redis_client = self._create_redis_client()

    def _create_redis_client(self):
        import redis
        redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
        return redis.from_url(redis_url, decode_responses=True)

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

    def _phone_candidates(self, phone_number: str) -> List[str]:
        """Return canonical phone variants used across WhatsApp, users and orders."""
        if not phone_number:
            return []

        try:
            from apps.core.utils import normalize_phone_number

            normalized = normalize_phone_number(phone_number)
        except Exception:
            normalized = ''

        digits = re.sub(r'\D', '', phone_number or '')
        variants = [
            phone_number,
            digits,
            normalized,
            f"+{normalized}" if normalized else '',
        ]

        if digits.startswith('55'):
            variants.append(digits[2:])
        elif digits:
            variants.append(f"55{digits}")
            variants.append(f"+55{digits}")

        return [value for value in dict.fromkeys(v for v in variants if v)]

    def _format_address_for_context(self, address: Any) -> str:
        """Format address dicts/strings compactly for agent context."""
        if not address:
            return ''
        if isinstance(address, str):
            return address
        if not isinstance(address, dict):
            return str(address)

        if address.get('formatted'):
            return str(address['formatted'])

        parts = [
            address.get('street') or address.get('address') or address.get('raw_address'),
            address.get('number'),
            address.get('complement'),
            address.get('neighborhood'),
            address.get('city'),
            address.get('state'),
            address.get('zip_code'),
        ]
        return ', '.join(str(part) for part in parts if part)

    def _is_store_identity_name(self, name: str, store=None) -> bool:
        """Return True when a supposed customer name is actually the store identity."""
        normalized_name = self._normalize_runtime_text(name)
        if not normalized_name:
            return False

        blocked = {'cliente whatsapp', 'cliente', 'desconhecido'}
        if normalized_name in blocked:
            return True

        candidates = []
        if store:
            candidates.extend([
                getattr(store, 'name', ''),
                getattr(store, 'slug', ''),
                getattr(store, 'whatsapp_number', ''),
            ])
        try:
            for account in self.agent.accounts.all()[:3]:
                candidates.extend([
                    getattr(account, 'name', ''),
                    getattr(account, 'display_phone_number', ''),
                    getattr(account, 'phone_number', ''),
                ])
        except Exception:
            pass

        for candidate in candidates:
            normalized_candidate = self._normalize_runtime_text(candidate)
            if normalized_candidate and normalized_name == normalized_candidate:
                return True

        return False

    def _build_customer_context(
        self,
        *,
        phone_number: str,
        conversation_id: Optional[str] = None,
        store=None,
    ) -> str:
        """
        Build factual CRM/order context for the current customer.

        This context is intentionally read-only. It lets the agent answer who the
        customer is and what they bought before, but explicitly forbids reusing
        old orders as the current cart without a new confirmation.
        """
        phone_candidates = self._phone_candidates(phone_number)
        if not phone_candidates and not conversation_id:
            return ''

        try:
            from django.db.models import Count
            from apps.conversations.models import Conversation
            from apps.stores.models import StoreCustomer, StoreOrder
            from apps.users.models import UnifiedUser
        except Exception as exc:
            logger.error("[AGENT CONTEXT] Error importing customer context models: %s", exc)
            return ''

        name_candidates: List[str] = []
        saved_addresses: List[str] = []

        try:
            if conversation_id:
                conv = Conversation.objects.filter(id=conversation_id).first()
                if conv:
                    if conv.contact_name:
                        name_candidates.append(conv.contact_name)
                    if conv.phone_number:
                        phone_candidates.extend(self._phone_candidates(conv.phone_number))
                    if conv.wa_id:
                        phone_candidates.extend(self._phone_candidates(conv.wa_id))
        except Exception as exc:
            logger.warning("[AGENT CONTEXT] Conversation customer lookup failed: %s", exc)

        phone_candidates = [value for value in dict.fromkeys(phone_candidates) if value]

        try:
            store_customer_qs = StoreCustomer.objects.filter(
                models.Q(phone__in=phone_candidates) | models.Q(whatsapp__in=phone_candidates)
            ).select_related('store', 'user')
            if store:
                store_customer_qs = store_customer_qs.filter(store=store)

            for store_customer in store_customer_qs[:3]:
                full_name = store_customer.user.get_full_name() or getattr(store_customer.user, 'email', '')
                if (
                    full_name
                    and '@pastita.local' not in full_name
                    and not self._is_store_identity_name(full_name, store=store)
                ):
                    name_candidates.append(full_name)
                for addr in store_customer.address_list.order_by('-is_default', '-created_at')[:2]:
                    formatted = self._format_address_for_context({
                        'street': addr.street,
                        'number': addr.number,
                        'neighborhood': addr.neighborhood,
                        'city': addr.city,
                        'state': addr.state,
                        'formatted': addr.formatted,
                    })
                    if formatted:
                        saved_addresses.append(formatted)
        except Exception as exc:
            logger.warning("[AGENT CONTEXT] StoreCustomer lookup failed: %s", exc)

        try:
            for user in UnifiedUser.objects.filter(phone_number__in=phone_candidates)[:3]:
                if (
                    user.name
                    and user.name.lower() != 'desconhecido'
                    and not self._is_store_identity_name(user.name, store=store)
                ):
                    name_candidates.append(user.name)
        except Exception as exc:
            logger.warning("[AGENT CONTEXT] UnifiedUser lookup failed: %s", exc)

        try:
            order_qs = StoreOrder.objects.filter(customer_phone__in=phone_candidates)
            if store:
                order_qs = order_qs.filter(store=store)

            order_qs = order_qs.select_related('store').prefetch_related('items').order_by('-created_at')
            recent_orders = list(order_qs[:5])
            if not recent_orders and not name_candidates and not saved_addresses:
                return ''

            if recent_orders:
                for order in recent_orders:
                    if order.customer_name and not self._is_store_identity_name(order.customer_name, store=store):
                        name_candidates.append(order.customer_name)
                    formatted = self._format_address_for_context(order.delivery_address)
                    if formatted:
                        saved_addresses.append(formatted)

            total_orders = order_qs.count()
            stats = order_qs.order_by().values('status').annotate(count=Count('id'))
            status_counts = {row['status']: row['count'] for row in stats}
            successful_count = sum(
                status_counts.get(status, 0)
                for status in ('paid', 'confirmed', 'preparing', 'ready', 'out_for_delivery', 'delivered', 'completed')
            )
            cancelled_count = status_counts.get('cancelled', 0)

            customer_name = next(
                (
                    name for name in name_candidates
                    if name
                    and name.lower() != 'desconhecido'
                    and not self._is_store_identity_name(name, store=store)
                ),
                '',
            )
            lines = [
                "👤 CONTEXTO DO CLIENTE (dados reais do CRM/pedidos):",
                "• Use apenas como histórico/identidade. Nunca trate pedido antigo como pedido atual sem confirmação nova.",
            ]
            if customer_name:
                lines.append(f"• Nome provável: {customer_name}")
            if phone_candidates:
                lines.append(f"• Telefones equivalentes: {', '.join(phone_candidates[:4])}")
            lines.append(
                f"• Total de pedidos encontrados: {total_orders}"
                f" ({successful_count} ativos/concluídos, {cancelled_count} cancelados)"
            )

            unique_addresses = []
            for address in saved_addresses:
                if address and address not in unique_addresses:
                    unique_addresses.append(address)
            if unique_addresses:
                lines.append("• Endereço salvo/mais recente: " + unique_addresses[0])

            if recent_orders:
                lines.append("• Pedidos recentes:")
                for order in recent_orders:
                    items = ", ".join(
                        f"{item.quantity}x {item.product_name}"
                        for item in order.items.all()[:5]
                    ) or "sem itens salvos"
                    address = self._format_address_for_context(order.delivery_address)
                    address_text = f" | endereço: {address}" if address else ""
                    lines.append(
                        f"  - #{order.order_number} em {order.created_at.strftime('%d/%m/%Y')}: "
                        f"{items} | total R$ {order.total} | status {order.status}/{order.payment_status}"
                        f"{address_text}"
                    )

            return "\n".join(lines)
        except Exception as exc:
            logger.error("[AGENT CONTEXT] Error loading customer order history: %s", exc)
            return ''

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

            phone_candidates = self._phone_candidates(phone_number)
            session_qs = CustomerSession.objects.filter(phone_number__in=phone_candidates)
            if store:
                from apps.automation.models import CompanyProfile as _CP
                profile_ids = _CP.objects.filter(store=store).values_list('id', flat=True)
                session_qs = session_qs.filter(company_id__in=profile_ids)

            session = session_qs.order_by('-updated_at').first()
            if session:
                # Preferir StoreOrder como fonte de verdade quando disponível
                _order = session.order if session.order_id else None
                _pix_code = (_order.pix_code if _order else None) or session.pix_code
                _pix_expires = (_order.pix_expires_at if _order else None) or session.pix_expires_at
                if _pix_code:
                    if _pix_expires and _pix_expires <= timezone.now():
                        return {
                            'found': False,
                            'expired': True,
                            'message': 'O PIX gerado expirou. Um novo pagamento precisa ser gerado.',
                        }
                    return {
                        'found': True,
                        'pix_code': _pix_code,
                        'expires_at': _pix_expires,
                        'source': 'store_order' if _order and _order.pix_code else 'customer_session',
                    }

            order = StoreOrder.objects.filter(
                customer_phone__in=phone_candidates,
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

    def _resolve_store(self, conversation_id) -> Optional['Store']:
        """
        Resolve a store for the current conversation, guarded so it never raises.

        Primeiro tenta o contexto canônico de automação (via Conversation), depois
        cai para a primeira conta associada ao agente. Retorna a store ou None.
        """
        store = None

        if conversation_id:
            try:
                from apps.conversations.models import Conversation
                from apps.automation.services.context_service import AutomationContextService
                conv = Conversation.objects.select_related('account').get(id=conversation_id)
                store = AutomationContextService.resolve(conversation=conv).store
                if store:
                    logger.info(f"[AGENT CONTEXT] Found store via automation context: {store.name}")
            except Conversation.DoesNotExist:
                logger.warning(f"[AGENT CONTEXT] Conversation {conversation_id} not found")
            except Exception as e:
                logger.error(f"[AGENT CONTEXT] Error loading store from automation context: {e}")

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

        return store

    def _build_menu_text(self, store) -> str:
        """Formata o CARDÁPIO INTERNO da loja. Cacheado em Redis por store.id
        (invalidado no save de produto/categoria). Retorna '' quando não há produtos."""
        key = menu_context_cache_key(store.id)
        cached = cache.get(key)
        if cached is not None:        # '' é um hit válido (loja sem produtos)
            return cached

        from apps.stores.models import StoreProduct
        products = StoreProduct.objects.filter(
            store=store,
            is_active=True,
        ).select_related('category').order_by(
            'category__sort_order', 'category__name', 'name'
        ).exclude(tags__contains=['ingrediente'])

        menu_text = ''
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

        cache.set(key, menu_text, _MENU_CTX_TTL)
        return menu_text

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

        # Resolve the store ONCE, before building customer context — assim o
        # contexto do cliente já é montado com escopo na store certa numa única
        # chamada (antes resolvíamos depois e refazíamos o contexto, desperdício).
        store = self._resolve_store(conversation_id)

        # 1. Load customer identity/order context (scoped to the resolved store).
        # Keep this factual and guarded: history is useful for CRM answers, but
        # must never become the current cart without explicit confirmation.
        #
        # MUDANÇA INTENCIONAL (isolamento multi-tenant): montamos o contexto do
        # cliente UMA vez, já com escopo na store resolvida. O fluxo antigo fazia
        # uma 1ª passada com store=None e só a descartava se a passada com escopo
        # tivesse conteúdo — ou seja, quando o cliente só tinha histórico em OUTRA
        # loja, dados de outro tenant (nome/endereço/pedidos) vazavam pro prompt
        # desta loja. Agora, se não há contexto desta loja, nada é anexado. Ver
        # test_dynamic_context.test_no_cross_store_customer_leak.
        try:
            customer_context = self._build_customer_context(
                phone_number=phone_number,
                conversation_id=conversation_id,
                store=store,
            )
            if customer_context:
                context_parts.append(customer_context)
        except Exception as e:
            logger.error(f"[AGENT CONTEXT] Error loading customer/order data: {e}")

        # 2. Load store menu/catalog
        try:
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
                    "• Ofereça APENAS produtos que aparecem no CARDÁPIO INTERNO acima — nunca sugira itens fora dele.\n"
                    "• Nunca transforme recomendação em pedido sem confirmação explícita.\n"
                    "• Só diga que PIX foi gerado se existir um código PIX real disponível.\n"
                    "• Nunca diga que criou pedido, calculou entrega ou gerou pagamento se isso ainda não aconteceu.\n"
                )

            # Load products from store — all active, grouped by category, with stock status
            if store:
                try:
                    menu_text = self._build_menu_text(store)

                    if menu_text:
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
                all_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                hours_text = "\n⏰ HORÁRIO DE FUNCIONAMENTO:\n"
                for day in all_days:
                    day_pt = _DAY_PT.get(day, day.capitalize())
                    day_hours = store.operating_hours.get(day)
                    if day_hours:
                        hours_text += f"• {day_pt}: {day_hours.get('open', '--:--')} às {day_hours.get('close', '--:--')}\n"
                    else:
                        hours_text += f"• {day_pt}: FECHADO\n"
                context_parts.append(hours_text)
        except Exception as e:
            logger.error(f"[AGENT CONTEXT] Error loading business hours: {e}")

        try:
            if store:
                location_parts = []
                address = getattr(store, 'address', '') or ''
                city = getattr(store, 'city', '') or ''
                full_address = ', '.join(p for p in [address, city] if p)
                if full_address:
                    location_parts.append(f"• Endereço da loja: {full_address}")
                if getattr(store, 'delivery_enabled', False) and not getattr(store, 'pickup_enabled', False):
                    location_parts.append("• Apenas entrega (sem retirada no local)")
                elif not getattr(store, 'delivery_enabled', False) and getattr(store, 'pickup_enabled', False):
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

                phone_candidates = self._phone_candidates(phone_number)
                session_qs = CustomerSession.objects.filter(
                    phone_number__in=phone_candidates,
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
                        # Batch: 1 query para TODOS os produtos do carrinho (evita N+1 —
                        # antes era 1 query por item). Mesma saída de antes.
                        product_ids = [it.get('product_id') for it in pending_items if it.get('product_id')]
                        products_by_id = {
                            str(p.id): p
                            for p in _SP.objects.filter(id__in=product_ids).only('id', 'name', 'price')
                        }
                        item_lines = []
                        for it in pending_items:
                            prod = products_by_id.get(str(it.get('product_id')))
                            if prod is not None:
                                item_lines.append(f"  - {it['quantity']}x {prod.name} (R$ {prod.price})")
                            else:
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

                    last_order = cart_data.get('last_order') or {}
                    if last_order:
                        last_order_lines = [
                            f"Último pedido na sessão: #{last_order.get('order_number', '?')}",
                            f"Status: {last_order.get('status', '?')}",
                            f"Pagamento: {last_order.get('payment_status', '?')}",
                            f"Total: R$ {last_order.get('total', '?')}",
                            f"Entrega: {last_order.get('delivery_method', '?')}",
                        ]
                        order_items = last_order.get('items') or []
                        if order_items:
                            item_lines = [
                                f"  - {item.get('quantity', '?')}x {item.get('product_name', 'produto')} "
                                f"(R$ {item.get('subtotal', '?')})"
                                for item in order_items[:8]
                            ]
                            last_order_lines.append("Itens:\n" + "\n".join(item_lines))
                        session_parts.append("\n".join(last_order_lines))

                    # Só injeta PIX se o pagamento AINDA está pendente.
                    # Quando payment_status=paid ou order.status em fase de preparo/entrega,
                    # o LLM NÃO deve reenviar o código — já foi pago ou enviado antes.
                    _ctx_order = session.order if session.order_id else None
                    _order_paid = (
                        (_ctx_order and _ctx_order.payment_status == 'paid')
                        or session.status in ('payment_confirmed', 'completed', 'order_placed')
                    )
                    _ctx_pix_code = ((_ctx_order.pix_code if _ctx_order else None) or session.pix_code) if not _order_paid else None
                    _ctx_pix_qr = ((_ctx_order.pix_qr_code if _ctx_order else None) or session.pix_qr_code) if not _order_paid else None
                    if _ctx_pix_code:
                        session_parts.append(
                            f"Status: pagamento PIX gerado, aguardando confirmação.\n"
                            f"Código PIX (copia e cola): {_ctx_pix_code}"
                        )
                        if _ctx_pix_qr:
                            session_parts.append(f"QR Code PIX (base64): {_ctx_pix_qr[:50]}... [truncado]")

                    if session_parts:
                        context_parts.append("\n🛒 ESTADO DO PEDIDO ATUAL:\n" + "\n".join(session_parts))

            except Exception as e:
                logger.error(f"[AGENT CONTEXT] Error loading session state: {e}")

            try:
                from apps.core.utils import normalize_phone_number
                from apps.stores.models import StoreOrder

                normalized_phone = normalize_phone_number(phone_number)
                phone_candidates = self._phone_candidates(phone_number)
                if normalized_phone:
                    phone_candidates.extend(self._phone_candidates(normalized_phone))
                phone_candidates = [value for value in dict.fromkeys(phone_candidates) if value]

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

                    # Guardrail: quando pedido está pronto/em entrega/entregue,
                    # o LLM não deve perguntar confirmações nem reenviar PIX.
                    _terminal_statuses = {'ready', 'out_for_delivery', 'delivered', 'completed', 'preparing'}
                    if recent_order.status in _terminal_statuses or recent_order.payment_status == 'paid':
                        context_parts.append(
                            "\n⚠️ REGRA CRÍTICA: O pagamento já foi confirmado e o pedido está sendo processado/entregue. "
                            "NUNCA peça confirmação de envio ao cliente. "
                            "NUNCA reenvie o código PIX. "
                            "Se o cliente disser 'ok', 'entendi', 'certo' ou algo parecido, "
                            "responda brevemente (ex: 'Perfeito! 😊') e não inicie novo fluxo de pedido."
                        )
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

    # ── Composição do cardápio ───────────────────────────────────────────────
    # O modelo só para de inventar "o molho vem incluso" quando a composição
    # chega como DADO. Nada aqui é opinião: sai tudo do que está cadastrado.

    @staticmethod
    def _brl(valor) -> str:
        try:
            return f"R$ {Decimal(str(valor)):.2f}".replace('.', ',')
        except Exception:
            return "R$ —"

    @staticmethod
    def _slug_compare(texto: str) -> str:
        import unicodedata
        return unicodedata.normalize('NFD', texto or '').encode('ascii', 'ignore').decode().lower()

    def _match_product(self, store, nome: str):
        """Melhor casamento por nome. Empate resolve pelo nome mais curto —
        'Molho' ganha de 'Molho Especial da Casa' quando o cliente diz 'molho'."""
        from apps.stores.models import StoreProduct
        alvo = self._slug_compare(nome).strip()
        if not alvo:
            return None
        candidatos = [
            p for p in StoreProduct.objects.filter(store=store, is_active=True)
                                           .select_related('category')
            if alvo in self._slug_compare(p.name)
        ]
        if not candidatos:
            return None
        return sorted(
            candidatos,
            key=lambda p: (self._slug_compare(p.name) != alvo, len(p.name)),
        )[0]

    def _match_combo(self, store, nome: str):
        from apps.stores.models import StoreCombo
        alvo = self._slug_compare(nome).strip()
        if not alvo:
            return None
        candidatos = [
            c for c in StoreCombo.objects.filter(store=store, is_active=True)
            if alvo in self._slug_compare(c.name)
        ]
        if not candidatos:
            return None
        return sorted(
            candidatos,
            key=lambda c: (self._slug_compare(c.name) != alvo, len(c.name)),
        )[0]

    def _descrever_produto(self, produto) -> str:
        from apps.stores.models import ComboProductGroup

        cat = produto.category.name if produto.category else 'Geral'
        linhas = [f"{produto.name} — {self._brl(produto.price)}  [{cat}]"]

        if getattr(produto, 'description', ''):
            linhas.append(produto.description)

        variantes = [v for v in produto.variants.filter(is_active=True)]
        if variantes:
            opcoes = ", ".join(
                f"{v.name} ({self._brl(v.get_price())})" for v in variantes
            )
            linhas.append(f"Opções/sabores: {opcoes}")

        # Onde esse item REALMENTE vem incluso — o contraexemplo honesto.
        combos = ComboProductGroup.objects.filter(
            models.Q(product=produto) | models.Q(product_options__product=produto)
            | models.Q(variant_limits__variant__product=produto)
        ).select_related('combo').distinct()
        nomes_combo = sorted({g.combo.name for g in combos if g.combo.is_active})
        if nomes_combo:
            linhas.append("Vem incluso nestes combos: " + ", ".join(nomes_combo))

        linhas.append(
            "Não acompanha nenhum item extra por padrão — molho, bebida e "
            "complementos são vendidos à parte, exceto dentro dos combos citados."
        )
        return "\n".join(linhas)

    def _descrever_combo(self, combo) -> str:
        linhas = [f"{combo.name} — {self._brl(combo.price)}"]
        if getattr(combo, 'description', ''):
            linhas.append(combo.description)

        grupos = combo.groups.all().select_related('product').prefetch_related(
            'product_options__product', 'variant_limits__variant__product'
        )
        if grupos:
            linhas.append("O que vem dentro:")
        for g in grupos:
            rotulo = g.title or (g.product.name if g.product else 'Escolha')
            regra = "obrigatório" if g.is_required else "opcional"
            if g.min_selections == g.max_selections:
                quantos = f"escolha {g.max_selections}"
            else:
                quantos = f"escolha de {g.min_selections} a {g.max_selections}"
            opcoes = [o.product.name for o in g.product_options.all()]
            opcoes += [
                f"{l.variant.product.name} {l.variant.name}".strip()
                for l in g.variant_limits.all()
            ]
            sufixo = f": {', '.join(opcoes)}" if opcoes else ""
            linhas.append(f"  • {rotulo} ({regra}, {quantos}){sufixo}")

        linhas.append("Só vem o que está listado acima. Qualquer outro item é à parte.")
        return "\n".join(linhas)

    def _build_tools(self, phone_number: str = "", store=None):
        """Build Langchain tools bound to the current customer/store context."""
        self._last_created_order = None

        @tool
        def buscar_produto(nome: str) -> str:
            """Busca um produto no cardápio pelo nome ou parte do nome."""
            if not store:
                return "Cardápio indisponível no momento."
            try:
                import unicodedata

                def _normalize(s: str) -> str:
                    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()

                from apps.stores.models import StoreProduct
                all_products = (
                    StoreProduct.objects
                    .filter(store=store, is_active=True)
                    .exclude(tags__contains=["ingrediente"])
                    .select_related("category")
                )
                # Normaliza o nome da busca e faz matching em Python (tolerante a acentos)
                normalized_query = _normalize(nome)
                matched = [
                    p for p in all_products
                    if normalized_query in _normalize(p.name)
                ][:6]

                if not matched:
                    return f"Nenhum produto encontrado para '{nome}'."
                lines = []
                for p in matched:
                    cat = p.category.name if p.category else "Geral"
                    desc = f" — {p.description[:70]}..." if getattr(p, "description", "") else ""
                    lines.append(f"[{cat}] {p.name} — R$ {p.price}{desc} (id: {p.id})")
                return "\n".join(lines)
            except Exception as exc:
                return f"Erro ao buscar produto: {exc}"

        @tool
        def detalhes_do_produto(nome: str) -> str:
            """Composição EXATA de um produto: descrição completa, opções/sabores e o
            que acompanha ou não acompanha. Use SEMPRE antes de afirmar que algum
            item (molho, bebida, acompanhamento) vem incluso."""
            if not store:
                return "Cardápio indisponível no momento."
            try:
                produto = self._match_product(store, nome)
                if not produto:
                    return (
                        f"Não encontrei '{nome}' no cardápio. "
                        "Não afirme nada sobre esse item — ofereça buscar outro."
                    )
                return self._descrever_produto(produto)
            except Exception as exc:
                logger.exception("[AGENT TOOL] detalhes_do_produto falhou")
                return f"Erro ao consultar o produto: {exc}"

        @tool
        def detalhes_do_combo(nome: str) -> str:
            """Composição EXATA de um combo/kit: preço, grupos de escolha, quantos itens
            o cliente escolhe em cada grupo e quais opções existem. Use SEMPRE antes de
            dizer o que vem dentro de um combo."""
            if not store:
                return "Cardápio indisponível no momento."
            try:
                combo = self._match_combo(store, nome)
                if not combo:
                    return (
                        f"Não encontrei o combo '{nome}'. "
                        "Não invente o conteúdo — ofereça ver os combos disponíveis."
                    )
                return self._descrever_combo(combo)
            except Exception as exc:
                logger.exception("[AGENT TOOL] detalhes_do_combo falhou")
                return f"Erro ao consultar o combo: {exc}"

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
                phone_candidates = self._phone_candidates(phone_number)
                order = StoreOrder.objects.filter(
                    customer_phone__in=phone_candidates,
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
                phone_candidates = self._phone_candidates(phone_number)
                orders = StoreOrder.objects.filter(
                    customer_phone__in=phone_candidates,
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

        # ── Cart tools (ordem completa sem intervenção humana) ─────────────────

        _cart_key = f"agent_cart:{self.agent.id}:{phone_number}"
        _sm_cache: list = [None]  # lazy-init CustomerSession manager

        def _session_manager():
            """Lazy-initialise the session manager once per agent call."""
            if _sm_cache[0] is None:
                try:
                    from apps.automation.services.session_manager import get_session_manager
                    from apps.automation.models import CompanyProfile as _CP
                    company = _CP.objects.filter(store=store).first()
                    if company and phone_number:
                        _sm_cache[0] = get_session_manager(company, phone_number)
                except Exception:
                    pass
            return _sm_cache[0]

        def _get_cart() -> dict:
            import json
            raw = self.redis_client.get(_cart_key)
            if raw:
                return json.loads(raw)
            # Fallback: seed from CustomerSession.pending_items (handler pipeline)
            try:
                sm = _session_manager()
                if sm and sm.session and sm.session.cart_data:
                    from apps.stores.models import StoreProduct as _SP
                    pending = sm.session.cart_data.get('pending_items') or []
                    items = []
                    for it in pending:
                        try:
                            p = _SP.objects.get(id=it['product_id'])
                            qty = int(it.get('quantity', 1))
                            up = float(it.get('unit_price') or float(p.price))
                            items.append({
                                'product_id': str(p.id),
                                'product_name': p.name,
                                'quantity': qty,
                                'unit_price': up,
                                'total': round(up * qty, 2),
                            })
                        except Exception:
                            pass
                    if items:
                        cart = {'items': items}
                        _save_cart(cart)
                        return cart
            except Exception:
                pass
            return {"items": []}

        def _save_cart(cart: dict) -> None:
            import json
            self.redis_client.setex(_cart_key, 3600 * 6, json.dumps(cart))
            # Sync back to CustomerSession so the handler pipeline stays in sync
            try:
                sm = _session_manager()
                if sm and sm.session:
                    data = dict(sm.session.cart_data or {})
                    items = cart.get('items', [])
                    if items:
                        data['pending_items'] = [
                            {
                                'product_id': it['product_id'],
                                'quantity': it['quantity'],
                                'unit_price': it.get('unit_price', 0),
                            }
                            for it in items
                        ]
                    else:
                        data.pop('pending_items', None)
                    if cart.get('delivery_address'):
                        data['delivery_address'] = cart['delivery_address']
                    if cart.get('delivery_fee') is not None:
                        data['delivery_fee_calculated'] = float(cart['delivery_fee'])
                    sm.session.cart_data = data
                    sm.session.save(update_fields=['cart_data', 'updated_at'])
            except Exception:
                pass

        @tool
        def adicionar_ao_carrinho(produto_nome: str, quantidade: int = 1) -> str:
            """
            Adiciona um produto ao carrinho do cliente pelo nome.
            Retorna confirmação com nome do produto, preço unitário e subtotal do carrinho.
            Use esta ferramenta quando o cliente quiser pedir um item.
            """
            if not store:
                return "Loja não disponível."
            try:
                import unicodedata

                def _norm(s: str) -> str:
                    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()

                from apps.stores.models import StoreProduct
                all_prods = (
                    StoreProduct.objects
                    .filter(store=store, is_active=True)
                    .exclude(tags__contains=["ingrediente"])
                    .select_related("category")
                )
                nq = _norm(produto_nome)
                matches = [p for p in all_prods if nq in _norm(p.name)]
                if not matches:
                    return f"Produto '{produto_nome}' não encontrado no cardápio."

                product = matches[0]
                cart = _get_cart()
                items = cart["items"]

                # Verifica se já está no carrinho
                existing = next((i for i in items if i["product_id"] == str(product.id)), None)
                if existing:
                    existing["quantity"] += quantidade
                    existing["total"] = float(product.price) * existing["quantity"]
                else:
                    items.append({
                        "product_id": str(product.id),
                        "product_name": product.name,
                        "quantity": quantidade,
                        "unit_price": float(product.price),
                        "total": float(product.price) * quantidade,
                    })
                cart["items"] = items
                _save_cart(cart)

                cart_total = sum(i["total"] for i in items)
                return (
                    f"✓ {quantidade}x {product.name} (R$ {product.price} cada) adicionado.\n"
                    f"Carrinho: {len(items)} item(ns) | Total: R$ {cart_total:.2f}"
                )
            except Exception as exc:
                return f"Erro ao adicionar ao carrinho: {exc}"

        @tool
        def ver_carrinho() -> str:
            """
            Mostra o carrinho atual do cliente com todos os itens e total.
            Use quando o cliente quiser revisar o pedido antes de confirmar.
            """
            cart = _get_cart()
            items = cart.get("items", [])
            if not items:
                return "Carrinho vazio."
            lines = [f"• {i['quantity']}x {i['product_name']} — R$ {i['total']:.2f}" for i in items]
            cart_total = sum(i["total"] for i in items)
            lines.append(f"TOTAL: R$ {cart_total:.2f}")
            return "\n".join(lines)

        @tool
        def remover_do_carrinho(produto_nome: str) -> str:
            """Remove um item do carrinho pelo nome do produto."""
            import unicodedata

            def _norm(s: str) -> str:
                return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()

            cart = _get_cart()
            items = cart.get("items", [])
            nq = _norm(produto_nome)
            original_len = len(items)
            cart["items"] = [i for i in items if nq not in _norm(i["product_name"])]
            if len(cart["items"]) == original_len:
                return f"'{produto_nome}' não está no carrinho."
            _save_cart(cart)
            return f"'{produto_nome}' removido do carrinho."

        @tool
        def salvar_endereco_entrega(endereco: str) -> str:
            """Salva ou atualiza o endereço de entrega para o pedido atual.
            Chame sempre que o cliente informar ou corrigir o endereço — inclusive quando disser
            que informou errado ou quiser mudar. Também calcula e confirma a taxa de entrega."""
            endereco = endereco.strip()
            if not endereco:
                return "Endereço inválido. Informe o endereço completo com quadra/rua e número."
            cart = _get_cart()
            cart['delivery_address'] = endereco
            _save_cart(cart)
            if store:
                try:
                    from apps.stores.services.geo import geo_service
                    geo = geo_service.geocode(endereco, restrict_to_city=True)
                    if geo and geo.get('lat') and geo.get('lng'):
                        fee_info = geo_service.calculate_delivery_fee(
                            store,
                            customer_lat=float(geo['lat']),
                            customer_lng=float(geo['lng']),
                            customer_address_text=geo.get('formatted_address') or endereco,
                        )
                    else:
                        fee_info = geo_service.calculate_delivery_fee(
                            store,
                            destination_address=endereco,
                            customer_address_text=endereco,
                        )
                    if not fee_info.get('is_within_area', True) or fee_info.get('fee') is None:
                        cart.pop('delivery_address', None)
                        _save_cart(cart)
                        return (
                            fee_info.get('message')
                            or "Esse endereço fica fora da nossa área de entrega."
                        )
                    fee = float(fee_info['fee'])
                    cart['delivery_fee'] = fee
                    _save_cart(cart)
                    dist = fee_info.get('distance_km')
                    dist_text = f" ({float(dist):.1f} km)" if dist else ""
                    return (
                        f"Endereço salvo: {geo.get('formatted_address') or endereco}{dist_text}\n"
                        f"Taxa de entrega: {self._format_brl(fee)}"
                    )
                except Exception as exc:
                    logger.warning("[AGENT] salvar_endereco_entrega fee calc failed: %s", exc)
            return f"Endereço salvo: {endereco}"

        @tool
        def finalizar_pedido(endereco: str = "", observacoes: str = "") -> str:
            """
            Finaliza o pedido: cria o pedido no sistema, calcula a taxa de entrega e gera o código PIX.
            Só chame DEPOIS de ter os itens no carrinho e o endereço confirmado via salvar_endereco_entrega.
            Retorna o valor total, taxa de entrega e o código PIX para pagamento.
            """
            if not store:
                return "Loja não disponível."
            if not phone_number:
                return "Telefone do cliente não disponível."

            cart = _get_cart()
            items = cart.get("items", [])
            if not items:
                return "Carrinho vazio. Adicione itens antes de finalizar."
            effective_address = cart.get('delivery_address') or endereco.strip()
            if not effective_address:
                return "Endereço não informado. Use salvar_endereco_entrega com o endereço do cliente."
            endereco = effective_address

            try:
                from apps.whatsapp.services.order_service import WhatsAppOrderService

                customer_name = ""
                try:
                    from apps.stores.models import StoreCustomer
                    phone_candidates = self._phone_candidates(phone_number)
                    cust = StoreCustomer.objects.filter(
                        store=store, phone__in=phone_candidates
                    ).first()
                    customer_name = cust.name if cust else ""
                except Exception:
                    pass

                svc = WhatsAppOrderService(
                    store=store,
                    phone_number=phone_number,
                    customer_name=customer_name,
                )
                result = svc.create_order_from_cart(
                    items=items,
                    delivery_address=endereco,
                    customer_notes=observacoes,
                    delivery_method="delivery",
                    payment_method="pix",
                )

                if not result.get("success"):
                    return f"Não foi possível criar o pedido: {result.get('error', 'erro desconhecido')}"

                # Limpa o carrinho após sucesso
                self.redis_client.delete(_cart_key)

                order = result.get("order")
                pix_code = result.get("pix_code") or result.get("pix", {}).get("qr_code") or ""
                total = result.get("total") or (order.total if order else "?")
                delivery_fee = result.get("delivery_fee", "")
                order_num = order.order_number if order else result.get("order_number", "")

                response = f"Pedido #{order_num} criado!\n"
                if delivery_fee:
                    response += f"Taxa de entrega: R$ {delivery_fee}\n"
                response += f"Total: R$ {total}\n"
                if pix_code:
                    response += f"PIX (copia e cola):\n{pix_code}"
                else:
                    response += "PIX sendo gerado — use consultar_pagamento em instantes."
                return response

            except Exception as exc:
                logger.exception("[AGENT] Erro ao finalizar pedido: %s", exc)
                return f"Erro ao finalizar pedido: {exc}"

        return [
            buscar_produto, detalhes_do_produto, detalhes_do_combo, listar_categorias,
            adicionar_ao_carrinho, ver_carrinho, remover_do_carrinho,
            salvar_endereco_entrega, finalizar_pedido,
            verificar_pedido_pendente, consultar_historico_pedidos,
            informacoes_entrega, consultar_pagamento,
        ]

    def _get_store_for_context(self, conversation_id: Optional[str] = None):
        """Resolve the store for tool binding (same logic as _build_dynamic_context)."""
        store = None
        if conversation_id:
            try:
                from apps.conversations.models import Conversation
                from apps.automation.services.context_service import AutomationContextService
                conv = Conversation.objects.select_related('account').get(id=conversation_id)
                store = AutomationContextService.resolve(conversation=conv).store
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
        conversation_id: Optional[str] = None,
        store=None,
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
        # `store` explícito ganha da descoberta automática.
        #
        # No WhatsApp a loja vem da conversa ou da conta vinculada ao agente.
        # Na tela "Testar Assistente" não existe conversa, e um agente sem
        # conta vinculada resolvia `None` — aí toda pergunta sobre produto
        # respondia "Cardápio indisponível no momento", e quem testava concluía
        # que o catálogo tinha caído.
        store = store or self._get_store_for_context(conversation_id)
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
            usage_acc = {}
            max_iterations = 2 if allowed_tools else 5
            for _iteration in range(max_iterations):
                response = llm_with_tools.invoke(current_messages)
                usage_acc = accumulate_usage(usage_acc, response)
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
                    usage_acc = accumulate_usage(usage_acc, final_response)
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

            model_name = self.agent.model_name
            input_tokens = usage_acc.get('input_tokens', 0)
            output_tokens = usage_acc.get('output_tokens', 0)
            total_tokens = usage_acc.get('total_tokens', 0)
            cost_brl = estimate_cost_brl(model_name, input_tokens, output_tokens)

            logger.info(
                "[LLM COST] model=%s in=%s out=%s total=%s cost_brl=%s agent=%s session=%s",
                model_name, input_tokens, output_tokens, total_tokens,
                cost_brl, self.agent.id, session_id,
            )

            return {
                'response': response_text,
                'session_id': session_id,
                'processing_time': processing_time,
                'model': model_name,
                'tokens_used': total_tokens,        # agora soma de TODAS as iterações
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cost_brl': str(cost_brl),          # str p/ serialização JSON segura
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
