import logging
from typing import Any, Dict

from apps.stores.models.order import StoreOrder as Order

from .base import HandlerResult, IntentHandler

logger = logging.getLogger(__name__)


class PaymentStatusHandler(IntentHandler):
    """Handler para status de pagamento."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        session_manager = self._get_session_manager()
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
                    ],
                )
        pending_order = Order.objects.filter(
            customer_phone=self.conversation.phone_number,
            **({"store": self.store} if self.store else {}),
            payment_status='pending',
            pix_code__gt='',
        ).order_by('-created_at').first()
        if pending_order and pending_order.pix_code:
            session_manager.set_payment_pending(
                pix_code=pending_order.pix_code,
                payment_id=str(pending_order.id),
            )
            return HandlerResult.buttons(
                body=pending_order.pix_code,
                buttons=[
                    {'id': f'pix_copy_{pending_order.id}', 'title': 'COPIAR CODIGO PIX'},
                    {'id': 'send_comprovante', 'title': '📤 Enviar Comprovante'},
                    {'id': 'cancel_order', 'title': '❌ Cancelar'},
                ],
            )
        return HandlerResult.text("Não encontrei pagamentos pendentes. ✅\n\nQuer fazer um pedido novo?")


class ViewQRCodeHandler(IntentHandler):
    """Handler para mostrar QR Code do PIX."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        session_manager = self._get_session_manager()
        session_data = session_manager.get_session_data()
        pix_code = session_data.get('pix_code', '')
        order_id = session_data.get('order_id', '')
        if not pix_code:
            return HandlerResult.text("❌ Não encontrei um pagamento pendente.\n\nQuer fazer um pedido novo?")
        try:
            from apps.stores.models import StoreOrder
            order = StoreOrder.objects.get(id=order_id)
            ticket_url = order.payment_url if hasattr(order, 'payment_url') else None
        except Exception:
            ticket_url = None
        if ticket_url:
            return HandlerResult.text(
                f"📱 *QR Code do PIX*\n\n"
                f"Escaneie o QR Code no seu app bancário:\n\n"
                f"{ticket_url}\n\n"
                f"Ou use o código PIX abaixo 👇"
            )
        return HandlerResult.text(
            f"📱 *QR Code*\n\n"
            f"Use o código PIX que enviei antes:\n"
            f"`{pix_code[:50]}...`\n\n"
            f"Cole no seu app bancário!"
        )


class CopyPixHandler(IntentHandler):
    """Handler para copiar código PIX."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        session_manager = self._get_session_manager()
        session_data = session_manager.get_session_data()
        pix_code = session_data.get('pix_code', '')
        if not pix_code:
            return HandlerResult.text("❌ Não encontrei um pagamento pendente.\n\nQuer fazer um pedido novo?")
        return HandlerResult.text(pix_code)
