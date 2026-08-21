import logging
import re
from typing import Any, Dict, List, Optional

from django.utils import timezone

from apps.stores.models.order import StoreOrder as Order

from .base import HandlerResult, IntentHandler, _parse_items_from_text_dynamic

logger = logging.getLogger(__name__)


class TrackOrderHandler(IntentHandler):
    """Handler para rastrear pedido."""

    def _build_phone_variants(self) -> list:
        """Variantes do telefone da conversa — SSOT em core.utils.phone_variants.

        Antes só gerava as formas COM o nono dígito. O `wa_id` do WhatsApp vem
        SEM ele, e o pedido feito no site grava COM: a busca nunca casava e o
        bot respondia "Não encontrei pedidos recentes" sobre o pedido que ele
        mesmo tinha acabado de confirmar (CE-2608062713, 06/ago).
        """
        from apps.core.utils import phone_variants
        return phone_variants(self.conversation.phone_number or '')

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

    def _order_id_from_reply(self, intent_data: Dict[str, Any]) -> str:
        """UUID embutido no botão `track_<uuid>`.

        O botão "🔄 Atualizar" carrega o id exato do pedido, mas o handler só
        olhava o texto do botão ("🔄 Atualizar") e o número extraído da
        mensagem — jogava fora a resposta que já tinha em mãos e caía na busca
        por telefone, que falhava pelo nono dígito.
        """
        entities = intent_data.get('entities', {}) or {}
        reply_id = str(
            entities.get('reply_id')
            or intent_data.get('reply_id')
            or (intent_data.get('interactive_reply') or {}).get('id')
            or ''
        )
        if reply_id.startswith('track_'):
            return reply_id[len('track_'):].strip()
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
        # O id do botão é a fonte mais confiável: aponta para UM pedido.
        reply_order_id = self._order_id_from_reply(intent_data)
        if reply_order_id:
            from uuid import UUID
            try:
                UUID(reply_order_id)
                last_order = order_qs.filter(id=reply_order_id).first()
            except (ValueError, TypeError):
                last_order = None
        if not last_order and order_number:
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
                # localtime: created_at é UTC; sem converter o card dizia
                # "14:18" para um pedido feito às 11:18 de Brasília.
                f"Data: {timezone.localtime(last_order.created_at).strftime('%d/%m/%Y %H:%M')}\n"
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
        return self._show_catalog()

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
        logger.info("[CreateOrderHandler] Perguntando método de entrega (conversa=%s)", self.conversation.id)
        return self._ask_delivery_method(items)

    def _show_catalog(self) -> HandlerResult:
        # Fluxo enxuto (29/jul): sem itens na mensagem → catálogo direto.
        # O passo "Como prefere começar?" (Cardápio/Pedido Rápido/Ajuda) era
        # loop puro — todos os caminhos terminavam no catálogo mesmo.
        session_manager = self._get_session_manager()
        session_manager.get_or_create_session()
        context = session_manager.get_context()
        context.start_order_flow()
        from .catalog import MenuRequestHandler
        return MenuRequestHandler(self.account, self.conversation, self.company_profile).handle({})

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
            cancelled_number = self._cancel_linked_unpaid_order(session_manager)
            session_manager.reset_session()
            order_line = f"O pedido #{cancelled_number} foi cancelado e " if cancelled_number else ""
            return HandlerResult.text(
                "❌ *Pedido cancelado!*\n\n"
                f"{order_line}seu carrinho foi esvaziado.\n\n"
                "Quer fazer um novo pedido? É só digitar *pedido* ou *cardápio*!"
            )
        return HandlerResult.text(
            "Não encontrei nenhum pedido em andamento para cancelar. ✅\n\n"
            "Quer fazer um pedido?"
        )

    @staticmethod
    def _cancel_linked_unpaid_order(session_manager) -> str:
        """Cancela o StoreOrder vinculado à sessão SE ainda não foi pago.

        Antes só a sessão era resetada — o pedido ficava 'pending' no painel
        para sempre. Pedido pago NUNCA é cancelado por aqui.
        """
        try:
            from apps.stores.models import StoreOrder
            session = session_manager.get_or_create_session()
            order = getattr(session, 'order', None)
            if not order:
                return ''
            if (
                order.status == StoreOrder.OrderStatus.PENDING
                and order.payment_status == StoreOrder.PaymentStatus.PENDING
            ):
                order.status = StoreOrder.OrderStatus.CANCELLED
                order.save(update_fields=['status', 'updated_at'])
                logger.info(
                    "[CancelOrderHandler] StoreOrder %s cancelado pelo cliente",
                    order.order_number,
                )
                return str(order.order_number)
        except Exception as exc:
            logger.warning("[CancelOrderHandler] Erro ao cancelar StoreOrder: %s", exc)
        return ''
