import logging
from typing import Any, Dict

from .base import HandlerResult, IntentHandler

logger = logging.getLogger(__name__)


class GreetingHandler(IntentHandler):
    """Handler para saudações — retorna boas-vindas com atalhos diretos."""

    @staticmethod
    def _session_order_is_active(session) -> bool:
        """True apenas se o pedido vinculado à sessão ainda está em andamento.

        Sessão terminal reutilizada (24h) não pode dizer "sendo processado"
        depois do pedido entregue/cancelado.
        """
        from apps.stores.models import StoreOrder
        finished = {
            StoreOrder.OrderStatus.DELIVERED,
            StoreOrder.OrderStatus.COMPLETED,
            StoreOrder.OrderStatus.CANCELLED,
            StoreOrder.OrderStatus.REFUNDED,
            StoreOrder.OrderStatus.FAILED,
        }
        try:
            order = session.order
        except Exception:
            order = None
        if order is not None:
            return order.status not in finished
        # Sem pedido vinculado: só PAYMENT_PENDING justifica "em processamento"
        from apps.automation.models import CustomerSession
        return session.status == CustomerSession.SessionStatus.PAYMENT_PENDING

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        order_enabled = self._bot_order_enabled()
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
                        if self._session_order_is_active(session):
                            return HandlerResult.text(
                                f"{hi} Seu pedido está sendo processado. "
                                "Pode acompanhar aqui ou falar com a gente se precisar de ajuda."
                            )
                        # Pedido já entregue/cancelado (ou sessão concluída sem
                        # pedido ativo) — segue para boas-vindas normais.

                    if order_enabled and session.status in (
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

        # Sem sessão ativa — boas-vindas completas para cliente novo/retornante
        company_name = (
            getattr(self.company, 'company_name', None)
            or (self.store.name if self.store else None)
            or 'nossa loja'
        )
        customer_name = self.get_customer_name()
        greeting = f"Olá, {customer_name}! 👋" if customer_name != 'Cliente' else "Olá! 👋"

        # Verifica se tem pedido recente (últimos 7 dias) para oferecer repetição
        recent_order = None
        if self.store and order_enabled:
            try:
                from django.utils import timezone
                from datetime import timedelta
                from apps.stores.models import StoreOrder
                cutoff = timezone.now() - timedelta(days=7)
                phone = self.conversation.phone_number
                recent_order = StoreOrder.objects.filter(
                    store=self.store,
                    customer_phone__endswith=phone[-8:],
                    status__in=[
                        StoreOrder.OrderStatus.DELIVERED,
                        StoreOrder.OrderStatus.PICKED_UP,
                        StoreOrder.OrderStatus.CONFIRMED,
                        StoreOrder.OrderStatus.PAID,
                    ],
                    created_at__gte=cutoff,
                ).order_by('-created_at').first()
            except Exception as exc:
                logger.warning('[GreetingHandler] Erro ao buscar pedido recente: %s', exc)

        if recent_order:
            body = (
                f"{greeting} Que bom te ver por aqui! 😊\n\n"
                f"Quer repetir seu último pedido (*#{recent_order.order_number}*)?"
            )
            logger.info('[GreetingHandler] Cliente retornante com pedido recente #%s', recent_order.order_number)
            return HandlerResult.buttons(
                body=body,
                buttons=[
                    {'id': 'repeat_order', 'title': '🔁 Repetir Pedido'},
                    {'id': 'view_menu', 'title': '📋 Ver Cardápio'},
                    {'id': 'contact_support', 'title': '👤 Atendente'},
                ],
            )

        body = (
            f"{greeting} Bem-vindo(a) à *{company_name}*! 🌿\n\n"
            f"O que posso fazer por você?"
        )
        logger.info('[GreetingHandler] Saudação com botões diretos para %s', customer_name)
        buttons = [{'id': 'view_menu', 'title': '📋 Ver Cardápio'}]
        cta = self._order_cta_button()
        if cta:
            buttons.append(cta)
        buttons.append({'id': 'contact_support', 'title': '👤 Atendente'})
        return HandlerResult.buttons(body=body, buttons=buttons)
