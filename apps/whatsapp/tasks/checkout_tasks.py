"""Finalização assíncrona de pedido do bot WhatsApp.

O clique em PIX/Cartão responde na hora ("pedido recebido, gerando pagamento")
e a parte lenta (criar pedido + Mercado Pago) roda aqui. Antes era síncrono no
processamento da mensagem: ~90s de espera e falha de envio silenciosa.
"""
import logging
import time

from celery import shared_task

logger = logging.getLogger(__name__)


def _send_handler_result(account, phone_number: str, result) -> None:
    """Entrega um HandlerResult direto pelo MessageService (fora do dispatcher)."""
    from apps.whatsapp.services.message_service import MessageService

    svc = MessageService()
    data = result.interactive_data or {}
    if result.interactive_type == 'buttons' and data.get('buttons'):
        svc.send_interactive_buttons(
            account_id=str(account.id),
            to=phone_number,
            body_text=data.get('body') or '',
            buttons=data['buttons'],
            header=data.get('header'),
            footer=data.get('footer'),
        )
        return
    if result.response_text and result.response_text not in (
        'BUTTONS_SENT', 'LIST_SENT', 'PRODUCT_LIST_SENT',
    ):
        svc.send_text_message(
            account_id=str(account.id),
            to=phone_number,
            text=result.response_text,
        )


@shared_task(bind=True, max_retries=1, default_retry_delay=10, queue='whatsapp')
def finalize_whatsapp_order_task(
    self,
    account_id: str,
    conversation_id: str,
    profile_id: str,
    payment_method: str,
    lock_key: str = None,
):
    """Cria o pedido, gera o pagamento (PIX/link cartão) e envia o resultado."""
    from django.core.cache import cache

    from apps.automation.models import CompanyProfile
    from apps.conversations.models import Conversation
    from apps.whatsapp.intents.handlers.base import HandlerResult
    from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
    from apps.whatsapp.models import WhatsAppAccount

    started = time.monotonic()
    account = WhatsAppAccount.objects.get(pk=account_id)
    conversation = Conversation.objects.get(pk=conversation_id)
    profile = CompanyProfile.objects.filter(pk=profile_id).first()
    handler = InteractiveReplyHandler(account, conversation, profile)

    try:
        session_manager = handler._get_session_manager()
        items = session_manager.get_pending_order_items()
        delivery_method = session_manager.get_pending_delivery_method()
        addr_info = session_manager.get_delivery_address_info()
        customer_notes = session_manager.get_customer_notes()

        if not items:
            result = HandlerResult.text(
                "❌ Não encontrei itens no seu pedido.\n\n"
                "Por favor, selecione os produtos novamente. Digite *cardápio* para ver as opções."
            )
        else:
            result = handler._finalize_order(
                items,
                delivery_method=delivery_method,
                payment_method=payment_method,
                delivery_address=addr_info.get('address', ''),
                customer_notes=customer_notes,
                delivery_fee_override=addr_info.get('fee'),
                addr_info=addr_info,
            )
            if not (result.response_text or '').startswith(('❌ Erro ao criar pedido', '❌ Loja')):
                try:
                    session_manager.clear_pending_order_items()
                except Exception as exc:
                    logger.warning('[finalize_task] Erro ao limpar itens pendentes: %s', exc)
    except Exception as exc:
        logger.exception('[finalize_task] Finalização falhou (tentativa %s)', self.request.retries)
        if lock_key:
            cache.delete(lock_key)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        result = HandlerResult.text(
            "❌ Não conseguimos gerar seu pagamento agora.\n\n"
            "Digite *pix* para tentar novamente ou fale com um atendente. 🙏"
        )
    finally:
        if lock_key:
            cache.delete(lock_key)

    try:
        _send_handler_result(account, conversation.phone_number, result)
    except Exception:
        logger.exception('[finalize_task] FALHA AO ENVIAR resposta do pedido — cliente sem retorno!')
        raise

    logger.info(
        '[finalize_task] Pedido finalizado e resposta enviada em %.1fs (payment=%s)',
        time.monotonic() - started, payment_method,
    )
