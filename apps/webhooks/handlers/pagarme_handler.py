"""Webhook do Pagar.me para cobranças de voucher.

REGRA DURA: o corpo recebido não é fonte da verdade. Ele é só um aviso de que
algo mudou; quem decide é `GET /orders/{id}` com a chave da loja. Duas vezes o
Cardapidex perdeu ou inventou dinheiro por confiar no corpo — o 200 sem
processar de 31/ago e o backfill que duplicou receita.
"""
import logging

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.stores.models import StoreOrder, StorePayment
from apps.stores.services import pagarme_orders

from .base import BaseHandler

logger = logging.getLogger(__name__)

EVENTOS_TRATADOS = {
    'order.paid', 'order.payment_failed', 'charge.paid',
    'charge.payment_failed', 'charge.refunded',
}


def _momento_do_pagamento(corpo: dict):
    """Hora em que o dinheiro entrou, segundo o Pagar.me — não a hora em que
    o NOSSO servidor processou o webhook. Sem isso, `paid_at` reflete quando a
    entrega/reentrega chegou aqui, e o caixa mentiria sobre quando pagou.

    Cai para `timezone.now()` quando o corpo não traz nada utilizável — nunca
    inventa um parse que não sabemos que existe de verdade na API.
    """
    charges = (corpo or {}).get('charges') or []
    primeira = charges[0] if charges else {}
    bruto = (
        primeira.get('paid_at')
        or (primeira.get('last_transaction') or {}).get('created_at')
    )
    if bruto:
        parsed = parse_datetime(str(bruto))
        if parsed is not None:
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.utc)
            return parsed
    return timezone.now()


class PagarmeHandler(BaseHandler):
    def handle(self, event, payload: dict, headers: dict) -> dict:
        tipo = str((payload or {}).get('type') or '')
        if tipo not in EVENTOS_TRATADOS:
            logger.info('Webhook Pagar.me ignorado: type=%s', tipo)
            return {'ignored': True, 'reason': f'evento não tratado: {tipo}'}

        dados = (payload or {}).get('data') or {}
        external_id = str(dados.get('id') or '')
        # charge.* traz o id da CHARGE; order.* traz o id da ORDER. Gravamos o
        # id da order, então aceitamos os dois caminhos de busca.
        order_id = str((dados.get('order') or {}).get('id') or '') or external_id

        pagamento = (
            StorePayment.objects
            .filter(external_id__in=[e for e in (external_id, order_id) if e],
                    payment_method=StorePayment.PaymentMethod.VOUCHER)
            .select_related('order', 'gateway', 'store')
            .first()
        )
        if pagamento is None:
            # Não criar nada: cobrança órfã virou receita fantasma antes.
            logger.warning('Webhook Pagar.me sem StorePayment: id=%s', external_id)
            return {'ignored': True, 'reason': 'cobrança desconhecida'}

        gateway = pagamento.gateway
        if gateway is None or not gateway.api_key:
            logger.error('Webhook Pagar.me sem credencial da loja: pagamento=%s', pagamento.pk)
            return {'ignored': True, 'reason': 'gateway sem credencial'}

        status_code, corpo = pagarme_orders.consultar_order(gateway.api_key, order_id)
        ok, status, _, motivo = pagarme_orders.interpret(status_code, corpo)

        if status == 'pending':
            return {'ok': True, 'status': 'pending'}

        if ok and status == 'approved':
            if pagamento.status != StorePayment.PaymentStatus.COMPLETED:
                pagamento.status = StorePayment.PaymentStatus.COMPLETED
                pagamento.paid_at = _momento_do_pagamento(corpo)
                pagamento.gateway_response = corpo or {}
                pagamento.save()
            pedido = pagamento.order
            if pedido and pedido.payment_status != StoreOrder.PaymentStatus.PAID:
                pedido.payment_status = StoreOrder.PaymentStatus.PAID
                pedido.save(update_fields=['payment_status', 'updated_at'])
            return {'ok': True, 'status': 'approved'}

        if status == 'refunded':
            # Dinheiro que ENTROU e foi devolvido não é o mesmo que nunca ter
            # sido autorizado — não mexe em `paid_at`: quando o dinheiro
            # chegou continua sendo verdade depois do estorno.
            if pagamento.status != StorePayment.PaymentStatus.REFUNDED:
                pagamento.status = StorePayment.PaymentStatus.REFUNDED
                pagamento.gateway_response = corpo or {}
                pagamento.save()
            return {'ok': True, 'status': 'refunded'}

        if pagamento.status != StorePayment.PaymentStatus.FAILED:
            pagamento.status = StorePayment.PaymentStatus.FAILED
            pagamento.error_message = pagarme_orders.mensagem_de_recusa(motivo)
            pagamento.gateway_response = corpo or {}
            pagamento.save()
        return {'ok': True, 'status': 'failed'}
