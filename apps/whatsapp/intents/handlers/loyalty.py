import logging
from typing import Any, Dict

from apps.stores.models import StoreOrder
from apps.stores.services.checkout_service import CheckoutService

from .base import HandlerResult, IntentHandler

logger = logging.getLogger(__name__)


class LoyaltyStatusHandler(IntentHandler):
    """Responde saldo do cartão fidelidade dentro da janela (custo zero)."""

    def _build_phone_variants(self) -> list:
        from apps.core.utils import normalize_phone_number
        raw_phone = self.conversation.phone_number or ''
        normalized = normalize_phone_number(raw_phone)
        digits_only = ''.join(filter(str.isdigit, raw_phone))
        variants = [raw_phone, normalized, digits_only]
        if normalized:
            variants.append(f'+{normalized}')
        return [value for value in dict.fromkeys(v for v in variants if v)]

    def _resolve_user(self):
        if not self.store:
            return None
        phone_variants = self._build_phone_variants()
        if not phone_variants:
            return None
        order = (StoreOrder.objects
                 .filter(store=self.store, customer_phone__in=phone_variants, customer__isnull=False)
                 .order_by('-created_at').first())
        return order.customer if order else None

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[LoyaltyStatusHandler] Respondendo saldo de fidelidade")
        user = self._resolve_user()
        status = CheckoutService.get_loyalty_status(self.store, user) if (user and self.store) else None
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
