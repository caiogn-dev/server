"""
Mercado Pago webhook handler.
"""
import hashlib
import hmac
import logging
import os
from typing import Dict, Any
from django.http import HttpResponse

from .base import BaseHandler
from ..models import WebhookEvent

logger = logging.getLogger(__name__)


def verify_mercadopago_signature_with_secret(request, payload: dict, secret: str) -> bool:
    """
    Mesma validação de assinatura do MP, porém com a chave passada por parâmetro.

    Existe para as lojas: cada `StorePaymentGateway` pode ter o seu próprio
    `webhook_secret`, mas o ESQUEMA assinado é idêntico ao da plataforma. Antes
    havia uma segunda implementação em apps/stores/api/webhooks.py que assinava o
    corpo cru — coisa que o MP não faz — e rejeitava 100% dos webhooks da loja.
    Uma implementação só, dois chamadores.
    """
    return _check_signature(request, payload, secret)


def _verify_mercadopago_signature(request, payload: dict) -> bool:
    """
    Validate Mercado Pago webhook HMAC-SHA256 signature.

    MP sends:
      x-signature: ts=<timestamp>,v1=<hmac>
      x-request-id: <uuid>

    Signed template: "id:<data.id>;request-id:<X-Request-Id>;ts:<ts>"
    Ref: https://www.mercadopago.com.br/developers/en/docs/your-integrations/notifications/webhooks
    """
    secret = os.environ.get('MERCADO_PAGO_WEBHOOK_SECRET', '')
    if not secret:
        # Sem secret: em produção REJEITA (fail-closed) — aceitar abriria forja
        # de webhook de pagamento (marcar pedido como pago sem pagar). Em DEBUG
        # libera para testes locais. (Em prod o secret está setado, então isto
        # é só rede de segurança contra deploy mal configurado.)
        from django.conf import settings
        if not settings.DEBUG:
            logger.warning("MERCADO_PAGO_WEBHOOK_SECRET ausente em produção — rejeitando webhook")
            return False
        return True  # DEBUG: skip validation para testes locais

    return _check_signature(request, payload, secret)


def _check_signature(request, payload: dict, secret: str) -> bool:
    """Verificação HMAC propriamente dita. `secret` já resolvido pelo chamador."""
    x_signature = request.headers.get('x-signature', '')
    x_request_id = request.headers.get('x-request-id', '')

    if not x_signature:
        logger.warning("Mercado Pago webhook missing x-signature header")
        return False

    # Parse ts and v1 from "ts=<ts>,v1=<hmac>"
    ts = ''
    v1 = ''
    for part in x_signature.split(','):
        part = part.strip()
        if part.startswith('ts='):
            ts = part[3:]
        elif part.startswith('v1='):
            v1 = part[3:]

    if not ts or not v1:
        logger.warning("Mercado Pago x-signature malformed: %s", x_signature)
        return False

    # O `data.id` que o MP assina vem da QUERY STRING (?data.id=...), não do
    # corpo. Nos webhooks de subscription_preapproval o corpo pode vir vazio, o
    # que zerava o data_id e quebrava o HMAC (bug do 401). Preferimos a query e
    # caímos pro corpo como fallback. MP normaliza id alfanumérico p/ minúsculas.
    qp = getattr(request, 'query_params', None)
    if qp is None:
        qp = getattr(request, 'GET', {})
    query_id = (qp.get('data.id') or '').strip()
    body_id = str((payload or {}).get('data', {}).get('id') or '').strip()

    # Candidatos de manifesto: a doc do MP varia quanto ao ';' final entre
    # versões e o id pode vir da query ou do corpo. Todos exigem o secret, então
    # aceitar qualquer variante NÃO enfraquece a segurança (atacante sem o secret
    # não forja nenhuma). Se nenhuma bater, é secret errado — logamos p/ diagnóstico.
    ids = []
    for did in (query_id, query_id.lower(), body_id, body_id.lower()):
        if did and did not in ids:
            ids.append(did)
    ids = ids or ['']

    candidates = []
    for did in ids:
        base = f"id:{did};request-id:{x_request_id};ts:{ts}"
        candidates.append(base + ";")
        candidates.append(base)

    for template in candidates:
        expected = hmac.new(
            secret.encode('utf-8'),
            template.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(v1, expected):
            return True

    # Nenhum candidato bateu: log diagnóstico (sem secret nem hashes completos)
    # pra identificar, no próximo webhook real, se é formato ou secret.
    logger.warning(
        "Mercado Pago webhook HMAC mismatch — rejecting "
        "(query_id=%r body_id=%r x_request_id=%r ts=%r v1_pre=%s)",
        query_id, body_id, x_request_id, ts, (v1 or '')[:8],
    )
    return False


class MercadoPagoHandler(BaseHandler):
    """
    Handler for Mercado Pago payment webhooks.
    """
    
    def handle(self, event: WebhookEvent, payload: dict, headers: dict) -> Dict[str, Any]:
        """
        Process Mercado Pago webhook.
        Delegates to the existing store webhook service.
        """
        # Signature already validated by the dispatcher (_verify_signature).
        # _verify_mercadopago_signature is called there via WebhookEndpoint secret.
        # Extract data from payload
        event_type = payload.get('type', '')
        data_id = payload.get('data', {}).get('id')
        
        logger.info(f"Processing Mercado Pago webhook: {event_type}, data_id={data_id}")
        
        # Process based on event type
        if event_type.startswith('payment'):
            result = self._handle_payment_webhook(payload)
        elif event_type.startswith('merchant_order'):
            result = self._handle_order_webhook(payload)
        elif event_type.startswith('subscription') or 'preapproval' in event_type:
            result = self._handle_preapproval_webhook(data_id)
        else:
            result = {'processed': False, 'reason': 'unknown_event_type'}

        return result

    def _handle_preapproval_webhook(self, preapproval_id) -> Dict[str, Any]:
        """Assinatura SaaS (preapproval): busca status no MP e atualiza StoreSubscription."""
        if not preapproval_id:
            return {'processed': False, 'reason': 'no_preapproval_id'}
        try:
            from apps.stores.services import subscription_service
            # Mesma seleção de token da criação (prefere SANDBOX_TOKEN se setado).
            # Usar settings.MERCADO_PAGO_ACCESS_TOKEN direto quebra a paridade em
            # sandbox: a assinatura é criada com o token sandbox (conta do test
            # user) e o GET do webhook com o token prod (outra conta) → 400.
            sdk = subscription_service._sdk()
            resp = sdk.preapproval().get(str(preapproval_id))
            mp_status = (resp.get('response') or {}).get('status', '')
            return subscription_service.apply_preapproval_event(str(preapproval_id), mp_status)
        except Exception as e:
            logger.error(f"Erro no webhook de preapproval {preapproval_id}: {e}")
            return {'processed': False, 'reason': 'preapproval_error'}
    
    def _handle_payment_webhook(self, payload: dict) -> Dict[str, Any]:
        """Handle payment-related webhooks."""
        from django.db import DatabaseError
        from apps.stores.models import StoreOrder
        from apps.stores.services.checkout_service import CheckoutService, checkout_service

        # Pagamento da PLATAFORMA (adesão SaaS) com external_reference inline.
        # Alguns payloads do MP já trazem external_reference/status; quando trazem
        # e começam com 'setup:', desvia direto sem custo de fetch.
        ext_ref = str(payload.get('external_reference')
                      or payload.get('data', {}).get('external_reference') or '')
        if ext_ref.startswith('setup:'):
            from apps.stores.services import subscription_service
            mp_status = (payload.get('status')
                         or payload.get('data', {}).get('status') or '')
            return subscription_service.mark_setup_fee_paid(ext_ref, mp_status)

        data_id = payload.get('data', {}).get('id')
        if not data_id:
            return {'processed': False, 'error': 'Missing data.id'}

        payment_id = str(data_id)
        payment_status = (
            payload.get('status')
            or payload.get('data', {}).get('status')
            or payload.get('action')
        )

        if payment_status in {'payment.created', 'payment.updated'}:
            payment_status = None

        if not payment_status:
            try:
                order = StoreOrder.objects.filter(payment_id=payment_id).select_related('store').first()
            except DatabaseError as exc:
                logger.error("Mercado Pago webhook order lookup failed: %s", exc)
                return {
                    'processed': False,
                    'payment_id': payment_id,
                    'reason': 'order_lookup_failed',
                }
            if not order:
                # Sem pedido de loja com esse payment_id: o webhook cru do MP só
                # traz data.id (sem external_reference), então pode ser o pagamento
                # da adesão SaaS na conta da PLATAFORMA. Busca no token da plataforma
                # pra descobrir external_reference/status antes de desistir.
                setup_result = self._try_platform_setup_payment(payment_id)
                if setup_result is not None:
                    return setup_result
                return {
                    'processed': False,
                    'payment_id': payment_id,
                    'reason': 'order_not_found',
                }

            try:
                import mercadopago
            except ImportError:
                return {
                    'processed': False,
                    'payment_id': payment_id,
                    'reason': 'mercadopago_sdk_unavailable',
                }

            credentials = checkout_service.get_payment_credentials(order.store)
            if not credentials:
                return {
                    'processed': False,
                    'payment_id': payment_id,
                    'order_id': str(order.id),
                    'reason': 'payment_credentials_not_found',
                }

            sdk = mercadopago.SDK(credentials['access_token'])
            response = sdk.payment().get(payment_id)
            if response.get('status') != 200:
                return {
                    'processed': False,
                    'payment_id': payment_id,
                    'order_id': str(order.id),
                    'reason': 'payment_fetch_failed',
                    'status_code': response.get('status'),
                }
            payment_status = response.get('response', {}).get('status')

        order = CheckoutService.process_payment_webhook(payment_id, payment_status)

        return {
            'processed': bool(order),
            'payment_id': payment_id,
            'order_id': str(order.id) if order else None,
            'order_number': order.order_number if order else '',
            'payment_status': payment_status,
            'action': 'payment_updated',
        }
    
    def _try_platform_setup_payment(self, payment_id: str):
        """
        Verifica se um payment sem pedido de loja é, na verdade, o pagamento da
        adesão SaaS (preference da PLATAFORMA). Busca o payment no token da
        plataforma (mesma fonte que criou a preference) e, se o external_reference
        começar com 'setup:', marca a setup_fee_paid.

        Retorna o dict de resultado quando É um pagamento de adesão; retorna None
        quando não é (aí o chamador segue o fluxo normal de 'order_not_found').
        """
        try:
            from apps.stores.services import subscription_service
            sdk = subscription_service._sdk()
            response = sdk.payment().get(str(payment_id))
        except Exception as exc:
            logger.warning("Falha ao buscar payment %s no token da plataforma: %s", payment_id, exc)
            return None
        if response.get('status') != 200:
            return None
        body = response.get('response') or {}
        ext = str(body.get('external_reference') or '')
        if not ext.startswith('setup:'):
            return None
        return subscription_service.mark_setup_fee_paid(ext, body.get('status') or '')

    def _handle_order_webhook(self, payload: dict) -> Dict[str, Any]:
        """Handle order-related webhooks."""
        data_id = payload.get('data', {}).get('id')
        
        return {
            'processed': True,
            'order_id': data_id,
            'action': 'merchant_order_updated'
        }
    
    def handle_verification(self, request) -> HttpResponse:
        """Mercado Pago doesn't use challenge-response."""
        return HttpResponse("OK", status=200)
