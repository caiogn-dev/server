"""Webhook do iFood (apps centralizados): /webhooks/v1/ifood/.

Liberado para o app Cardapidex em 23/11/2026, junto com a homologação parcial.
Regras da documentação (events/webhook-overview, webhook-signature, presence):

    assinatura   X-IFood-Signature = HMAC-SHA256 hex do body BRUTO com o
                 client_secret do app. Inválida → 401 (o iFood testa isso na
                 homologação mandando assinatura errada). Os dois apps podem
                 apontar para a mesma URL: o segredo que bate diz qual é.
    tempo        202 em até 5 s; o evento vai para a fila (Celery).
    KEEPALIVE    a cada 30 s. Modo por app: 202 = todas as lojas online. Modo
                 por merchant: devolver {"merchantIds": [...]} só com quem está
                 conectado aqui. App de ENTREGAS nunca põe loja online — não é
                 PDV, abriria a loja no iFood sem ninguém olhando pedidos.
    entrega      at-least-once, fora de ordem, sem ACK: idempotência pelo `id`
                 (mesmo cache do polling, então os dois caminhos convivem).
"""
from __future__ import annotations

import hashlib
import hmac
import logging

from django.conf import settings
from django.db import transaction

from apps.stores.services import ifood_oauth

logger = logging.getLogger(__name__)

KEEPALIVE = 'KEEPALIVE'
TESTE = 'teste'


def app_da_assinatura(corpo: bytes, assinatura: str) -> str | None:
    """Qual app assinou este body ('pedidos' | 'entregas'), ou None se nenhum."""
    assinatura = (assinatura or '').strip().lower()
    if not assinatura:
        return None
    # Segredo REAL sempre (o webhook do app de verdade não para durante a
    # gravação da homologação) e, com o modo homologação, o do app de teste.
    candidatos = [(app, ifood_oauth.credenciais_reais(app)[1]) for app in ('pedidos', 'entregas')]
    if ifood_oauth.em_homologacao():
        candidatos.append((TESTE, getattr(settings, 'IFOOD_HOMOLOGACAO_CLIENT_SECRET', '')))
    for app, segredo in candidatos:
        if not segredo:
            continue
        esperado = hmac.new(segredo.encode('utf-8'), corpo, hashlib.sha256).hexdigest()
        if hmac.compare_digest(esperado, assinatura):
            return app
    return None


def deve_processar(app: str) -> bool:
    """Em homologação o servidor fala com o iFood pelo app de teste: evento do
    app real não teria como buscar o pedido — a loja real está offline (ver
    `presenca`), então não chega pedido novo por ele."""
    return app == TESTE or not ifood_oauth.em_homologacao()


def _conectados(ids) -> set:
    from apps.stores.models import StoreIfoodIntegration
    minusculos = {str(i).lower() for i in ids if i}
    return set(
        StoreIfoodIntegration.objects.filter(conectado=True, merchant_id__in=minusculos)
        .values_list('merchant_id', flat=True)
    )


def presenca(app: str, evento: dict):
    """Resposta ao KEEPALIVE: None = 202 sem corpo; lista = merchantIds online."""
    ids = evento.get('merchantIds')
    if ids is None:
        return None
    if app not in ('pedidos', TESTE) or not deve_processar(app):
        return []  # entregas não é PDV; app real em homologação = loja offline
    online = _conectados(ids)
    return [m for m in ids if str(m).lower() in online]


def _loja(merchant_id):
    from apps.stores.models import StoreIfoodIntegration
    integracao = StoreIfoodIntegration.objects.filter(
        merchant_id=str(merchant_id or '').lower(), conectado=True,
    ).select_related('store').first()
    return integracao.store if integracao else None


def processar(app: str, evento: dict) -> bool:
    """Aplica um evento recebido pelo webhook. Levanta para o Celery tentar de novo."""
    from apps.stores.services import entrega_ifood, pedidos_do_ifood

    evento_id = evento.get('id')
    if ifood_oauth.evento_ja_visto(evento_id):
        return False
    if app == TESTE:
        app = 'pedidos'
    if app == 'entregas':
        aplicado = entrega_ifood.aplicar_evento(evento)
    else:
        store = _loja(evento.get('merchantId'))
        if store is None:
            logger.warning('ifood webhook: evento %s de merchant desconhecido %s — ignorado',
                           evento_id, evento.get('merchantId'))
            return False
        with transaction.atomic():
            aplicado = pedidos_do_ifood.aplicar_evento(store, evento)
    ifood_oauth.lembrar_evento(evento_id)
    logger.info('ifood webhook: evento %s %s pedido=%s ok', evento_id, evento.get('code'), evento.get('orderId'))
    return aplicado
