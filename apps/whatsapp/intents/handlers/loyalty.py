import logging
from typing import Any, Dict

from apps.stores.models import StoreOrder
from apps.stores.services.loyalty_service import LoyaltyService

from .base import HandlerResult, IntentHandler

logger = logging.getLogger(__name__)


class LoyaltyStatusHandler(IntentHandler):
    """Responde saldo do cartão fidelidade dentro da janela (custo zero)."""

    def _resolve_user(self):
        phone = getattr(self.conversation, 'phone_number', None)
        if not phone or not self.store:
            return None
        order = (StoreOrder.objects
                 .filter(store=self.store, customer_phone=phone, customer__isnull=False)
                 .order_by('-created_at').first())
        return order.customer if order else None

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[LoyaltyStatusHandler] Respondendo saldo de fidelidade")
        user = self._resolve_user()
        status = LoyaltyService.get_status(self.store, user) if (user and self.store) else None
        if not status or not status.get('enabled'):
            text = ('Nosso cartão fidelidade conta seus pedidos pagos no site! '
                    'Peça pelo cardápio para começar a juntar. 🥗')
        elif status['available_rewards'] > 0:
            text = (f"🎉 Você tem {status['available_rewards']} salada(s) grátis para resgatar! "
                    f"É só marcar o resgate no checkout do site.")
        else:
            text = (f"🥗 Cartão fidelidade: {status['progress']}/{status['threshold']} — "
                    f"faltam {status['remaining']} para a próxima grátis!")
        return HandlerResult.text(text)
