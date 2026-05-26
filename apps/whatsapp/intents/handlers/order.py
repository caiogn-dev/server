import logging
import re
from typing import Any, Dict, List, Optional

from apps.stores.models.order import StoreOrder as Order

from .base import HandlerResult, IntentHandler, _parse_items_from_text_dynamic

logger = logging.getLogger(__name__)


class TrackOrderHandler(IntentHandler):
    """Handler para rastrear pedido."""

    def _build_phone_variants(self) -> list:
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
            return HandlerResult.text("Não encontrei pedidos recentes. 😕\n\nQuer fazer um pedido novo?")
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
            if last_order.status in ['pending', 'confirmed', 'preparing', 'out_for_delivery']:
                return HandlerResult.buttons(
                    body=response,
                    buttons=[
                        {'id': f'track_{last_order.id}', 'title': '🔄 Atualizar'},
                        {'id': 'contact_support', 'title': '📞 Suporte'},
                    ],
                )
            return HandlerResult.text(response)
        return HandlerResult.text("Não encontrei pedidos recentes. 😕\n\nQuer fazer um pedido novo?")


class CreateOrderHandler(IntentHandler):
    """Handler para criar pedido — extrai produtos da mensagem e inicia fluxo de pedido real."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"[CreateOrderHandler] Iniciando handle")
        message_text = intent_data.get('original_message', '')
        items = self._extract_items_from_context(intent_data)
        if not items:
            items = self._parse_items_from_text(message_text)
        logger.info(f"[CreateOrderHandler] Itens extraídos: {items}")
        if items:
            return self._create_real_order(items, message_text)
        return self._start_order_flow()

    def _extract_items_from_context(self, intent_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = []
        try:
            from apps.whatsapp.models import Message
            recent_messages = Message.objects.filter(
                conversation=self.conversation,
                direction='inbound',
                status='received',
            ).order_by('-created_at')[:5]
            for msg in recent_messages:
                parsed = self._parse_items_from_text(msg.body or '')
                if parsed:
                    items.extend(parsed)
                    break
        except Exception as e:
            logger.warning(f"[CreateOrderHandler] Erro ao buscar contexto: {e}")
        return items

    def _create_real_order(self, items: List[Dict], message_text: str) -> HandlerResult:
        logger.info(f"[CreateOrderHandler] Perguntando método de entrega para {self.conversation.phone_number}")
        return self._ask_delivery_method(items)

    def _start_order_flow(self) -> HandlerResult:
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
            ],
        )

    def _parse_items_from_text(self, text: str) -> List[Dict[str, Any]]:
        return _parse_items_from_text_dynamic(text, self.store)


class QuickOrderHandler(IntentHandler):
    """Handler para pedido rápido — cria pedido diretamente a partir do texto livre."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"[QuickOrderHandler] Iniciando handle")
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
        return _parse_items_from_text_dynamic(text, self.store)


class CancelOrderHandler(IntentHandler):
    """Handler para cancelar pedido em andamento."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"Cancel order intent")
        session_manager = self._get_session_manager()
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
