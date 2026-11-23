"""POST /webhooks/v1/ifood/ — ver apps/stores/services/webhook_ifood.py."""
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.stores.services import webhook_ifood

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def webhook_ifood_view(request):
    corpo = request.body  # bruto: a assinatura é do byte array, antes do parse
    app = webhook_ifood.app_da_assinatura(corpo, request.headers.get('X-IFood-Signature', ''))
    if app is None:
        logger.warning('ifood webhook: assinatura inválida (%s bytes)', len(corpo))
        return HttpResponse('Invalid signature', status=401)
    try:
        dados = json.loads(corpo)
    except ValueError:
        return HttpResponse('Invalid JSON', status=400)

    eventos = dados if isinstance(dados, list) else [dados]
    eventos = [e for e in eventos if isinstance(e, dict)]
    for evento in eventos:
        if str(evento.get('code') or '').upper() == webhook_ifood.KEEPALIVE:
            online = webhook_ifood.presenca(app, evento)
            if online is None:
                return HttpResponse(status=202)
            return JsonResponse({'merchantIds': online}, status=202)

    if not webhook_ifood.deve_processar(app):
        logger.warning('ifood webhook: %s eventos do app real ignorados (modo homologação)', len(eventos))
        return HttpResponse(status=202)
    from apps.stores.tasks import evento_do_webhook_ifood
    for evento in eventos:
        evento_do_webhook_ifood.delay(app, evento)
    return HttpResponse(status=202)
