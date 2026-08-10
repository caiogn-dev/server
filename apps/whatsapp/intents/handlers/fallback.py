import logging
from typing import Any, Dict, Optional

from .base import HandlerResult, IntentHandler

logger = logging.getLogger(__name__)


class HumanHandoffHandler(IntentHandler):
    """Handler para transferência para humano."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"[HumanHandoffHandler] Human handoff requested by {self.get_customer_name()}")
        try:
            from apps.conversations.services.conversation_service import ConversationService
            ConversationService().switch_to_human(str(self.conversation.id))
            logger.info(f"[HumanHandoffHandler] Conversation {self.conversation.id} switched to human mode")
        except Exception as exc:
            logger.warning(f"[HumanHandoffHandler] switch_to_human failed: {exc}")
        try:
            session_manager = self._get_session_manager()
            session_manager.set_waiting_for_address(False)
            session_manager.set_waiting_for_notes(False)
        except Exception as exc:
            logger.warning("[HumanHandoffHandler] Failed to clear session state: %s", exc)
        return HandlerResult.text(
            f"👨‍💼 *Transferindo para atendimento humano...*\n\n"
            f"Um de nossos atendentes vai te atender em breve.\n"
            f"Por favor, aguarde um momento. 🙏"
        )


class AffirmativeHandler(IntentHandler):
    """
    Handler para mensagens afirmativas ("Sim", "Ok", "Pode ser") sem contexto de botão.
    Interpreta a resposta com base no estado atual da sessão para evitar cair no LLM
    e causar busca de produto com o texto literal da confirmação.
    """

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info('[AffirmativeHandler] Afirmativo recebido — verificando contexto de sessão')
        try:
            session_manager = self._get_session_manager()

            # Esperando observações → "Sim" = sem observações, prosseguir
            if session_manager.is_waiting_for_notes():
                logger.info('[AffirmativeHandler] Sessão waiting_for_notes — tratando como sem obs.')
                return self._handle_notes_input('')

            # Esperando endereço → "Sim" ambíguo, pedir endereço de novo
            if session_manager.is_waiting_for_address():
                return HandlerResult.text(
                    "📍 Por favor, me informe seu endereço de entrega ou compartilhe sua localização. 🙏"
                )

            session = session_manager.get_or_create_session()
            if session:
                from apps.automation.models import CustomerSession
                if session.status == CustomerSession.SessionStatus.PAYMENT_PENDING:
                    from .payment import PaymentStatusHandler
                    return PaymentStatusHandler(
                        self.account, self.conversation, self.company_profile
                    ).handle(intent_data)

                if session.status in (
                    CustomerSession.SessionStatus.CART_CREATED,
                    CustomerSession.SessionStatus.CHECKOUT,
                ):
                    # "Sim" com carrinho aberto significa CONTINUAR — mandar o
                    # catálogo é a ação. Devolver a pergunta "quer continuar ou
                    # ver o cardápio?" era exatamente o botão que o cliente
                    # tinha acabado de apertar: o loop de 09/ago.
                    from .catalog import MenuRequestHandler
                    return MenuRequestHandler(
                        self.account, self.conversation, self.company_profile
                    ).handle(intent_data)
        except Exception as exc:
            logger.warning('[AffirmativeHandler] Erro ao verificar sessão: %s', exc)

        # Sem contexto claro — só as duas saídas reais: catálogo ou humano
        return HandlerResult.buttons(
            body="Claro! O que você gostaria de fazer? 😊",
            buttons=[
                {'id': 'view_menu', 'title': '📋 Cardápio'},
                {'id': 'contact_support', 'title': '👤 Atendente'},
            ],
        )


class UnknownHandler(IntentHandler):
    """Handler para intenções desconhecidas."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"Unknown intent detected")
        original_message = intent_data.get('original_message', '').strip()
        message = original_message.lower()

        # Mensagem de localização compartilhada via WhatsApp (tem prioridade)
        location_data = intent_data.get('location')
        if location_data and location_data.get('lat') and location_data.get('lng'):
            try:
                session_manager = self._get_session_manager()
                logger.info(
                    "[UnknownHandler] Localização recebida: lat=%s lng=%s",
                    location_data['lat'], location_data['lng'],
                )
                session_manager.set_waiting_for_address(True)
                return self._handle_location_input(
                    lat=float(location_data['lat']),
                    lng=float(location_data['lng']),
                    address_hint=location_data.get('address') or location_data.get('name') or '',
                )
            except Exception as exc:
                logger.warning("[UnknownHandler] Erro ao processar localização: %s", exc)

        # Verifica estado de checkout pendente (endereço ou observações)
        try:
            session_manager = self._get_session_manager()
            if session_manager.is_waiting_for_address() and len(original_message) >= 5:
                if intent_data.get('llm_available'):
                    logger.info("[UnknownHandler] Delegando address-waiting ao LLM: %s", original_message[:60])
                    return HandlerResult.needs_llm()
                logger.info("[UnknownHandler] Interceptando como endereço de entrega: %s", original_message[:60])
                return self._handle_address_input(original_message)
            if session_manager.is_waiting_for_notes():
                logger.info("[UnknownHandler] Interceptando como observação do pedido: %s", original_message[:60])
                return self._handle_notes_input(original_message)
        except Exception as exc:
            logger.warning("[UnknownHandler] Erro ao verificar estado da sessão: %s", exc)

        # Se a mensagem é só um número, pode ser quantidade após seleção de produto
        if message.isdigit():
            qty = int(message)
            if 1 <= qty <= 20:
                result = self._try_pending_product_order(qty)
                if result:
                    return result

        if intent_data.get('llm_available'):
            logger.info("[UnknownHandler] Mensagem desconhecida delegada ao LLM")
            return HandlerResult.needs_llm()

        # Sem "não consegui identificar": 1ª vez oferece atalhos úteis; se o
        # cliente seguir mandando coisas que não entendemos dentro do cooldown,
        # o bot fica QUIETO (provavelmente é conversa pra atendente, não spam).
        try:
            if not self._get_session_manager().should_send_unknown_helper():
                logger.info("[UnknownHandler] Unknown repetido dentro do cooldown — silêncio")
                return HandlerResult.silent()
        except Exception as exc:
            logger.warning("[UnknownHandler] Erro no cooldown de unknown: %s", exc)
        logger.info("[UnknownHandler] Mensagem não reconhecida — enviando atalhos")
        return HandlerResult.buttons(
            body="Como posso te ajudar? 👇",
            buttons=[
                {'id': 'view_menu', 'title': '📋 Cardápio'},
                {'id': 'contact_support', 'title': '👤 Atendente'},
            ],
        )

    def _try_pending_product_order(self, qty: int) -> Optional[HandlerResult]:
        try:
            session_manager = self._get_session_manager()
            session = session_manager.get_or_create_session()
            context_data = session.context or {}
            product_id = context_data.get('pending_product_id')
            if not product_id:
                return None
            from apps.stores.models import StoreProduct
            product = StoreProduct.objects.get(id=product_id, is_active=True)
            session.update_context('pending_product_id', None)
            session.update_context('pending_product_name', None)
            session.update_context('pending_product_price', None)
            # Lazy import to avoid circular dependency: fallback.py → interactive.py
            from .interactive import InteractiveReplyHandler
            return InteractiveReplyHandler(
                self.account, self.conversation, self.company_profile
            )._create_order_for_product(product, qty)
        except Exception as exc:
            logger.warning('[UnknownHandler] pending product order failed: %s', exc)
            return None
