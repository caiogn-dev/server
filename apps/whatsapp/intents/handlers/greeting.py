import logging
from typing import Any, Dict

from .base import HandlerResult, IntentHandler

logger = logging.getLogger(__name__)


class GreetingHandler(IntentHandler):
    """Handler para saudações — retorna boas-vindas com atalhos diretos."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        # Se o cliente já tem sessão com pedido/pagamento em andamento,
        # não reinicia com boas-vindas completas — apenas responde brevemente
        # e mostra o estado atual para evitar perda de contexto.
        try:
            session_manager = self._get_session_manager()
            session = session_manager.get_or_create_session()
            if session:
                from apps.automation.models import CustomerSession
                active_with_context = {
                    CustomerSession.SessionStatus.CART_CREATED,
                    CustomerSession.SessionStatus.CHECKOUT,
                    CustomerSession.SessionStatus.PAYMENT_PENDING,
                    CustomerSession.SessionStatus.PAYMENT_CONFIRMED,
                    CustomerSession.SessionStatus.ORDER_PLACED,
                    CustomerSession.SessionStatus.COMPLETED,
                }
                if session.status in active_with_context:
                    customer_name = self.get_customer_name()
                    first_name = customer_name.split()[0] if customer_name and customer_name != 'Cliente' else ''
                    hi = f"Oi, {first_name}! 😊" if first_name else "Oi! 😊"

                    if session.status in (
                        CustomerSession.SessionStatus.PAYMENT_PENDING,
                        CustomerSession.SessionStatus.PAYMENT_CONFIRMED,
                        CustomerSession.SessionStatus.ORDER_PLACED,
                        CustomerSession.SessionStatus.COMPLETED,
                    ):
                        return HandlerResult.text(
                            f"{hi} Seu pedido está sendo processado. "
                            "Pode acompanhar aqui ou falar com a gente se precisar de ajuda."
                        )

                    if session.status in (
                        CustomerSession.SessionStatus.CART_CREATED,
                        CustomerSession.SessionStatus.CHECKOUT,
                    ):
                        return HandlerResult.buttons(
                            body=f"{hi} Você tem itens no carrinho. Quer continuar seu pedido?",
                            buttons=[
                                {'id': 'continue_checkout', 'title': '✅ Continuar pedido'},
                                {'id': 'view_menu', 'title': '📋 Ver Cardápio'},
                                {'id': 'contact_support', 'title': '👤 Atendente'},
                            ],
                        )
        except Exception as exc:
            logger.warning('[GreetingHandler] Erro ao checar sessão: %s', exc)

        # Sem sessão ativa — boas-vindas completas para cliente novo
        company_name = (
            getattr(self.company, 'company_name', None)
            or (self.store.name if self.store else None)
            or 'nossa loja'
        )
        customer_name = self.get_customer_name()
        greeting = f"Olá, {customer_name}! 👋" if customer_name != 'Cliente' else "Olá! 👋"
        body = (
            f"{greeting} Bem-vindo(a) à *{company_name}*! 🌿\n\n"
            f"O que posso fazer por você?"
        )
        logger.info('[GreetingHandler] Saudação com botões diretos para %s', customer_name)
        return HandlerResult.buttons(
            body=body,
            buttons=[
                {'id': 'view_menu', 'title': '📋 Ver Cardápio'},
                {'id': 'montar_salada', 'title': '🥗 Montar Salada'},
                {'id': 'contact_support', 'title': '👤 Atendente'},
            ],
        )
