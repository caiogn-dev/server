"""Webhooks da 99Food (pedidos, entrega e cardápio).

Corpo de todo aviso, segundo a 99:
    {"app_id": <long>, "app_shop_id": "<id da loja no nosso sistema>",
     "type": "<tipo>", "timestamp": <int>, "data": {...} | "<string>"}

`orderNew` vira pedido no quadro (e já pede a confirmação, que a 99 exige em
5 min); cancelamento, conclusão e status de entrega atualizam o pedido. A
assinatura já foi conferida pelo dispatcher e o evento já está guardado.

A 99 dá 6 s por aviso e reenvia se a resposta não for errno 0: criar o pedido é
só banco; tudo que chama a 99 de volta vai para o Celery.
"""
import logging
from typing import Any, Dict

from apps.webhooks.handlers.base import BaseHandler
from apps.webhooks.models import WebhookEvent

logger = logging.getLogger(__name__)


class NinetyNineFoodHandler(BaseHandler):
    PROVIDER = '99food'

    def handle(self, event: WebhookEvent, payload: dict, headers: dict) -> Dict[str, Any]:
        from apps.stores.services import pedidos_da_99

        tipo = payload.get('type') or 'unknown'
        codigo = payload.get('app_shop_id') or ''
        dados = payload.get('data')
        loja = pedidos_da_99.loja_do_aviso(codigo)
        if loja is None:
            logger.warning('99food: aviso %s de loja desconhecida %r (evento %s)', tipo, codigo, event.pk)
            return {'ok': True, 'type': tipo, 'processado': False, 'motivo': 'loja desconhecida'}

        if tipo == 'orderNew' and isinstance(dados, dict):
            pedido, criado = pedidos_da_99.receber_pedido_novo(loja, dados)
            return {'ok': True, 'type': tipo, 'processado': True,
                    'order_number': pedido.order_number, 'criado': criado}

        processado = pedidos_da_99.aplicar_aviso(loja, tipo, dados)
        logger.info('99food: aviso %s da loja %s (evento %s, processado=%s)', tipo, loja.slug, event.pk, processado)
        return {'ok': True, 'type': tipo, 'processado': processado}
