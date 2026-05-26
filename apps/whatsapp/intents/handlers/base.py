"""
Base classes for WhatsApp intent handlers: HandlerResult + IntentHandler.
Also contains shared module-level helpers for product text parsing.
"""
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

from apps.stores.models import StoreProduct
from apps.stores.services.delivery_quote_service import delivery_quote_service

logger = logging.getLogger(__name__)


# ─── Shared helpers: dynamic item extraction ──────────────────────────────────

def _normalize_text(s: str) -> str:
    """Remove accents and lowercase for fuzzy product matching."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s.lower())
        if unicodedata.category(c) != 'Mn'
    )


def _parse_items_from_text_dynamic(text: str, store) -> List[Dict[str, Any]]:
    """
    Extrai pares (product_id, quantity) de um texto livre.

    1. Regex extrai pares (quantity, search_term) do texto.
    2. Para cada par, busca o produto da loja que melhor corresponde:
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

    products = list(StoreProduct.objects.filter(store=store, is_active=True).exclude(tags__contains=['ingrediente']))
    if not products:
        return []

    normalized_products = [
        (p, _normalize_text(p.name), p.name.lower().split())
        for p in products
    ]

    def _match(search_term: str) -> Optional[Any]:
        norm_search = _normalize_text(search_term)
        best = None
        for product, norm_name, words in normalized_products:
            if norm_search in norm_name or norm_name in norm_search:
                return product
            if words and len(words[0]) > 2 and words[0] in search_term:
                best = best or product
            for word in search_term.split():
                if len(word) > 3 and word in norm_name:
                    best = best or product
        return best

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

    if not items:
        product = _match(text_lower)
        if product:
            items.append({'product_id': str(product.id), 'quantity': 1})

    logger.info('[_parse_items_from_text_dynamic] store=%s text=%r items=%d',
                getattr(store, 'slug', store), text[:60], len(items))
    return items


# ─── HandlerResult ─────────────────────────────────────────────────────────────

class HandlerResult:
    """Resultado do processamento de um handler."""

    def __init__(
        self,
        response_text: Optional[str] = None,
        use_interactive: bool = False,
        interactive_type: Optional[str] = None,
        interactive_data: Optional[Dict] = None,
        requires_llm: bool = False,
    ):
        self.response_text = response_text
        self.use_interactive = use_interactive
        self.interactive_type = interactive_type
        self.interactive_data = interactive_data or {}
        self.requires_llm = requires_llm

    @classmethod
    def text(cls, text: str) -> 'HandlerResult':
        return cls(response_text=text)

    @classmethod
    def buttons(cls, body: str, buttons: list, header: Optional[str] = None,
                footer: Optional[str] = None) -> 'HandlerResult':
        return cls(
            response_text="BUTTONS_SENT",
            use_interactive=True,
            interactive_type='buttons',
            interactive_data={'body': body, 'buttons': buttons, 'header': header, 'footer': footer},
        )

    @classmethod
    def list_message(cls, body: str, button: str, sections: list) -> 'HandlerResult':
        return cls(
            response_text="LIST_SENT",
            use_interactive=True,
            interactive_type='list',
            interactive_data={'body': body, 'button': button, 'sections': sections},
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
            },
        )

    @classmethod
    def needs_llm(cls) -> 'HandlerResult':
        return cls(requires_llm=True)

    @classmethod
    def none(cls) -> 'HandlerResult':
        return cls()


# ─── IntentHandler base ────────────────────────────────────────────────────────

class IntentHandler:
    """Handler base para intenções."""

    def __init__(self, account, conversation, company_profile=None):
        self.account = account
        self.conversation = conversation
        self.company_profile = company_profile or getattr(account, 'company_profile', None)
        self._whatsapp_service = None
        self.store = self._get_store()

    @property
    def whatsapp_service(self):
        if self._whatsapp_service is None:
            from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService
            self._whatsapp_service = WhatsAppAPIService(self.account)
        return self._whatsapp_service

    @property
    def company(self):
        return self.company_profile

    def _get_session_manager(self):
        from apps.automation.services import get_session_manager
        context_owner = self.company_profile or self.store or self.account
        return get_session_manager(context_owner, self.conversation.phone_number)

    def _get_store(self):
        if self.company_profile and hasattr(self.company_profile, 'store'):
            return self.company_profile.store
        return None

    def _normalize_lookup_text(self, value: str) -> str:
        if not value:
            return ""
        normalized = unicodedata.normalize('NFD', str(value).lower())
        return ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Mn')

    def _match_fixed_delivery_zone_from_text(self, message: str) -> Optional[Dict[str, Any]]:
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
            self.whatsapp_service.send_text_message(to=self.conversation.phone_number, text=msg1)
        except Exception as exc:
            logger.warning("[_send_pix_confirmation] Erro ao enviar msg1: %s", exc)
        return HandlerResult.buttons(
            body=pix_code,
            buttons=[{'id': 'pix_copy', 'title': 'COPIAR CODIGO PIX'}],
        )

    def _handle_address_input(self, address_text: str) -> 'HandlerResult':
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
        fee_result = delivery_quote_service.normalize(
            delivery_quote_service.calculate_for_payload(
                self.store,
                {
                    'method': 'delivery',
                    'address': {
                        'raw_address': formatted_address,
                        'lat': lat,
                        'lng': lng,
                        **(address_components or {}),
                    },
                },
            )
        )
        if not fee_result.get('is_valid', fee_result.get('is_within_area', True)):
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
        try:
            pending = session_manager.get_pending_order_items()
        except Exception:
            pending = []
        if not pending:
            dist_text = f" ({distance_km:.1f} km)" if distance_km else ""
            time_text = f" (~{int(duration_minutes)} min)" if duration_minutes else ""
            fee_fmt = f"R$ {fee:.2f}".replace('.', ',') if fee > 0 else "Grátis 🎉"
            session_manager.set_waiting_for_notes(False)
            return HandlerResult.buttons(
                body=(
                    f"✅ *Entregamos aí!*\n\n"
                    f"📍 {formatted_address}\n"
                    f"🛵 Taxa de entrega{dist_text}{time_text}: *{fee_fmt}*\n\n"
                    f"Escolha um item no cardápio para montar seu pedido 👇"
                ),
                buttons=[{'id': 'view_menu', 'title': '📋 Ver Cardápio'}],
            )
        return self._show_order_summary_and_ask_notes(
            delivery_method='delivery',
            delivery_address=formatted_address,
            delivery_fee=float(fee),
            distance_km=distance_km,
            duration_minutes=duration_minutes,
        )

    def _ask_delivery_method(self, items: List[Dict[str, Any]]) -> 'HandlerResult':
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
            buttons = [{'id': 'order_delivery', 'title': '🛵 Entrega'}]
        return HandlerResult.buttons(body="📦 *Como prefere receber seu pedido?*", buttons=buttons)

    def _ask_payment_method(self, delivery_method: str) -> 'HandlerResult':
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
        return HandlerResult.buttons(body="💳 *Como prefere pagar?*", buttons=buttons)

    def _show_order_summary_and_ask_notes(
        self,
        delivery_method: str,
        delivery_address: str = '',
        delivery_fee: float = 0.0,
        distance_km: float = None,
        duration_minutes: float = None,
    ) -> 'HandlerResult':
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
        return HandlerResult.buttons(body=f"{note_line}💳 *Como prefere pagar?*", buttons=buttons)

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
        from apps.whatsapp.services import create_order_from_whatsapp
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
            if 'Erros de estoque' in error or 'fora de estoque' in error.lower() or 'estoque insuficiente' in error.lower():
                return HandlerResult.text(
                    "⚠️ *Um ou mais itens do seu pedido estão indisponíveis no momento.*\n\n"
                    "Por favor, revise seu pedido ou fale com um atendente para verificar o cardápio atualizado. 🙏"
                )
            return HandlerResult.text(
                "❌ Não conseguimos finalizar seu pedido agora.\n\nTente novamente em instantes ou fale com um atendente."
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
        return HandlerResult.text(
            f"✅ *Pedido #{order.order_number} confirmado!*\n\n"
            f"💰 *Total: R$ {float(order.total):.2f}*\n\n"
            f"💵 Pagamento na retirada — nos vemos em breve! 🏪"
        )

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        raise NotImplementedError

    def get_customer_name(self) -> str:
        return self.conversation.contact_name or 'Cliente'
