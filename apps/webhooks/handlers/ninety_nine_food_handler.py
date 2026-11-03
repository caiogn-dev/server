"""Webhooks da 99Food (pedidos, entrega e cardápio).

Corpo de todo aviso, segundo a 99:
    {"app_id": <long>, "app_shop_id": "<id da loja no nosso sistema>",
     "type": "<tipo>", "timestamp": <int>, "data": {...} | "<string>"}

Por ora só registra: a conta da loja na 99 ainda está em aprovação e os tipos
de evento de cada módulo serão tratados quando a integração de pedidos e do
99Entrega existir. O dispatcher já garantiu a assinatura e guardou o evento
(WebhookEvent), então nenhum aviso se perde até lá.

A 99 dá 6 s por aviso: qualquer processamento pesado futuro vai para o Celery.
"""
import logging
from typing import Any, Dict

from apps.webhooks.handlers.base import BaseHandler
from apps.webhooks.models import WebhookEvent

logger = logging.getLogger(__name__)


class NinetyNineFoodHandler(BaseHandler):
    PROVIDER = '99food'

    def handle(self, event: WebhookEvent, payload: dict, headers: dict) -> Dict[str, Any]:
        tipo = payload.get('type') or 'unknown'
        loja = payload.get('app_shop_id') or ''
        logger.info('99food: aviso %s da loja %s guardado (evento %s)', tipo, loja, event.pk)
        return {'ok': True, 'type': tipo, 'app_shop_id': loja, 'processado': False}
