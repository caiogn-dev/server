"""
WhatsApp Intent Handlers

Handlers específicos para cada tipo de intenção detectada.
Cada handler retorna uma resposta adequada ou None para fallback.
"""
import re
import unicodedata
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from django.core.cache import cache

from apps.whatsapp.intents.detector import IntentType, IntentData
from apps.whatsapp.services import create_order_from_whatsapp
from apps.automation.models import AutoMessage
from apps.stores.models import StoreProduct
from apps.stores.models.order import StoreOrder as Order

logger = logging.getLogger(__name__)


# ─── Shared helper: dynamic item extraction ───────────────────────────────────

def _normalize_text(s: str) -> str:
    """Remove accents and lowercase for fuzzy product matching."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s.lower())
        if unicodedata.category(c) != 'Mn'
    )


def _parse_items_from_text_dynamic(text: str, store) -> List[Dict[str, Any]]:
    """
    Extrai pares (product_id, quantity) de um texto livre.

    Estratégia (sem keywords hardcoded):
    1. Regex extrai pares (quantity, search_term) do texto.
    2. Para cada par, busca o produto da loja que melhor corresponde ao search_term:
       a. Correspondência exata (accent-insensitive substring)
       b. Primeira palavra do nome do produto dentro do search_term
       c. Qualquer palavra do search_term dentro do nome do produto
    3. Se nenhum par qty+nome for encontrado, tenta apenas nome → qty=1.
    """
    if not store:
        return []

    text_lower = text.lower().strip()
    if not text_lower:
        return []

    products = list(StoreProduct.objects.filter(store=store, is_active=True))
    if not products:
        return []

    # Pre-compute normalized names once
    normalized_products = [
        (p, _normalize_text(p.name), p.name.lower().split())
        for p in products
    ]

    def _match(search_term: str) -> Optional[Any]:
        norm_search = _normalize_text(search_term)
        best = None
        for product, norm_name, words in normalized_products:
            # Full name substring match (most precise)
            if norm_search in norm_name or norm_name in norm_search:
                return product
            # First word of product in search term
            if words and len(words[0]) > 2 and words[0] in search_term:
                best = best or product
            # Any word of search in product name
            for word in search_term.split():
                if len(word) > 3 and word in norm_name:
                    best = best or product
        return best

    # Patterns: "2 rondelli de frango", "quero 1 lasanha", "1x nhoque"
    quantity_patterns = [
        r'(\d+)\s*x?\s+([\w\s]{3,40}?)(?:\s+(?:e|com|sem|por|para)|$)',
        r'(\d+)\s+([\w\s]{3,40})',
    ]

    found_ids: set = set()
    items: List[Dict[str, Any]] = []

    for pattern in quantity_patterns:
        for qty_str, search_term in re.findall(pattern, text_lower):
            search_term = search_term.strip()
            if not search_term:
                continue
            quantity = int(qty_str)
            product = _match(search_term)
            if product and str(product.id) not in found_ids:
                found_ids.add(str(product.id))
                items.append({'product_id': str(product.id), 'quantity': quantity})

    # Fallback: no quantity mentioned — try just the name, qty=1
    if not items:
        product = _match(text_lower)
        if product:
            items.append({'product_id': str(product.id), 'quantity': 1})

    logger.info('[_parse_items_from_text_dynamic] store=%s text=%r items=%d',
                getattr(store, 'slug', store), text[:60], len(items))
    return items


class HandlerResult:
    """Resultado do processamento de um handler"""
    
    def __init__(
        self,
        response_text: Optional[str] = None,
        use_interactive: bool = False,
        interactive_type: Optional[str] = None,  # 'buttons', 'list'
        interactive_data: Optional[Dict] = None,
        requires_llm: bool = False
    ):
        self.response_text = response_text
        self.use_interactive = use_interactive
        self.interactive_type = interactive_type
        self.interactive_data = interactive_data or {}
        self.requires_llm = requires_llm
    
    @classmethod
    def text(cls, text: str) -> 'HandlerResult':
        """Cria resultado com texto simples"""
        return cls(response_text=text)
    
    @classmethod
    def buttons(cls, body: str, buttons: list, header: Optional[str] = None, 
                footer: Optional[str] = None) -> 'HandlerResult':
        """Cria resultado com botões interativos"""
        return cls(
            response_text="BUTTONS_SENT",
            use_interactive=True,
            interactive_type='buttons',
            interactive_data={
                'body': body, 
                'buttons': buttons,
                'header': header,
                'footer': footer
            }
        )
    
    @classmethod
    def list_message(cls, body: str, button: str, sections: list) -> 'HandlerResult':
        """Cria resultado com lista interativa"""
        return cls(
            response_text="LIST_SENT",
            use_interactive=True,
            interactive_type='list',
            interactive_data={'body': body, 'button': button, 'sections': sections}
        )

    @classmethod
    def product_list(
        cls,
        body: str,
        sections: list,
        header: Optional[str] = None,
        footer: Optional[str] = None,
        catalog_id: Optional[str] = None,
        fallback_sections: Optional[list] = None,
    ) -> 'HandlerResult':
        """Cria resultado com catálogo nativo do WhatsApp."""
        return cls(
            response_text="PRODUCT_LIST_SENT",
            use_interactive=True,
            interactive_type='product_list',
            interactive_data={
                'body': body,
                'sections': sections,
                'header': header,
                'footer': footer,
                'catalog_id': catalog_id,
                'fallback_sections': fallback_sections or [],
            }
        )
    
    @classmethod
    def needs_llm(cls) -> 'HandlerResult':
        """Indica que precisa de LLM"""
        return cls(requires_llm=True)
    
    @classmethod
    def none(cls) -> 'HandlerResult':
        """Sem resposta automática"""
        return cls()


class IntentHandler:
    """Handler base para intenções"""

    def __init__(self, account, conversation, company_profile=None):
        self.account = account
        self.conversation = conversation
        self.company_profile = company_profile or getattr(account, 'company_profile', None)
        self._whatsapp_service = None
        self.store = self._get_store()

    @property
    def whatsapp_service(self):
        """Lazy import to avoid circular import"""
        if self._whatsapp_service is None:
            from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService
            self._whatsapp_service = WhatsAppAPIService(self.account)
        return self._whatsapp_service
    
    @property
    def company(self):
        """Alias for company_profile — both names are used across the codebase."""
        return self.company_profile

    def _get_session_manager(self):
        """
        Resolve customer sessions from the canonical tenant context.

        A bare WhatsApp account can point to an account-only CompanyProfile
        created by signals. For order flows we must prefer the handler's
        store/company profile so cart and checkout state stay in the same
        session.
        """
        from apps.automation.services import get_session_manager

        context_owner = self.company_profile or self.store or self.account
        return get_session_manager(context_owner, self.conversation.phone_number)

    def _get_store(self):
        """Retorna a loja associada"""
        if self.company_profile and hasattr(self.company_profile, 'store'):
            return self.company_profile.store
        return None

    def _normalize_lookup_text(self, value: str) -> str:
        """Normalize free text for neighborhood / product matching."""
        if not value:
            return ""
        normalized = unicodedata.normalize('NFD', str(value).lower())
        return ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')

    def _match_fixed_delivery_zone_from_text(self, message: str) -> Optional[Dict[str, Any]]:
        """Resolve a fixed delivery zone by neighborhood keywords mentioned in text."""
        if not self.store:
            return None

        metadata = getattr(self.store, 'metadata', None) or {}
        zones = metadata.get('fixed_price_zones') or []
        if not zones:
            return None

        normalized_message = self._normalize_lookup_text(message)
        if not normalized_message:
            return None

        for zone in zones:
            keywords = list(zone.get('keywords') or [])
            if zone.get('name'):
                keywords.append(zone['name'])
            for keyword in keywords:
                normalized_keyword = self._normalize_lookup_text(keyword)
                if normalized_keyword and normalized_keyword in normalized_message:
                    return zone
        return None

    def _build_delivery_info_text(self, message: str = "") -> str:
        """Return deterministic delivery information for fee / region questions."""
        if not self.store:
            return (
                "🚚 *Informações de entrega*\n\n"
                "Não consegui carregar os dados da loja agora. Tente novamente em instantes."
            )

        if not getattr(self.store, 'delivery_enabled', True):
            return "🚫 No momento trabalhamos apenas com retirada."

        lines = [
            "🚚 *Informações de entrega*",
            "",
            "A taxa varia de acordo com a localização.",
            "Me envie sua localização pelo *alfinete do WhatsApp* para eu calcular certinho.",
        ]
        if self.store.min_order_value:
            lines.extend(["", f"Pedido mínimo: *R$ {float(self.store.min_order_value):.2f}*"])
        return "\n".join(lines)

    def _build_location_text(self) -> str:
        """Return deterministic store address information."""
        if not self.store:
            return "📍 Não consegui localizar o endereço da loja agora."

        lines = [f"📍 *{self.store.name}*"]
        address_parts = [
            getattr(self.store, 'address', ''),
            getattr(self.store, 'city', ''),
            getattr(self.store, 'state', ''),
            getattr(self.store, 'zip_code', ''),
        ]
        formatted = ", ".join(part for part in address_parts if part)
        if formatted:
            lines.extend(["", formatted])

        whatsapp_number = getattr(self.store, 'whatsapp_number', '') or getattr(self.account, 'phone_number', '')
        if whatsapp_number:
            lines.extend(["", f"WhatsApp: {whatsapp_number}"])
        return "\n".join(lines)

    def _build_contact_text(self) -> str:
        """Return deterministic contact information."""
        if not self.store:
            return "📞 Não consegui carregar o contato da loja agora."

        lines = [f"📞 *Contato - {self.store.name}*"]
        if getattr(self.store, 'phone', ''):
            lines.append(f"• Telefone: {self.store.phone}")
        if getattr(self.store, 'whatsapp_number', ''):
            lines.append(f"• WhatsApp: {self.store.whatsapp_number}")
        if getattr(self.store, 'email', ''):
            lines.append(f"• E-mail: {self.store.email}")
        return "\n".join(lines)

    def _send_pix_confirmation(self, order, pix_code: str) -> 'HandlerResult':
        """Envia confirmação do pedido em duas mensagens:
        1. Resumo do pedido com aviso de que o PIX vem a seguir
        2. Apenas o código PIX (fácil de copiar)
        """
        from apps.stores.models import StoreOrderItem
        order_items = StoreOrderItem.objects.filter(order_id=order.id)
        items_text = '\n'.join(
            f"• {item.quantity}x {item.product_name}"
            for item in order_items
        )
        msg1 = (
            f"✅ *Pedido #{order.order_number} confirmado!*\n\n"
            f"{items_text}\n\n"
            f"💰 *Total: R$ {float(order.total):.2f}*\n\n"
            f"💳 Pague via PIX — o código está na próxima mensagem 👇"
        )
        try:
            self.whatsapp_service.send_text_message(
                to=self.conversation.phone_number,
                text=msg1,
            )
        except Exception as exc:
            logger.warning("[_send_pix_confirmation] Erro ao enviar msg1: %s", exc)

        # Segunda mensagem: somente o código PIX no corpo, com botão abaixo.
        return HandlerResult.buttons(
            body=pix_code,
            buttons=[
                {'id': 'pix_copy', 'title': 'COPIAR CODIGO PIX'},
            ],
        )

    def _handle_address_input(self, address_text: str) -> 'HandlerResult':
        """
        Geocodifica o endereço via HERE, calcula a taxa de entrega e salva na sessão.
        Chamado pelo UnknownHandler quando session.waiting_for_address=True.
        O geocode já aplica "Palmas, Tocantins" e bbox automaticamente.
        """
        session_manager = self._get_session_manager()

        if not self.store:
            session_manager.set_waiting_for_address(False)
            return self._ask_payment_method('delivery')

        try:
            from apps.stores.services.geo import geo_service

            geo = geo_service.geocode(address_text, restrict_to_city=True)
            if not geo or not geo.get('lat'):
                return HandlerResult.text(
                    "❌ Não consegui localizar esse endereço em Palmas - TO.\n\n"
                    "Por favor, tente novamente com mais detalhes:\n"
                    "_Ex: Quadra 304 Sul, Alameda 2, Lote 5, Palmas_"
                )

            return self._process_location_and_ask_payment(
                session_manager=session_manager,
                geo_svc=geo_service,
                lat=geo['lat'],
                lng=geo['lng'],
                formatted_address=geo.get('formatted_address', address_text),
                address_components=geo.get('address', {}),
            )

        except Exception as exc:
            logger.error("[_handle_address_input] Erro geocode: %s", exc, exc_info=True)
            default_fee = float(getattr(self.store, 'default_delivery_fee', 0) or 0)
            session_manager.save_delivery_address_info(address=address_text, fee=default_fee)

        return self._ask_payment_method('delivery')

    def _handle_location_input(self, lat: float, lng: float, address_hint: str = '') -> 'HandlerResult':
        """
        Processa mensagem de localização compartilhada via WhatsApp.
        Já tem lat/lng — pula geocodificação, vai direto para calculate_delivery_fee.
        """
        session_manager = self._get_session_manager()

        if not self.store:
            session_manager.set_waiting_for_address(False)
            return self._ask_payment_method('delivery')

        try:
            from apps.stores.services.geo import geo_service

            address_display = address_hint
            rev_components: dict = {}
            if not address_display:
                try:
                    rev = geo_service.reverse_geocode(lat, lng)
                    if rev:
                        address_display = rev.get('formatted_address', f"{lat:.6f}, {lng:.6f}")
                        rev_components = {
                            k: v for k, v in rev.items()
                            if k in ('street', 'house_number', 'neighborhood', 'city', 'state', 'state_code', 'zip_code')
                            and v
                        }
                except Exception:
                    address_display = f"{lat:.6f}, {lng:.6f}"

            return self._process_location_and_ask_payment(
                session_manager=session_manager,
                geo_svc=geo_service,
                lat=lat,
                lng=lng,
                formatted_address=address_display,
                address_components=rev_components,
            )

        except Exception as exc:
            logger.error("[_handle_location_input] Erro: %s", exc, exc_info=True)
            default_fee = float(getattr(self.store, 'default_delivery_fee', 0) or 0)
            session_manager.save_delivery_address_info(address=address_hint or f"{lat},{lng}", fee=default_fee)

        return self._ask_payment_method('delivery')

    def _process_location_and_ask_payment(
        self,
        session_manager,
        geo_svc,
        lat: float,
        lng: float,
        formatted_address: str,
        address_components: dict = None,
    ) -> 'HandlerResult':
        """Calcula taxa, salva na sessão e mostra resumo do pedido com campo de observações."""
        fee_result = geo_svc.calculate_delivery_fee(
            self.store,
            lat,
            lng,
            customer_address_text=formatted_address,
        )

        fixed_zone_from_text = self._match_fixed_delivery_zone_from_text(formatted_address)
        if fixed_zone_from_text:
            fixed_fee = float(fixed_zone_from_text.get('fee', self.store.default_delivery_fee or 0))
            fee_result = {
                **fee_result,
                'fee': fixed_fee,
                'is_within_area': True,
                'zone': {
                    'id': None,
                    'name': fixed_zone_from_text.get('name') or 'Taxa fixa',
                    'min_distance': None,
                    'max_distance': None,
                },
                'message': f"Entrega com taxa fixa para a região: {fixed_zone_from_text.get('name', 'especial')}",
            }

        if not fee_result.get('is_within_area', True):
            return HandlerResult.text(
                "😔 Infelizmente seu endereço está fora da nossa área de entrega.\n\n"
                "Você pode retirar o pedido em nossa loja! Digite *retirada* para continuar."
            )

        fee = fee_result['fee']
        distance_km = fee_result.get('distance_km')
        duration_minutes = fee_result.get('duration_minutes')

        session_manager.save_delivery_address_info(
            address=formatted_address,
            fee=float(fee),
            distance_km=distance_km,
            duration_minutes=duration_minutes,
            lat=lat,
            lng=lng,
            address_components=address_components or {},
        )

        return self._show_order_summary_and_ask_notes(
            delivery_method='delivery',
            delivery_address=formatted_address,
            delivery_fee=float(fee),
            distance_km=distance_km,
            duration_minutes=duration_minutes,
        )

    def _ask_delivery_method(self, items: List[Dict[str, Any]]) -> 'HandlerResult':
        """Salva itens na sessão e pergunta entrega ou retirada."""
        try:
            session_manager = self._get_session_manager()
            session_manager.save_pending_order_items(items)
        except Exception as exc:
            logger.warning("[_ask_delivery_method] Erro ao salvar itens pendentes: %s", exc)

        store = self.store
        delivery_enabled = getattr(store, 'delivery_enabled', True) if store else True
        pickup_enabled = getattr(store, 'pickup_enabled', True) if store else True

        buttons = []
        if delivery_enabled:
            buttons.append({'id': 'order_delivery', 'title': '🛵 Entrega'})
        if pickup_enabled:
            buttons.append({'id': 'order_pickup', 'title': '🏪 Retirada'})

        if not buttons:
            # Loja sem método configurado — força entrega
            buttons = [{'id': 'order_delivery', 'title': '🛵 Entrega'}]

        return HandlerResult.buttons(
            body="📦 *Como prefere receber seu pedido?*",
            buttons=buttons,
        )

    def _ask_payment_method(self, delivery_method: str) -> 'HandlerResult':
        """Salva delivery_method na sessão e pergunta como o cliente quer pagar."""
        try:
            session_manager = self._get_session_manager()
            session_manager.save_pending_delivery_method(delivery_method)
        except Exception as exc:
            logger.warning("[_ask_payment_method] Erro ao salvar delivery_method: %s", exc)

        buttons = [
            {'id': 'pay_pix', 'title': '💠 PIX'},
            {'id': 'pay_card', 'title': '💳 Cartão Crédito/Débito'},
        ]
        if delivery_method == 'pickup':
            buttons.append({'id': 'pay_pickup', 'title': '💵 Pagar na Retirada'})

        return HandlerResult.buttons(
            body="💳 *Como prefere pagar?*",
            buttons=buttons,
        )

    def _show_order_summary_and_ask_notes(
        self,
        delivery_method: str,
        delivery_address: str = '',
        delivery_fee: float = 0.0,
        distance_km: float = None,
        duration_minutes: float = None,
    ) -> 'HandlerResult':
        """Mostra resumo completo do pedido (itens, endereço, taxa, total) e pede observações."""
        try:
            session_manager = self._get_session_manager()
            items = session_manager.get_pending_order_items()
            session_manager.set_waiting_for_notes(True)
        except Exception as exc:
            logger.warning("[_show_order_summary_and_ask_notes] Erro ao acessar sessão: %s", exc)
            items = []

        lines = ["📋 *Resumo do seu pedido:*\n"]
        subtotal = 0.0

        if items and self.store:
            from apps.stores.models import StoreProduct
            for it in items:
                try:
                    p = StoreProduct.objects.get(id=it['product_id'], is_active=True)
                    qty = int(it.get('quantity', 1))
                    price = float(p.price)
                    item_total = qty * price
                    subtotal += item_total
                    price_fmt = f"R$ {item_total:.2f}".replace('.', ',')
                    lines.append(f"• {qty}x {p.name} — {price_fmt}")
                except Exception as exc:
                    logger.warning("[_show_order_summary_and_ask_notes] Produto %s: %s", it.get('product_id'), exc)

        fee = float(delivery_fee or 0)
        total = subtotal + fee

        if delivery_method == 'delivery':
            dist_text = f" ({distance_km:.1f} km)" if distance_km else ""
            time_text = f" (~{int(duration_minutes)} min)" if duration_minutes else ""
            fee_fmt = f"R$ {fee:.2f}".replace('.', ',') if fee > 0 else "Grátis 🎉"
            addr_display = delivery_address or 'a definir'
            lines.append(f"\n📍 *Endereço:* {addr_display}")
            lines.append(f"🛵 *Taxa de entrega{dist_text}{time_text}:* {fee_fmt}")
        else:
            lines.append("\n🏪 *Retirada no local*")

        total_fmt = f"R$ {total:.2f}".replace('.', ',')
        lines.append(f"\n💰 *Total: {total_fmt}*")
        lines.append(
            "\n📝 *Alguma observação para o preparo?*\n"
            "_(ex: sem cebola, ponto da carne, alergia)_\n\n"
            "Responda *não* para continuar sem observações."
        )

        return HandlerResult.text("\n".join(lines))

    def _handle_notes_input(self, notes_text: str) -> 'HandlerResult':
        """Salva observações do cliente e exibe as formas de pagamento disponíveis."""
        _SKIP_WORDS = {
            'nao', 'n', 'nn', 'no', 'nope', 'nada', 'ok', 'okay', 'tudo bem',
            'tudo certo', 'sem observacao', 'sem observacoes', 'nenhuma',
            'nenhum', 'negativo', 'pode ser', 'pode', 'ta', 'ta bom', 'tá', 'tá bom',
            'sem obs', 'sem nada', 'nao tem', 'nao ha', 'sem', 'nothing',
        }
        session_manager = self._get_session_manager()
        normalized = self._normalize_lookup_text(notes_text)
        notes = '' if normalized in _SKIP_WORDS else notes_text.strip()

        try:
            session_manager.save_customer_notes(notes)
            delivery_method = session_manager.get_pending_delivery_method()
        except Exception as exc:
            logger.warning("[_handle_notes_input] Erro ao salvar observações: %s", exc)
            delivery_method = 'delivery'

        buttons = [
            {'id': 'pay_pix', 'title': '💠 PIX'},
            {'id': 'pay_card', 'title': '💳 Cartão Crédito/Débito'},
        ]
        if delivery_method == 'pickup':
            buttons.append({'id': 'pay_pickup', 'title': '💵 Pagar na Retirada'})

        note_line = f"✅ _Anotado: {notes}_\n\n" if notes else ""
        return HandlerResult.buttons(
            body=f"{note_line}💳 *Como prefere pagar?*",
            buttons=buttons,
        )

    def _finalize_order(
        self,
        items: List[Dict[str, Any]],
        delivery_method: str,
        payment_method: str = 'pix',
        delivery_address: str = '',
        customer_notes: str = '',
        delivery_fee_override: float = None,
        addr_info: dict = None,
    ) -> 'HandlerResult':
        """Cria o pedido com delivery e payment method definidos e retorna confirmação."""
        store_slug = getattr(self.store, 'slug', '') if self.store else ''
        if not store_slug:
            return HandlerResult.text("❌ Loja não disponível no momento.")

        result = create_order_from_whatsapp(
            store_slug=store_slug,
            phone_number=self.conversation.phone_number,
            items=items,
            customer_name=self.get_customer_name(),
            delivery_address=delivery_address,
            customer_notes=customer_notes,
            delivery_method=delivery_method,
            payment_method=payment_method,
            delivery_fee_override=delivery_fee_override,
            addr_info=addr_info,
        )

        if not result.get('success'):
            error = result.get('error', 'Erro desconhecido')
            return HandlerResult.text(
                f"❌ Erro ao criar pedido: {error}\n\nTente novamente ou fale com um atendente."
            )

        order = result['order']
        payment_data = result.get('payment_data', {})
        pm = result.get('payment_method', payment_method)

        if pm == 'pix':
            if payment_data.get('success'):
                return self._send_pix_confirmation(order, payment_data['pix_code'])
            error_msg = payment_data.get('error', 'Tente novamente')
            return HandlerResult.text(
                f"✅ *Pedido #{order.order_number} criado!*\n\n"
                f"💰 Total: R$ {float(order.total):.2f}\n"
                f"⚠️ Erro ao gerar PIX: {error_msg}"
            )

        if pm == 'card':
            if payment_data.get('success'):
                checkout_link = payment_data.get('checkout_link', '')
                return HandlerResult.text(
                    f"✅ *Pedido #{order.order_number} criado!*\n\n"
                    f"💰 *Total: R$ {float(order.total):.2f}*\n\n"
                    f"💳 Clique no link abaixo para pagar com cartão:\n"
                    f"{checkout_link}\n\n"
                    f"⏳ O link é seguro e gerado pelo Mercado Pago."
                )
            error_msg = payment_data.get('error', 'Tente novamente')
            return HandlerResult.text(
                f"✅ *Pedido #{order.order_number} criado!*\n\n"
                f"💰 Total: R$ {float(order.total):.2f}\n"
                f"⚠️ Erro ao gerar link de pagamento: {error_msg}"
            )

        # cash / pay_on_pickup
        return HandlerResult.text(
            f"✅ *Pedido #{order.order_number} confirmado!*\n\n"
            f"💰 *Total: R$ {float(order.total):.2f}*\n\n"
            f"💵 Pagamento na retirada — nos vemos em breve! 🏪"
        )

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        """Processa a intenção e retorna resultado"""
        raise NotImplementedError
    
    def get_customer_name(self) -> str:
        """Retorna nome do cliente"""
        return self.conversation.contact_name or 'Cliente'


class GreetingHandler(IntentHandler):
    """Handler para saudações — retorna boas-vindas com 1 botão 'Ver Opções'."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        company_name = (
            getattr(self.company, 'company_name', None)
            or (self.store.name if self.store else None)
            or 'nossa loja'
        )
        customer_name = self.get_customer_name()
        greeting = f"Olá, {customer_name}! 👋" if customer_name != 'Cliente' else "Olá! 👋"

        body = (
            f"{greeting} Bem-vindo(a) à *{company_name}*! 🌿\n\n"
            f"Toque no botão abaixo para ver o que temos para você."
        )
        logger.info('[GreetingHandler] Saudação com botão Ver Opções para %s', customer_name)
        return HandlerResult.buttons(
            body=body,
            buttons=[
                {'id': 'show_options', 'title': '📋 Ver Opções'},
            ],
        )


class PriceCheckHandler(IntentHandler):
    """Handler para consulta de preços — delega ao LLM (tem ferramenta buscar_produto)."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        message = intent_data.get('original_message', '')
        normalized_message = self._normalize_lookup_text(message)
        if any(term in normalized_message for term in ('taxa', 'frete', 'entrega', 'delivery')):
            logger.info("[PriceCheckHandler] Respondendo taxa de entrega de forma determinística")
            return HandlerResult.text(self._build_delivery_info_text(message))

        logger.info("[PriceCheckHandler] Respondendo preço de produto de forma determinística")
        return self._legacy_handle(intent_data)

    def _legacy_handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        entities = intent_data.get('entities', {})
        product_name = entities.get('product_name')
        
        logger.info(f"Price check for: {product_name}")
        
        if not self.store:
            return HandlerResult.text("Desculpe, não encontrei informações da loja no momento. 😔")
        
        # Se mencionou produto específico
        if product_name:
            products = StoreProduct.objects.filter(
                store=self.store,
                name__icontains=product_name,
                is_active=True
            )[:5]
            
            if products:
                if len(products) == 1:
                    # Produto único - mostra detalhes
                    p = products[0]
                    response = (
                        f"💰 *{p.name}*\n"
                        f"Preço: *R$ {p.price}*\n\n"
                    )
                    if p.description:
                        response += f"{p.description}\n\n"
                    
                    # Botão para adicionar ao carrinho
                    return HandlerResult.buttons(
                        body=response,
                        buttons=[
                            {'id': f'add_{p.id}_1', 'title': '🛒 Adicionar'},
                            {'id': f'details_{p.id}', 'title': 'ℹ️ Detalhes'},
                            {'id': 'view_catalog', 'title': '📋 Ver mais'},
                        ]
                    )
                else:
                    # Múltiplos produtos - lista
                    response = f"💰 Encontrei esses produtos:\n\n"
                    for p in products:
                        response += f"• *{p.name}*: R$ {p.price}\n"
                    
                    response += "\nQual você quer?"
                    return HandlerResult.text(response)
            else:
                return HandlerResult.text(
                    f"Não encontrei '{product_name}'. 😕\n\n"
                    f"Quer ver nosso cardápio completo?"
                )
        
        # Retorna produtos populares
        products = StoreProduct.objects.filter(
            store=self.store,
            is_active=True
        ).order_by('-created_at')[:5]
        
        if products:
            response = f"💰 *Alguns dos nossos produtos:*\n\n"
            for p in products:
                response += f"• {p.name}: R$ {p.price}\n"
            
            response += f"\nQuer ver mais opções ou detalhes de algum?"
            return HandlerResult.text(response)
        
        return HandlerResult.text(
            "Nosso cardápio está sendo atualizado! 🔄\n"
            "Tente novamente em alguns minutos."
        )


class ProductMentionHandler(IntentHandler):
    """Handler quando usuário menciona produto — usa somente o catálogo real da loja."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[ProductMentionHandler] Respondendo via busca determinística")
        return self._legacy_handle(intent_data)

    def _legacy_handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        message = intent_data.get('original_message', '').strip()
        logger.info(f"[ProductMentionHandler] Mensagem: {message}")

        if not self.store:
            return HandlerResult.text("Cardápio não disponível. 😔")
        
        # Busca TODOS os produtos ativos
        all_products = StoreProduct.objects.filter(
            store=self.store,
            is_active=True
        )
        
        # Se digitou algo genérico como "rondelli", "lasanha", "nhoque"
        # Mostra TODOS desse tipo
        search_term = message.lower().strip()
        normalized_search = self._normalize_lookup_text(search_term)
        
        # Remove palavras comuns
        search_term = search_term.replace('de ', '').replace('com ', '').replace('e ', '')
        
        # Busca produtos que CONTÊM o termo (para pegar todos os tipos)
        matched_products = []
        for product in all_products:
            product_name_lower = product.name.lower()
            normalized_name = self._normalize_lookup_text(product.name)
            # Verifica se o termo está no nome do produto
            if (
                search_term in product_name_lower
                or normalized_search == normalized_name
                or (len(normalized_search) >= 5 and normalized_search in normalized_name)
                or (len(normalized_name) >= 5 and normalized_name in normalized_search)
            ):
                matched_products.append(product)
                logger.info(f"[ProductMentionHandler] Match: {product.name}")
        
        # Se encontrou produtos, mostra todos
        if matched_products:
            if len(matched_products) == 1:
                # Só um produto: salva na sessão e pergunta quantidade com botões.
                p = matched_products[0]
                try:
                    session_manager = self._get_session_manager()
                    session = session_manager.get_or_create_session()
                    session.update_context('pending_product_id', str(p.id))
                    session.update_context('pending_product_name', p.name)
                    session.update_context('pending_product_price', float(p.price))
                except Exception as exc:
                    logger.warning('[ProductMentionHandler] session context save failed: %s', exc)

                return HandlerResult.buttons(
                    body=(
                        f"🍽️ *{p.name}*\n"
                        f"💰 R$ {p.price}\n\n"
                        f"Quantas unidades você quer?"
                    ),
                    buttons=[
                        {'id': f'add_{p.id}_1', 'title': '1 unidade'},
                        {'id': f'add_{p.id}_2', 'title': '2 unidades'},
                        {'id': f'add_{p.id}_3', 'title': '3 unidades'},
                    ],
                    footer="Ou digite a quantidade desejada",
                )
            else:
                # Vários tipos - mostra todos
                product_list = "\n".join([f"{i+1}. {p.name} - R$ {p.price}" 
                                          for i, p in enumerate(matched_products[:10])])
                return HandlerResult.text(
                    f"🍝 *{search_term.title()}* - Temos esses:\n\n"
                    f"{product_list}\n\n"
                    f"Qual você quer? Digite o número ou o nome! 👇"
                )
        
        # Se não encontrou com o termo, tenta match parcial
        # Ex: "rondelli" deve pegar "Rondelli de Frango", "Rondelli de Presunto", etc
        keyword_products = []
        for product in all_products:
            product_words = product.name.lower().split()
            # Pega a primeira palavra do produto (ex: "Rondelli" de "Rondelli de Frango")
            if product_words:
                first_word = product_words[0]
                if search_term == first_word or first_word in search_term:
                    keyword_products.append(product)
        
        if keyword_products:
            product_list = "\n".join([f"{i+1}. {p.name} - R$ {p.price}" 
                                      for i, p in enumerate(keyword_products[:10])])
            return HandlerResult.text(
                f"🍝 *{search_term.title()}* - Temos esses:\n\n"
                f"{product_list}\n\n"
                f"Qual você quer? Digite o número ou o nome! 👇"
            )
        
        # Não encontrou - mostra todos os produtos disponíveis
        available = all_products[:10]
        if available:
            product_list = "\n".join([f"• {p.name} - R$ {p.price}" for p in available])
            return HandlerResult.text(
                f"Temos esses produtos:\n\n"
                f"{product_list}\n\n"
                f"Qual você quer?"
            )
        
        return HandlerResult.text(
            "Cardápio em atualização. Tente novamente em breve! 🔄"
        )


class MenuRequestHandler(IntentHandler):
    """Handler para solicitação de cardápio"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"[MenuRequestHandler] Store: {self.store}")
        
        if not self.store:
            logger.error("[MenuRequestHandler] Sem store!")
            return HandlerResult.text("Cardápio não disponível no momento. 😔")
        
        # Busca produtos ativos, excluindo ingredientes do SaladBuilder.
        # Ingredientes são marcados com tag "ingrediente" e só fazem sentido
        # no site (modal Monte sua Salada); no WhatsApp mostramos apenas
        # Saladas e Molhos para não poluir o template.
        all_products = StoreProduct.objects.filter(
            store=self.store,
            is_active=True
        ).exclude(tags__contains=['ingrediente']).select_related('category').order_by(
            'category__sort_order', 'category__name', 'name'
        )

        total_products = all_products.count()
        logger.info(f"[MenuRequestHandler] Total produtos ativos (excluindo ingredientes): {total_products}")
        
        if total_products == 0:
            logger.error("[MenuRequestHandler] Nenhum produto ativo encontrado!")
            return HandlerResult.text("Nenhum produto disponível no momento. 😔")
        
        # Tenta agrupar por categoria
        products_by_category = {}
        for product in all_products:
            cat_name = product.category.name if product.category else 'Outros'
            # Extrai nome curto da categoria (última parte)
            if ' - ' in cat_name:
                cat_name = cat_name.split(' - ')[-1]
            
            if cat_name not in products_by_category:
                products_by_category[cat_name] = []
            products_by_category[cat_name].append(product)
        
        logger.info(f"[MenuRequestHandler] Categorias: {list(products_by_category.keys())}")
        
        # Cria seções - máximo 10 linhas no total no WhatsApp list message.
        # Não limita mais 3 por categoria; usa o limite global para não esconder
        # produtos válidos de uma categoria pequena como Saladas.
        sections = []
        total_rows = 0
        max_rows = 10
        
        for cat_name, products in list(products_by_category.items())[:5]:
            if total_rows >= max_rows:
                break
            
            remaining_rows = max_rows - total_rows
            products_to_show = products[:remaining_rows]
            
            rows = [
                {
                    'id': f'product_{p.id}',
                    'title': p.name[:24],
                    'description': f'R$ {p.price}'
                }
                for p in products_to_show
            ]
            
            # Verifica limite
            if total_rows + len(rows) > max_rows:
                rows = rows[:max_rows - total_rows]
            
            if rows:
                section = {
                    'title': cat_name[:24],
                    'rows': rows
                }
                sections.append(section)
                total_rows += len(rows)
                logger.info(f"[MenuRequestHandler] Adicionada categoria '{cat_name}' com {len(rows)} produtos")
        
        # Se não conseguiu criar seções, mostra em formato texto
        if not sections:
            logger.warning("[MenuRequestHandler] Sem seções, usando fallback de texto")
            if all_products.count() > 0:
                products = all_products[:10]
                product_list = "\n".join([f"• {p.name} - R$ {p.price}" for p in products])
                return HandlerResult.text(
                    f"📋 *Cardápio - {self.store.name}*\n\n"
                    f"{product_list}\n\n"
                    f"Para pedir, digite quantos você quer!\n"
                    f"Ex: *2 rondelli de frango*"
                )
            else:
                return HandlerResult.text("Nenhum produto disponível no momento. 😔")
        
        # Envia lista interativa
        product_sections = []
        total_product_items = 0
        max_product_items = 30

        for cat_name, products in list(products_by_category.items())[:10]:
            if total_product_items >= max_product_items:
                break

            remaining_items = max_product_items - total_product_items
            product_items = [
                {'product_retailer_id': str(p.id)}
                for p in products[:remaining_items]
            ]
            if not product_items:
                continue

            product_sections.append({
                'title': cat_name[:24],
                'product_items': product_items,
            })
            total_product_items += len(product_items)

        if product_sections:
            logger.info(
                "[MenuRequestHandler] Enviando catálogo WhatsApp com %s seções e %s produtos",
                len(product_sections),
                total_product_items,
            )
            return HandlerResult.product_list(
                header=f"Cardápio - {self.store.name}",
                body="Escolha seus itens pelo catálogo abaixo.",
                footer="As imagens, preços e detalhes vêm do catálogo do WhatsApp.",
                sections=product_sections,
                fallback_sections=sections,
            )

        logger.info(f"[MenuRequestHandler] Enviando lista com {len(sections)} seções")
        return HandlerResult.list_message(
            body=f"📋 *Cardápio - {self.store.name}*\n\nEscolha uma opção:",
            button="Ver opções",
            sections=sections
        )


class BusinessHoursHandler(IntentHandler):
    """Handler para horário de funcionamento — delega ao LLM."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[BusinessHoursHandler] Respondendo horário de forma determinística")
        return self._legacy_handle(intent_data)

    def _legacy_handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if not self.store:
            return HandlerResult.text(
                "🕐 Nosso horário de atendimento:\n"
                "Segunda a Sábado: 10h às 20h\n"
                "Domingo: 11h às 18h"
            )
        
        from datetime import datetime
        
        # Pega horário de hoje
        today = datetime.now().strftime('%A').lower()
        
        # Mapeia dias da semana
        day_names = {
            'monday': 'Segunda', 'tuesday': 'Terça', 'wednesday': 'Quarta',
            'thursday': 'Quinta', 'friday': 'Sexta', 'saturday': 'Sábado', 'sunday': 'Domingo'
        }
        
        # Tenta pegar horário do banco
        try:
            hours = self.store.operating_hours or {}
            today_hours = hours.get(today, {})
            
            if today_hours:
                open_time = today_hours.get('open', '10:00')
                close_time = today_hours.get('close', '20:00')
                
                response = (
                    f"🕐 *Horário de hoje ({day_names.get(today, 'Hoje')}):*\n"
                    f"{open_time} às {close_time}\n\n"
                )
            else:
                response = "🕐 *Horário de hoje:* Fechado\n\n"
            
            # Adiciona horário completo
            response += "*Horário da semana:*\n"
            for day_code, day_name in day_names.items():
                day_hours = hours.get(day_code, {})
                if day_hours:
                    response += f"{day_name}: {day_hours.get('open', '--:--')} às {day_hours.get('close', '--:--')}\n"
                else:
                    response += f"{day_name}: Fechado\n"
            
            return HandlerResult.text(response)
            
        except Exception as e:
            logger.error(f"Error getting business hours: {e}")
            return HandlerResult.text(
                "🕐 Nosso horário de atendimento:\n"
                "Segunda a Sábado: 10h às 20h\n"
                "Domingo: 11h às 18h"
            )


class DeliveryInfoHandler(IntentHandler):
    """Handler para informações de entrega — delega ao LLM."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[DeliveryInfoHandler] Respondendo entrega de forma determinística")
        return HandlerResult.text(self._build_delivery_info_text(intent_data.get('original_message', '')))

    def _legacy_handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if not self.store:
            return HandlerResult.text(
                "🚚 *Informações de Entrega*\n\n"
                "• Tempo médio: 40-60 minutos\n"
                "• Taxa de entrega: a consultar\n"
                "• Área de cobertura: Consulte seu CEP\n\n"
                "Quer fazer um pedido?"
            )
        
        try:
            delivery_settings = self.store.delivery_settings or {}
            
            response = f"🚚 *{self.store.name} - Entrega*\n\n"
            
            # Tempo de entrega
            delivery_time = delivery_settings.get('delivery_time', '40-60')
            response += f"⏱️ Tempo médio: *{delivery_time} minutos*\n"
            
            # Taxa de entrega
            delivery_fee = delivery_settings.get('delivery_fee')
            if delivery_fee:
                response += f"💰 Taxa de entrega: *R$ {delivery_fee}*\n"
            else:
                response += f"💰 Taxa de entrega: *Consultar*\n"
            
            # Pedido mínimo
            min_order = delivery_settings.get('min_order')
            if min_order:
                response += f"📦 Pedido mínimo: *R$ {min_order}*\n"
            
            response += "\nQuer fazer um pedido?"
            
            return HandlerResult.buttons(
                body=response,
                buttons=[
                    {'id': 'start_order', 'title': '🛒 Fazer Pedido'},
                    {'id': 'check_cep', 'title': '📍 Consultar CEP'},
                    {'id': 'view_menu', 'title': '📋 Cardápio'},
                ]
            )
            
        except Exception as e:
            logger.error(f"Error getting delivery info: {e}")
            return HandlerResult.text(
                "🚚 *Informações de Entrega*\n\n"
                "• Tempo médio: 40-60 minutos\n"
                "• Taxa de entrega: a consultar\n\n"
                "Quer fazer um pedido?"
            )


class TrackOrderHandler(IntentHandler):
    """Handler para rastrear pedido"""

    def _build_phone_variants(self) -> list[str]:
        from apps.core.utils import normalize_phone_number

        raw_phone = self.conversation.phone_number or ''
        normalized = normalize_phone_number(raw_phone)
        digits_only = ''.join(filter(str.isdigit, raw_phone))
        variants = [raw_phone, normalized, digits_only]
        if normalized:
            variants.append(f'+{normalized}')
        return [value for value in dict.fromkeys(v for v in variants if v)]

    def _extract_order_number(self, intent_data: Dict[str, Any]) -> str:
        entities = intent_data.get('entities', {}) or {}
        order_number = (entities.get('order_number') or '').strip()
        if order_number:
            return order_number

        message = (intent_data.get('original_message') or '').strip()
        if not message:
            return ''

        patterns = [
            r'(?:pedido|ordem|order)\s*[#:-]?\s*([A-Za-z0-9][A-Za-z0-9\-_.]{2,})',
            r'#\s*([A-Za-z0-9][A-Za-z0-9\-_.]{2,})',
        ]
        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ''

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        order_number = self._extract_order_number(intent_data)

        logger.info(f"Track order: number={order_number}")

        if not self.store and not order_number:
            return HandlerResult.text(
                "Não encontrei pedidos recentes. 😕\n\n"
                "Quer fazer um pedido novo?"
            )

        phone_variants = self._build_phone_variants()

        order_qs = Order.objects.all()
        if self.store:
            order_qs = order_qs.filter(store=self.store)

        last_order = None

        if order_number:
            order_qs_by_number = order_qs.filter(order_number__iexact=order_number)
            if phone_variants:
                order_qs_by_number = order_qs_by_number.filter(customer_phone__in=phone_variants)
            last_order = order_qs_by_number.order_by('-created_at').first()

            if not last_order:
                last_order = order_qs.filter(order_number__iexact=order_number).order_by('-created_at').first()

        if not last_order and phone_variants:
            last_order = order_qs.filter(customer_phone__in=phone_variants).order_by('-created_at').first()

        if not last_order:
            try:
                session_manager = self._get_session_manager()
                session_data = session_manager.get_session_data()
                session_order_id = session_data.get('order_id')
                if session_order_id:
                    from uuid import UUID
                    try:
                        UUID(str(session_order_id))
                        last_order = order_qs.filter(id=session_order_id).first()
                    except (ValueError, TypeError):
                        last_order = order_qs.filter(order_number__iexact=str(session_order_id)).first()
            except Exception as exc:
                logger.warning('[TrackOrderHandler] Failed to inspect session order id: %s', exc)
        
        if last_order:
            status_map = {
                'pending': '⏳ Aguardando confirmação',
                'confirmed': '✅ Pedido confirmado',
                'preparing': '👨‍🍳 Em preparo',
                'ready': '✨ Pronto para retirada',
                'out_for_delivery': '🛵 Saiu para entrega',
                'delivered': '📦 Entregue',
                'cancelled': '❌ Cancelado',
            }
            
            status_display = status_map.get(last_order.status, f'Status: {last_order.status}')
            
            response = (
                f"📦 *Pedido #{last_order.order_number}*\n"
                f"{status_display}\n"
                f"Data: {last_order.created_at.strftime('%d/%m/%Y %H:%M')}\n"
                f"Total: R$ {last_order.total}"
            )
            
            # Se ainda está em andamento, mostra botão de acompanhamento
            if last_order.status in ['pending', 'confirmed', 'preparing', 'out_for_delivery']:
                return HandlerResult.buttons(
                    body=response,
                    buttons=[
                        {'id': f'track_{last_order.id}', 'title': '🔄 Atualizar'},
                        {'id': 'contact_support', 'title': '📞 Suporte'},
                    ]
                )
            
            return HandlerResult.text(response)
        
        return HandlerResult.text(
            "Não encontrei pedidos recentes. 😕\n\n"
            "Quer fazer um pedido novo?"
        )


class CreateOrderHandler(IntentHandler):
    """Handler para criar pedido - Extrai produtos da mensagem e cria pedido real"""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"[CreateOrderHandler] Iniciando handle")
        
        # Pega mensagem atual e histórico
        message_text = intent_data.get('original_message', '')
        logger.info(f"[CreateOrderHandler] Mensagem: {message_text}")
        
        # Tenta extrair produtos da mensagem atual ou do contexto
        items = self._extract_items_from_context(intent_data)
        
        if not items:
            # Se não achou itens, tenta extrair da mensagem atual
            items = self._parse_items_from_text(message_text)
        
        logger.info(f"[CreateOrderHandler] Itens extraídos: {items}")
        
        if items:
            # Cria pedido real
            return self._create_real_order(items, message_text)
        
        # Se não achou itens, inicia fluxo normal de pedido
        return self._start_order_flow()
    
    def _extract_items_from_context(self, intent_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Tenta extrair produtos do contexto da conversa"""
        items = []
        
        # Busca nas mensagens anteriores da conversa
        try:
            from apps.whatsapp.models import Message
            recent_messages = Message.objects.filter(
                conversation=self.conversation,
                direction='inbound',
                status='received'
            ).order_by('-created_at')[:5]
            
            for msg in recent_messages:
                parsed = self._parse_items_from_text(msg.body or '')
                if parsed:
                    items.extend(parsed)
                    break  # Usa só o primeiro que encontrar
                    
        except Exception as e:
            logger.warning(f"[CreateOrderHandler] Erro ao buscar contexto: {e}")
        
        return items
    
    def _create_real_order(self, items: List[Dict], message_text: str) -> HandlerResult:
        """Salva itens e pergunta método de entrega antes de criar o pedido."""
        logger.info(f"[CreateOrderHandler] Perguntando método de entrega para {self.conversation.phone_number}")
        return self._ask_delivery_method(items)
    
    def _start_order_flow(self) -> HandlerResult:
        """Inicia fluxo de pedido quando não achou itens"""
        session_manager = self._get_session_manager()
        
        session_manager.get_or_create_session()
        context = session_manager.get_context()
        context.start_order_flow()
        
        return HandlerResult.buttons(
            body=(
                f"🛒 *Vamos fazer seu pedido, {self.get_customer_name()}!*\n\n"
                f"Como prefere começar?"
            ),
            buttons=[
                {'id': 'order_catalog', 'title': '📋 Ver Cardápio'},
                {'id': 'order_quick', 'title': '⚡ Pedido Rápido'},
                {'id': 'order_help', 'title': '❓ Preciso de Ajuda'},
            ]
        )
    
    def _parse_items_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extrai itens do texto — busca dinâmica nos produtos da loja (sem keywords hardcoded)."""
        return _parse_items_from_text_dynamic(text, self.store)


class QuickOrderHandler(IntentHandler):
    """Handler para pedido rápido - cria pedido diretamente"""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"[QuickOrderHandler] Iniciando handle")

        # Extrai itens da mensagem original
        message_text = intent_data.get('original_message', '')
        logger.info(f"[QuickOrderHandler] Mensagem original: {message_text}")

        if not message_text:
            return HandlerResult.text(
                "🛒 *Pedido Rápido*\n\n"
                "Digite seu pedido:\n"
                "• 'Quero 2 rondelli de frango'\n"
                "• '1 lasanha e 1 nhoque'\n\n"
                "Ou digite 'cardápio' para ver opções."
            )

        # Extrai itens do texto
        items = self._parse_items_from_text(message_text)
        logger.info(f"[QuickOrderHandler] Itens extraídos: {items}")

        if not items:
            logger.warning(f"[QuickOrderHandler] Nenhum item encontrado na mensagem: {message_text}")
            return HandlerResult.text(
                "❌ Não consegui identificar os itens do seu pedido.\n\n"
                "Tente escrever de outra forma ou digite 'cardápio'."
            )

        logger.info(f"[QuickOrderHandler] {len(items)} itens extraídos, perguntando método de entrega")
        return self._ask_delivery_method(items)

    def _parse_items_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extrai itens do texto do usuário — busca dinâmica nos produtos da loja."""
        return _parse_items_from_text_dynamic(text, self.store)

    def _format_order_items(self, order) -> str:
        """Formata itens do pedido para exibição"""
        items_text = ""
        for item in order.items.all():
            items_text += f"• {item.quantity}x {item.product_name} = R$ {item.total}\n"
        return items_text


class PaymentStatusHandler(IntentHandler):
    """Handler para status de pagamento"""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        # Busca sessão ativa primeiro
        session_manager = self._get_session_manager()

        # Verifica se há sessão com pagamento pendente
        if session_manager.is_payment_pending():
            session_data = session_manager.get_session_data()
            pix_code = session_data.get('pix_code', '')

            if pix_code:
                return HandlerResult.buttons(
                    body=pix_code,
                    buttons=[
                        {'id': 'pix_copy', 'title': 'COPIAR CODIGO PIX'},
                        {'id': 'send_comprovante', 'title': '📤 Enviar Comprovante'},
                        {'id': 'cancel_order', 'title': '❌ Cancelar'},
                    ]
                )

        # Fallback: busca último pedido pendente no banco
        pending_order = Order.objects.filter(
            customer_phone=self.conversation.phone_number,
            **({"store": self.store} if self.store else {}),
            status='pending_payment'
        ).order_by('-created_at').first()

        if pending_order and pending_order.pix_code:
            # Atualiza sessão com dados do pedido
            session_manager.set_payment_pending(
                pix_code=pending_order.pix_code,
                payment_id=str(pending_order.id)
            )

            return HandlerResult.buttons(
                body=pending_order.pix_code,
                buttons=[
                    {'id': f'pix_copy_{pending_order.id}', 'title': 'COPIAR CODIGO PIX'},
                    {'id': 'send_comprovante', 'title': '📤 Enviar Comprovante'},
                    {'id': 'cancel_order', 'title': '❌ Cancelar'},
                ]
            )

        return HandlerResult.text(
            "Não encontrei pagamentos pendentes. ✅\n\n"
            "Quer fazer um pedido novo?"
        )


class LocationHandler(IntentHandler):
    """Handler para localização/endereço — delega ao LLM."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[LocationHandler] Respondendo localização de forma determinística")
        return HandlerResult.text(self._build_location_text())


class ContactHandler(IntentHandler):
    """Handler para contato — delega ao LLM."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[ContactHandler] Respondendo contato de forma determinística")
        return HandlerResult.text(self._build_contact_text())


class CancelOrderHandler(IntentHandler):
    """Handler para cancelar pedido em andamento"""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"Cancel order intent")

        session_manager = self._get_session_manager()

        # Verifica se há pedido para cancelar
        if session_manager.is_order_in_progress():
            session_manager.reset_session()
            return HandlerResult.text(
                "❌ *Pedido cancelado!*\n\n"
                "Seu carrinho foi esvaziado.\n\n"
                "Quer fazer um novo pedido? É só digitar *pedido* ou *cardápio*!"
            )

        return HandlerResult.text(
            "Não encontrei nenhum pedido em andamento para cancelar. ✅\n\n"
            "Quer fazer um pedido?"
        )


class HumanHandoffHandler(IntentHandler):
    """Handler para transferência para humano"""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"[HumanHandoffHandler] Human handoff requested by {self.get_customer_name()}")

        try:
            from apps.conversations.services.conversation_service import ConversationService
            ConversationService().switch_to_human(str(self.conversation.id))
            logger.info(f"[HumanHandoffHandler] Conversation {self.conversation.id} switched to human mode")
        except Exception as exc:
            logger.warning(f"[HumanHandoffHandler] switch_to_human failed: {exc}")

        return HandlerResult.text(
            f"👨‍💼 *Transferindo para atendimento humano...*\n\n"
            f"Um de nossos atendentes vai te atender em breve.\n"
            f"Por favor, aguarde um momento. 🙏"
        )


class FAQHandler(IntentHandler):
    """Handler para perguntas frequentes — delega ao LLM."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[FAQHandler] Delegando ao LLM")
        return HandlerResult.needs_llm()


class ViewQRCodeHandler(IntentHandler):
    """Handler para mostrar QR Code do PIX"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        session_manager = self._get_session_manager()
        session_data = session_manager.get_session_data()
        
        pix_code = session_data.get('pix_code', '')
        order_id = session_data.get('order_id', '')
        
        if not pix_code:
            return HandlerResult.text(
                "❌ Não encontrei um pagamento pendente.\n\n"
                "Quer fazer um pedido novo?"
            )
        
        # Busca o pedido para pegar o ticket_url
        try:
            from apps.stores.models import StoreOrder
            order = StoreOrder.objects.get(id=order_id)
            ticket_url = order.payment_url if hasattr(order, 'payment_url') else None
        except:
            ticket_url = None
        
        if ticket_url:
            return HandlerResult.text(
                f"📱 *QR Code do PIX*\n\n"
                f"Escaneie o QR Code no seu app bancário:\n\n"
                f"{ticket_url}\n\n"
                f"Ou use o código PIX abaixo 👇"
            )
        else:
            return HandlerResult.text(
                f"📱 *QR Code*\n\n"
                f"Use o código PIX que enviei antes:\n"
                f"`{pix_code[:50]}...`\n\n"
                f"Cole no seu app bancário!"
            )


class CopyPixHandler(IntentHandler):
    """Handler para copiar código PIX"""
    
    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        session_manager = self._get_session_manager()
        session_data = session_manager.get_session_data()
        
        pix_code = session_data.get('pix_code', '')
        
        if not pix_code:
            return HandlerResult.text(
                "❌ Não encontrei um pagamento pendente.\n\n"
                "Quer fazer um pedido novo?"
            )
        
        return HandlerResult.text(pix_code)


class ProductNotFoundHandler(IntentHandler):
    """Handler quando produto não é encontrado - evita alucinações da IA"""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if not self.store:
            return HandlerResult.text(
                "❌ Não encontrei esse produto.\n\n"
                "Digite *cardápio* para ver o que temos disponível! 📋"
            )

        # Busca produtos similares
        from apps.stores.models import StoreProduct
        products = StoreProduct.objects.filter(
            store=self.store,
            is_active=True
        )[:5]

        product_list = "\n".join([f"• {p.name} - R$ {p.price}" for p in products])

        return HandlerResult.text(
            f"❌ Não encontrei esse produto.\n\n"
            f"Temos disponíveis:\n{product_list}\n\n"
            f"Qual desses você quer? 😊"
        )


class UnknownHandler(IntentHandler):
    """Handler para intenções desconhecidas — tenta resolver número de quantidade
    (pedido na sequência de seleção de produto) antes de responder com fallback."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"Unknown intent detected")

        original_message = intent_data.get('original_message', '').strip()
        message = original_message.lower()

        # ── Mensagem de localização compartilhada via WhatsApp (tem prioridade) ──
        location_data = intent_data.get('location')
        if location_data and location_data.get('lat') and location_data.get('lng'):
            try:
                session_manager = self._get_session_manager()
                if session_manager.is_waiting_for_address():
                    logger.info(
                        "[UnknownHandler] Localização recebida: lat=%s lng=%s",
                        location_data['lat'], location_data['lng'],
                    )
                    return self._handle_location_input(
                        lat=float(location_data['lat']),
                        lng=float(location_data['lng']),
                        address_hint=location_data.get('address') or location_data.get('name') or '',
                    )
            except Exception as exc:
                logger.warning("[UnknownHandler] Erro ao processar localização: %s", exc)

        # ── Verifica estado de checkout pendente (endereço ou observações) ──
        try:
            session_manager = self._get_session_manager()
            if session_manager.is_waiting_for_address() and len(original_message) >= 5:
                logger.info("[UnknownHandler] Interceptando como endereço de entrega: %s", original_message[:60])
                return self._handle_address_input(original_message)
            if session_manager.is_waiting_for_notes():
                logger.info("[UnknownHandler] Interceptando como observação do pedido: %s", original_message[:60])
                return self._handle_notes_input(original_message)
        except Exception as exc:
            logger.warning("[UnknownHandler] Erro ao verificar estado da sessão: %s", exc)
        # ────────────────────────────────────────────────────────────────────

        # Se a mensagem é só um número, pode ser quantidade após seleção de produto
        if message.isdigit():
            qty = int(message)
            if 1 <= qty <= 20:
                result = self._try_pending_product_order(qty)
                if result:
                    return result

        # Mensagem não reconhecida como estado especial. Quando existe agente
        # ativo, deixa o pipeline consultar o LLM com o contexto real da loja.
        if intent_data.get('llm_available'):
            logger.info("[UnknownHandler] Mensagem desconhecida delegada ao LLM")
            return HandlerResult.needs_llm()

        # Sem agente ativo, mantém fallback determinístico para evitar inventar
        # item, preço, taxa ou estado de pedido.
        logger.info("[UnknownHandler] Mensagem não reconhecida — fallback determinístico")
        return HandlerResult.buttons(
            body="Não consegui identificar isso com segurança. Como quer continuar?",
            buttons=[
                {'id': 'view_menu', 'title': '📋 Cardápio'},
                {'id': 'contact_support', 'title': '👤 Atendente'},
            ],
        )

    def _try_pending_product_order(self, qty: int) -> Optional[HandlerResult]:
        """Se há produto pendente na sessão, cria pedido com a quantidade digitada."""
        try:
            session_manager = self._get_session_manager()
            session = session_manager.get_or_create_session()
            context_data = session.context or {}
            product_id = context_data.get('pending_product_id')
            if not product_id:
                return None

            from apps.stores.models import StoreProduct
            product = StoreProduct.objects.get(id=product_id, is_active=True)

            # Limpa produto pendente da sessão
            session.update_context('pending_product_id', None)
            session.update_context('pending_product_name', None)
            session.update_context('pending_product_price', None)

            return InteractiveReplyHandler(
                self.account, self.conversation, self.company_profile
            )._create_order_for_product(product, qty)
        except Exception as exc:
            logger.warning('[UnknownHandler] pending product order failed: %s', exc)
            return None


class InteractiveReplyHandler(IntentHandler):
    """
    Handles interactive replies from WhatsApp (button clicks / list selections).

    ID routing conventions:
      product_<uuid>          — user selected a product from a list menu
      add_<uuid>_<qty>        — user clicked an "add N units" button
      view_menu | view_catalog | order_catalog
                              — show the product catalog list
      start_order | order_quick
                              — start/fast order flow
      track_<order_id>        — track an existing order
      contact_support         — handoff to human agent
    """

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        reply_id = intent_data.get('reply_id', '')
        reply_title = intent_data.get('reply_title', '')

        logger.info('[InteractiveReplyHandler] reply_id=%s', reply_id)

        if reply_id.startswith('product_'):
            return self._handle_product_selection(reply_id, reply_title)

        if reply_id.startswith('add_'):
            return self._handle_add_to_cart(reply_id)

        if reply_id in ('view_menu', 'view_catalog', 'order_catalog'):
            return MenuRequestHandler(
                self.account, self.conversation, self.company_profile
            ).handle(intent_data)

        if reply_id in ('start_order', 'order_quick'):
            return CreateOrderHandler(
                self.account, self.conversation, self.company_profile
            ).handle(intent_data)

        if reply_id in ('order_delivery', 'order_pickup'):
            return self._handle_delivery_choice(reply_id)

        if reply_id in ('pay_pix', 'pay_card', 'pay_pickup'):
            return self._handle_payment_choice(reply_id)

        if reply_id.startswith('pix_copy'):
            return CopyPixHandler(
                self.account, self.conversation, self.company_profile
            ).handle(intent_data)

        if reply_id == 'send_comprovante':
            return HandlerResult.text(
                "📤 Para enviar o comprovante, tire uma foto ou screenshot do pagamento "
                "e envie aqui na conversa.\n\n"
                "Vamos verificar e confirmar seu pedido! ✅"
            )

        if reply_id == 'cancel_order':
            return CancelOrderHandler(
                self.account, self.conversation, self.company_profile
            ).handle(intent_data)

        if reply_id.startswith('track_'):
            return TrackOrderHandler(
                self.account, self.conversation, self.company_profile
            ).handle(intent_data)

        if reply_id == 'show_options':
            return HandlerResult.list_message(
                body="O que você gostaria de fazer? 😊",
                button="Ver Opções",
                sections=[{
                    'title': 'Escolha uma opção',
                    'rows': [
                        {'id': 'view_menu',      'title': '📋 Ver Cardápio',         'description': 'Veja nossos pratos e preços'},
                        {'id': 'montar_salada',  'title': '🥗 Montar Salada',        'description': 'Monte sua salada personalizada'},
                        {'id': 'contact_support','title': '👤 Falar com Atendente',  'description': 'Prefere falar com um humano?'},
                    ],
                }],
            )

        if reply_id == 'montar_salada':
            return MenuRequestHandler(
                self.account, self.conversation, self.company_profile
            ).handle(intent_data)

        if reply_id == 'contact_support':
            return HumanHandoffHandler(
                self.account, self.conversation, self.company_profile
            ).handle(intent_data)

        # Unknown ID — acknowledge and guide
        logger.warning('[InteractiveReplyHandler] Unhandled reply_id=%s', reply_id)
        return HandlerResult.buttons(
            body=f"Você selecionou: {reply_title or reply_id}\n\nComo posso ajudar?",
            buttons=[
                {'id': 'view_menu', 'title': '📋 Ver Cardápio'},
                {'id': 'start_order', 'title': '🛒 Fazer Pedido'},
            ],
        )

    def _handle_delivery_choice(self, reply_id: str) -> HandlerResult:
        """Usuário escolheu entrega ou retirada."""
        delivery_method = 'pickup' if reply_id == 'order_pickup' else 'delivery'

        try:
            session_manager = self._get_session_manager()
            items = session_manager.get_pending_order_items()
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao recuperar itens pendentes: %s', exc)
            items = []

        if not items:
            return HandlerResult.text(
                "❌ Não encontrei itens no seu pedido.\n\n"
                "Por favor, selecione os produtos novamente. Digite *cardápio* para ver as opções."
            )

        if delivery_method == 'delivery':
            # Precisa coletar endereço antes de perguntar pagamento
            try:
                session_manager.save_pending_delivery_method('delivery')
                session_manager.set_waiting_for_address(True)
            except Exception as exc:
                logger.warning('[InteractiveReplyHandler] Erro ao salvar estado de endereço: %s', exc)
            return HandlerResult.text(
                "📍 *Qual é o seu endereço de entrega?*\n\n"
                "Você pode:\n\n"
                "📌 *Compartilhar sua localização* — toque no clipe 📎 e escolha *Localização* (mais rápido e preciso!)\n\n"
                "✍️ *Ou digitar o endereço*, por exemplo:\n"
                "_Quadra 304 Sul, Alameda 2, Lote 5_\n"
                "_ARSE 72, Rua 4, Casa 3_"
            )

        # Retirada — mostra resumo do pedido e pede observações
        logger.info('[InteractiveReplyHandler] Pickup — mostrando resumo e pedindo observações')
        try:
            session_manager.save_pending_delivery_method('pickup')
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] Erro ao salvar pickup: %s', exc)
        return self._show_order_summary_and_ask_notes(delivery_method='pickup')

    def _handle_payment_choice(self, reply_id: str) -> HandlerResult:
        """Usuário escolheu o método de pagamento — recupera itens + delivery + endereço e cria o pedido."""
        payment_map = {
            'pay_pix': 'pix',
            'pay_card': 'card',
            'pay_pickup': 'cash',
        }
        payment_method = payment_map.get(reply_id, 'pix')

        try:
            session_manager = self._get_session_manager()
            session = session_manager.get_or_create_session()
            lock_key = f"whatsapp:checkout:{getattr(session, 'id', self.conversation.id)}"
            if not cache.add(lock_key, '1', timeout=240):
                return HandlerResult.text(
                    "Estou finalizando seu pedido e gerando o pagamento. "
                    "Pode levar alguns instantes, já te envio aqui."
                )
            items = session_manager.get_pending_order_items()
            delivery_method = session_manager.get_pending_delivery_method()
            addr_info = session_manager.get_delivery_address_info()
            customer_notes = session_manager.get_customer_notes()
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Erro ao recuperar dados pendentes: %s', exc)
            lock_key = None
            session_manager = None
            items = []
            delivery_method = 'delivery'
            addr_info = {}
            customer_notes = ''

        if not items:
            try:
                session_data = session_manager.get_session_data() if session_manager else {}
            except Exception:
                session_data = {}
            if lock_key:
                cache.delete(lock_key)
            if session_data.get('pix_code'):
                return HandlerResult.text(session_data['pix_code'])
            return HandlerResult.text(
                "❌ Não encontrei itens no seu pedido.\n\n"
                "Por favor, selecione os produtos novamente. Digite *cardápio* para ver as opções."
            )

        delivery_address = addr_info.get('address', '')
        delivery_fee_override = addr_info.get('fee')  # None se pickup ou se não calculou

        logger.info(
            '[InteractiveReplyHandler] Finalizando pedido: delivery=%s payment=%s fee=%s address=%s lat=%s lng=%s notes=%r',
            delivery_method, payment_method, delivery_fee_override,
            delivery_address[:40] if delivery_address else '',
            addr_info.get('lat'), addr_info.get('lng'),
            customer_notes[:40] if customer_notes else '',
        )
        result = self._finalize_order(
            items,
            delivery_method=delivery_method,
            payment_method=payment_method,
            delivery_address=delivery_address,
            customer_notes=customer_notes,
            delivery_fee_override=delivery_fee_override,
            addr_info=addr_info,
        )
        if not (
            result.response_text
            and result.response_text.startswith(('❌ Erro ao criar pedido', '❌ Loja'))
        ):
            try:
                session_manager.clear_pending_order_items()
            except Exception as exc:
                logger.warning('[InteractiveReplyHandler] Erro ao limpar itens pendentes: %s', exc)
        if lock_key:
            cache.delete(lock_key)
        return result

    def _handle_product_selection(self, reply_id: str, reply_title: str) -> HandlerResult:
        """User selected a product from the interactive list — ask for quantity."""
        product_uuid = reply_id[len('product_'):]

        try:
            product = StoreProduct.objects.get(id=product_uuid, is_active=True)
        except StoreProduct.DoesNotExist:
            logger.warning('[InteractiveReplyHandler] product_id not found: %s', product_uuid)
            return HandlerResult.text(
                "Produto não encontrado. 😕\n\nQuer ver o cardápio completo? Digite *cardápio*."
            )
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Error fetching product %s: %s', product_uuid, exc)
            return HandlerResult.text("Erro ao buscar produto. Tente novamente.")

        # Persist selected product in session so the next free-text reply can resolve it
        try:
            session_manager = self._get_session_manager()
            session = session_manager.get_or_create_session()
            session.update_context('pending_product_id', str(product.id))
            session.update_context('pending_product_name', product.name)
            session.update_context('pending_product_price', float(product.price))
        except Exception as exc:
            logger.warning('[InteractiveReplyHandler] session context save failed: %s', exc)

        return HandlerResult.buttons(
            body=(
                f"🍽️ *{product.name}*\n"
                f"💰 R$ {product.price}\n\n"
                f"Quantas unidades você quer?"
            ),
            buttons=[
                {'id': f'add_{product.id}_1', 'title': '1 unidade'},
                {'id': f'add_{product.id}_2', 'title': '2 unidades'},
                {'id': f'add_{product.id}_3', 'title': '3 unidades'},
            ],
            footer="Ou digite a quantidade desejada",
        )

    def _handle_add_to_cart(self, reply_id: str) -> HandlerResult:
        """User clicked an 'add N units' button: add_<product_uuid>_<qty>."""
        # Format: add_<uuid>_<qty>  — qty is the last segment, uuid may contain hyphens
        parts = reply_id.split('_')
        if len(parts) < 3:
            return HandlerResult.text("Erro ao processar pedido. Tente novamente.")

        try:
            quantity = int(parts[-1])
            # UUID sits between the first underscore and the last underscore
            product_id = '_'.join(parts[1:-1])
        except (ValueError, IndexError):
            return HandlerResult.text("Erro ao processar pedido. Tente novamente.")

        try:
            product = StoreProduct.objects.get(id=product_id, is_active=True)
        except StoreProduct.DoesNotExist:
            return HandlerResult.text("Produto não encontrado. 😕")
        except Exception as exc:
            logger.error('[InteractiveReplyHandler] Error fetching product %s: %s', product_id, exc)
            return HandlerResult.text("Erro ao buscar produto. Tente novamente.")

        return self._create_order_for_product(product, quantity)

    def _create_order_for_product(self, product, quantity: int) -> HandlerResult:
        """Salva item na sessão e pergunta método de entrega."""
        if not self.store:
            return HandlerResult.text("Loja não disponível no momento. 😔")

        items = [{'product_id': str(product.id), 'quantity': quantity}]
        return self._ask_delivery_method(items)


# ===== MAPEAMENTO DE HANDLERS =====
HANDLER_MAP = {
    IntentType.GREETING: GreetingHandler,
    IntentType.PRICE_CHECK: PriceCheckHandler,
    IntentType.PRODUCT_MENTION: ProductMentionHandler,
    IntentType.MENU_REQUEST: MenuRequestHandler,
    IntentType.BUSINESS_HOURS: BusinessHoursHandler,
    IntentType.DELIVERY_INFO: DeliveryInfoHandler,
    IntentType.TRACK_ORDER: TrackOrderHandler,
    IntentType.PAYMENT_STATUS: PaymentStatusHandler,
    IntentType.VIEW_QR_CODE: ViewQRCodeHandler,
    IntentType.COPY_PIX: CopyPixHandler,
    IntentType.LOCATION: LocationHandler,
    IntentType.CONTACT: ContactHandler,
    IntentType.CREATE_ORDER: CreateOrderHandler,
    IntentType.ADD_TO_CART: QuickOrderHandler,
    IntentType.CANCEL_ORDER: CancelOrderHandler,
    IntentType.HUMAN_HANDOFF: HumanHandoffHandler,
    IntentType.FAQ: FAQHandler,
    IntentType.UNKNOWN: UnknownHandler,
}


def get_handler(intent_type: IntentType, account, conversation) -> Optional[IntentHandler]:
    """Retorna o handler apropriado para a intenção"""
    handler_class = HANDLER_MAP.get(intent_type)
    if handler_class:
        return handler_class(account, conversation)
    return None
