"""iFood Entrega: chamar o entregador do iFood para pedido do Cardapidex.

Substitui a Uber Direct (que só cotava em sombra). App CENTRALIZADO
"Cardapidex Entregas" (IFOOD_ENTREGAS_*): um token para todas as lojas que
aprovaram o app no Portal do Parceiro; cada loja só tem o `merchant_id`.

    cotar      GET  /shipping/v1.0/merchants/{m}/deliveryAvailabilities
    chamar     POST /shipping/v1.0/merchants/{m}/orders → 202 {id, trackingUrl}
    eventos    GET  /events/v1.0/events:polling + ACK (a cada 30 s, beat)
    cancelar   GET  /shipping/v1.0/orders/{id}/cancellationReasons → POST .../cancel

O iFood é OPÇÃO, nunca trava: cotação recusada (fora dos ~10 km, fora do
horário, sem frota) ou iFood fora do ar → o frete volta para a tabela da loja,
e o entregador pode ser chamado à mão ou por outro meio.

No pedido:
    external_delivery_provider='ifood', _id (id da entrega no iFood),
    _status (último evento), _code (código que o entregador pede ao cliente),
    _url (rastreio). Detalhes (valor, quoteId, erro, entregador) ficam em
    metadata['entrega_ifood'].
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from . import ifood_oauth

logger = logging.getLogger(__name__)

PROVEDOR = 'ifood'
APP = 'entregas'
CHAVE_META = 'entrega_ifood'
COTACAO_CACHE_S = 600

#: Status da entrega que ainda pode virar entregador na porta.
ATIVOS = frozenset({
    'REQUESTED', 'REQUEST_DRIVER', 'REQUEST_DRIVER_SUCCESS', 'ASSIGN_DRIVER', 'GOING_TO_ORIGIN',
    'ARRIVED_AT_ORIGIN', 'DISPATCHED', 'DELIVERY_IN_TRANSIT', 'ARRIVED_AT_DESTINATION',
    'DELIVERY_DROP_CODE_REQUESTED', 'CANCELLATION_REQUESTED', 'DELIVERY_CANCELLATION_REQUESTED',
    'CANCELLATION_REQUEST_FAILED', 'DELIVERY_CANCELLATION_REQUEST_REJECTED',
})
#: Status depois dos quais dá para chamar de novo.
ENCERRADOS_SEM_ENTREGA = frozenset({
    'REQUEST_DRIVER_FAILED', 'DELIVERY_CANCELLED', 'CANCELLED', 'DELIVERY_CANCELLATION_REQUEST_ACCEPTED',
})

TEXTOS = {
    'REQUESTED': 'Procurando entregador',
    'REQUEST_DRIVER': 'Procurando entregador',
    'REQUEST_DRIVER_SUCCESS': 'Entregador a caminho da loja',
    'ASSIGN_DRIVER': 'Entregador a caminho da loja',
    'GOING_TO_ORIGIN': 'Entregador a caminho da loja',
    'ARRIVED_AT_ORIGIN': 'Entregador na loja',
    'DISPATCHED': 'Saiu para entrega',
    'DELIVERY_IN_TRANSIT': 'Saiu para entrega',
    'ARRIVED_AT_DESTINATION': 'Entregador no endereço',
    'DELIVERY_DROP_CODE_REQUESTED': 'Entregador pedindo o código',
    'DELIVERY_CONCLUDED': 'Entregue',
    'CONCLUDED': 'Entregue',
    'REQUEST_DRIVER_FAILED': 'Nenhum entregador disponível',
    'DELIVERY_CANCELLED': 'Cancelada',
    'CANCELLED': 'Cancelada',
    'CANCELLATION_REQUESTED': 'Cancelamento pedido',
    'DELIVERY_CANCELLATION_REQUESTED': 'Cancelamento pedido',
    'DELIVERY_CANCELLATION_REQUEST_ACCEPTED': 'Cancelada',
    'CANCELLATION_REQUEST_FAILED': 'Cancelamento recusado',
    'DELIVERY_CANCELLATION_REQUEST_REJECTED': 'Cancelamento recusado',
}

#: Código de recusa do iFood → frase para o lojista.
MOTIVOS = {
    'DeliveryDistanceTooHigh': 'Endereço longe demais para o entregador iFood.',
    'OffOpeningHours': 'Loja fora do horário no iFood.',
    'ServiceAreaMismatch': 'Endereço fora da área do iFood.',
    'OriginNotFound': 'Endereço da loja não encontrado no iFood.',
    'HighDemand': 'iFood com alta demanda agora — tente em instantes.',
    'UnavailableFleet': 'Sem entregador iFood disponível agora.',
    'MerchantStatusAvailability': 'Loja indisponível no iFood.',
    'MerchantEasyDeliveryDisabled': 'Entrega iFood não habilitada para esta loja.',
    'InvalidPaymentMethods': 'Forma de pagamento não aceita pelo entregador iFood.',
    'PaymentMethodNotFound': 'Forma de pagamento não aceita pelo entregador iFood.',
    'PaymentTotalInvalid': 'Valor do pagamento não confere com o pedido.',
    'NRELimitExceeded': 'Limite de entregas do iFood atingido.',
    'BadRequestCustomer': 'Dados do cliente recusados pelo iFood (nome/telefone).',
}


class EntregaIfoodRecusada(Exception):
    def __init__(self, mensagem: str, codigo: str = ''):
        super().__init__(mensagem)
        self.codigo = codigo


# ── loja ─────────────────────────────────────────────────────────────────

def integracao_ativa(store):
    """A integração da loja se ela pode usar o entregador iFood agora, senão None."""
    if not ifood_oauth.esta_configurado(APP):
        return None
    from apps.stores.models import StoreIfoodIntegration
    integracao = StoreIfoodIntegration.objects.filter(store=store).first()
    if integracao is None or not integracao.merchant_id or not integracao.conectado:
        return None
    return integracao


def _recusa(erro) -> EntregaIfoodRecusada:
    codigo, mensagem = '', ''
    corpo = getattr(erro, 'corpo', '') or ''
    try:
        dados = json.loads(corpo) if corpo else {}
        if isinstance(dados, dict):
            dados = dados.get('error') if isinstance(dados.get('error'), dict) else dados
            codigo = str(dados.get('code') or '')
            mensagem = str(dados.get('message') or '')
    except ValueError:
        pass
    texto = MOTIVOS.get(codigo) or mensagem or str(erro)
    return EntregaIfoodRecusada(texto[:300], codigo)


def _api(metodo, caminho, **kw):
    try:
        return ifood_oauth.api(APP, metodo, caminho, **kw)
    except ifood_oauth.IfoodNaoConfigurado as exc:
        raise EntregaIfoodRecusada('Entregador iFood não configurado na plataforma.') from exc
    except ifood_oauth.IfoodRecusou as exc:
        raise _recusa(exc) from exc


# ── cotação ──────────────────────────────────────────────────────────────

def _decimal(valor) -> Decimal:
    try:
        return Decimal(str(valor if valor not in (None, '') else 0)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0.00')


def cotar(store, lat, lng) -> dict:
    """Cotação do iFood para levar da loja até o ponto. Levanta EntregaIfoodRecusada."""
    integracao = integracao_ativa(store)
    if integracao is None:
        raise EntregaIfoodRecusada('Entregador iFood não está ativo nesta loja.')
    lat, lng = float(lat), float(lng)
    chave = f'ifood:cotacao:{integracao.merchant_id}:{lat:.5f}:{lng:.5f}'
    guardada = cache.get(chave)
    if guardada:
        return guardada
    dados = _api(
        'GET', f'/shipping/v1.0/merchants/{integracao.merchant_id}/deliveryAvailabilities',
        params={'latitude': lat, 'longitude': lng},
    ) or {}
    quote = dados.get('quote') or {}
    tempo = dados.get('deliveryTime') or {}
    cotacao = {
        'quote_id': str(dados.get('id') or ''),
        'valor': _decimal(quote.get('netValue', quote.get('grossValue'))),
        'valor_bruto': _decimal(quote.get('grossValue')),
        'distancia_km': round(float(dados.get('distance') or 0) / 1000, 2),
        'tempo_min': int(tempo.get('min') or 0) // 60,
        'tempo_max': int(tempo.get('max') or 0) // 60,
        'expira_em': dados.get('expirationAt') or '',
        'aceita_pagamento_na_entrega': bool(dados.get('hasPaymentMethods')),
    }
    if not cotacao['quote_id']:
        raise EntregaIfoodRecusada('iFood não devolveu cotação.')
    cache.set(chave, cotacao, timeout=COTACAO_CACHE_S)
    return cotacao


def frete_para_o_cliente(store, lat, lng):
    """Frete pelo iFood (cotação + acréscimo da loja), ou None para usar a tabela."""
    integracao = integracao_ativa(store)
    if integracao is None or not integracao.frete_pelo_ifood or lat is None or lng is None:
        return None
    try:
        cotacao = cotar(store, lat, lng)
    except EntregaIfoodRecusada as exc:
        logger.info('entrega_ifood: sem cotação para %s (%s): %s', store.slug, exc.codigo, exc)
        return None
    except Exception:  # cotação nunca derruba o checkout
        logger.exception('entrega_ifood: cotação quebrou para %s', store.slug)
        return None
    return {
        'fee': cotacao['valor'] + (integracao.acrescimo_frete or Decimal('0')),
        'quote_id': cotacao['quote_id'],
        'distance_km': cotacao['distancia_km'],
        'duration_minutes': cotacao['tempo_max'] or None,
        'provider': PROVEDOR,
        'valor_ifood': cotacao['valor'],
    }


# ── pedido → iFood ───────────────────────────────────────────────────────

def _digitos(texto) -> str:
    return re.sub(r'\D', '', str(texto or ''))


def _telefone(store, order) -> dict:
    numero = _digitos(order.customer_phone)
    if numero.startswith('55') and len(numero) >= 12:
        numero = numero[2:]
    tipo = 'CUSTOMER'
    if len(numero) not in (10, 11):
        numero = _digitos(store.whatsapp_number or store.phone)
        if numero.startswith('55') and len(numero) >= 12:
            numero = numero[2:]
        tipo = 'STORE'
    return {'type': tipo, 'countryCode': '55', 'areaCode': numero[:2], 'number': numero[2:]}


def _cep(store, endereco: dict, lat, lng) -> str:
    cep = _digitos(endereco.get('zip_code') or endereco.get('postal_code') or endereco.get('cep'))
    if len(cep) == 8:
        return cep
    try:
        from apps.stores.services.geo.service import geo_service
        reverso = geo_service.reverse_geocode(lat, lng) or {}
        cep = _digitos(reverso.get('zip_code') or reverso.get('postalCode'))
    except Exception:
        cep = ''
    if len(cep) == 8:
        return cep
    return _digitos(store.zip_code)[:8]


def _endereco(store, order) -> dict:
    endereco = order.delivery_address if isinstance(order.delivery_address, dict) else {}
    lat, lng = endereco.get('lat', endereco.get('latitude')), endereco.get('lng', endereco.get('longitude'))
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        raise EntregaIfoodRecusada('Pedido sem localização no mapa — marque o pino antes de chamar.')
    return {
        'postalCode': _cep(store, endereco, lat, lng),
        'streetNumber': str(endereco.get('number') or 'S/N')[:10],
        'streetName': str(endereco.get('street') or endereco.get('formatted') or 'Endereço no mapa')[:50],
        'complement': str(endereco.get('complement') or '')[:50],
        'reference': str(endereco.get('reference') or order.delivery_notes or '')[:70],
        'neighborhood': str(endereco.get('neighborhood') or '')[:50],
        'city': str(endereco.get('city') or store.city or '')[:50],
        'state': str(endereco.get('state') or store.state or '')[:2].upper(),
        'country': 'BR',
        'coordinates': {'latitude': lat, 'longitude': lng},
    }


def _itens(order) -> list:
    itens = []
    for item in order.items.all():
        total = float(item.subtotal)
        itens.append({
            'id': str(item.id),
            'name': (item.product_name + (f' {item.variant_name}' if item.variant_name else ''))[:50],
            'externalCode': str(item.sku or item.product_id or item.id)[:50],
            'quantity': item.quantity,
            'unitPrice': float(item.unit_price),
            'price': float(item.unit_price) * item.quantity,
            'optionsPrice': round(total - float(item.unit_price) * item.quantity, 2),
            'totalPrice': total,
        })
    if not itens:  # pedido "só com o valor"
        valor = float(order.subtotal or order.total)
        itens.append({
            'id': str(order.id), 'name': f'Pedido {order.order_number}'[:50], 'externalCode': order.order_number[:50],
            'quantity': 1, 'unitPrice': valor, 'price': valor, 'optionsPrice': 0, 'totalPrice': valor,
        })
    return itens


def _pagamento(order):
    """None se já pago; senão o pagamento OFFLINE que o entregador recebe."""
    from apps.stores.formas_de_pagamento import PAGOS_NA_ENTREGA
    if order.payment_method not in PAGOS_NA_ENTREGA or order.payment_status == 'paid':
        return None
    valor = float(order.total)
    if order.payment_method == 'cash':
        metodo = {'method': 'CASH', 'type': 'OFFLINE', 'value': valor}
        if order.change_for and order.change_for > order.total:
            metodo['cash'] = {'changeFor': float(order.change_for)}
    elif order.payment_method == 'card_on_delivery':
        metodo = {'method': 'CREDIT', 'type': 'OFFLINE', 'value': valor}
    else:
        raise EntregaIfoodRecusada('Vale na entrega não é aceito pelo entregador iFood.')
    return {'methods': [metodo]}


def _meta(order) -> dict:
    metadata = order.metadata if isinstance(order.metadata, dict) else {}
    dados = metadata.get(CHAVE_META)
    return dict(dados) if isinstance(dados, dict) else {}


def _gravar_meta(order, **campos):
    from apps.stores.models import StoreOrder
    with transaction.atomic():
        atual = StoreOrder.objects.select_for_update().get(pk=order.pk)
        metadata = atual.metadata if isinstance(atual.metadata, dict) else {}
        metadata[CHAVE_META] = {**(metadata.get(CHAVE_META) or {}), **campos}
        StoreOrder.objects.filter(pk=order.pk).update(metadata=metadata)
    order.metadata = metadata


def montar_pedido(order, cotacao: dict, preparo_s: int = 0) -> dict:
    store = order.store
    corpo = {
        'customer': {'name': (order.customer_name or 'Cliente')[:50], 'phone': _telefone(store, order)},
        'delivery': {
            'merchantFee': float(order.delivery_fee or 0),
            'preparationTime': int(preparo_s),
            'quoteId': cotacao['quote_id'],
            'deliveryAddress': _endereco(store, order),
        },
        'items': _itens(order),
        'displayId': (_digitos(order.order_number) or order.order_number)[-4:],
        'metadata': {'cardapidex_order_id': str(order.id), 'order_number': order.order_number},
    }
    pagamento = _pagamento(order)
    if pagamento:
        corpo['payments'] = pagamento
    return corpo


def chamar(order, preparo_s: int = 0):
    """Chama o entregador iFood para o pedido. Idempotente enquanto a entrega estiver ativa."""
    from apps.stores.models import StoreOrder

    if order.delivery_method != 'delivery':
        raise EntregaIfoodRecusada('Pedido de retirada não tem entrega.')
    if order.external_delivery_provider == PROVEDOR and order.external_delivery_id \
            and order.external_delivery_status not in ENCERRADOS_SEM_ENTREGA:
        return order
    integracao = integracao_ativa(order.store)
    if integracao is None:
        raise EntregaIfoodRecusada('Entregador iFood não está ativo nesta loja.')

    trava = f'ifood_entrega:{order.pk}'
    if not cache.add(trava, 1, timeout=120):
        return order
    try:
        endereco = _endereco(order.store, order)
        coords = endereco['coordinates']
        try:
            cotacao = cotar(order.store, coords['latitude'], coords['longitude'])
            if _pagamento(order) and not cotacao['aceita_pagamento_na_entrega']:
                raise EntregaIfoodRecusada('Pagamento na entrega não aceito pelo entregador iFood aqui.')
            resposta = _api(
                'POST', f'/shipping/v1.0/merchants/{integracao.merchant_id}/orders',
                corpo=montar_pedido(order, cotacao, preparo_s),
            ) or {}
        except EntregaIfoodRecusada as exc:
            _gravar_meta(order, erro=str(exc), erro_codigo=exc.codigo, erro_em=timezone.now().isoformat())
            raise
        entrega_id = str(resposta.get('id') or '')
        if not entrega_id:
            _gravar_meta(order, erro='iFood não devolveu a entrega.', erro_em=timezone.now().isoformat())
            raise EntregaIfoodRecusada('iFood não devolveu a entrega.')
        StoreOrder.objects.filter(pk=order.pk).update(
            external_delivery_provider=PROVEDOR, external_delivery_id=entrega_id[:100],
            external_delivery_status='REQUESTED', external_delivery_code='',
            external_delivery_url=str(resposta.get('trackingUrl') or '')[:500],
        )
        _gravar_meta(
            order, valor=f"{cotacao['valor']:.2f}", quote_id=cotacao['quote_id'],
            chamado_em=timezone.now().isoformat(), erro='', erro_codigo='', entregador=None,
        )
        order.refresh_from_db()
        logger.info('entrega_ifood: %s chamado (%s)', order.order_number, entrega_id)
        return order
    finally:
        cache.delete(trava)


def cancelar(order, motivo: str = ''):
    if order.external_delivery_provider != PROVEDOR or not order.external_delivery_id:
        raise EntregaIfoodRecusada('Este pedido não tem entregador iFood.')
    entrega = order.external_delivery_id
    motivos = _api('GET', f'/shipping/v1.0/orders/{entrega}/cancellationReasons')
    if not motivos:
        raise EntregaIfoodRecusada('O iFood não permite mais cancelar esta entrega.')
    escolhido = motivos[0]
    codigo = escolhido.get('cancelCodeId') or escolhido.get('code') or escolhido.get('cancellationCode')
    try:
        codigo = int(codigo)
    except (TypeError, ValueError):
        raise EntregaIfoodRecusada('iFood devolveu motivo de cancelamento inválido.')
    _api('POST', f'/shipping/v1.0/orders/{entrega}/cancel', corpo={
        'reason': (motivo or escolhido.get('description') or 'Cancelado pela loja')[:250],
        'cancellationCode': codigo,
    })
    from apps.stores.models import StoreOrder
    StoreOrder.objects.filter(pk=order.pk).update(external_delivery_status='CANCELLATION_REQUESTED')
    order.refresh_from_db()
    return order


# ── iFood → pedido (eventos) ─────────────────────────────────────────────

_PARA_O_PEDIDO = {
    'DISPATCHED': 'out_for_delivery',
    'DELIVERY_IN_TRANSIT': 'out_for_delivery',
    'DELIVERY_CONCLUDED': 'delivered',
    'CONCLUDED': 'delivered',
}
_ORDEM = ['pending', 'confirmed', 'processing', 'paid', 'preparing', 'ready', 'shipped',
          'out_for_delivery', 'delivered', 'completed']
_FINAIS = {'delivered', 'completed', 'cancelled', 'refunded', 'failed'}


def aplicar_evento(evento: dict) -> bool:
    """Aplica um evento de entrega. False = não é de pedido nosso (ACK mesmo assim)."""
    from apps.stores.models import StoreOrder

    entrega = str(evento.get('orderId') or '')
    codigo = str(evento.get('fullCode') or evento.get('code') or '').upper()
    if not entrega or not codigo:
        return False
    pedido = StoreOrder.objects.filter(external_delivery_provider=PROVEDOR, external_delivery_id=entrega) \
        .select_related('store').first()
    if pedido is None:
        return False

    campos = {'external_delivery_status': codigo[:30]}
    extra = evento.get('metadata') if isinstance(evento.get('metadata'), dict) else {}
    if codigo == 'DELIVERY_DROP_CODE_REQUESTED' and extra.get('CODE'):
        campos['external_delivery_code'] = str(extra['CODE'])[:30]
    StoreOrder.objects.filter(pk=pedido.pk).update(**campos)

    entregador = {k: extra[k] for k in ('workerName', 'workerPhone', 'driverName', 'driverPhone') if extra.get(k)}
    if entregador:
        _gravar_meta(pedido, entregador={
            'nome': entregador.get('workerName') or entregador.get('driverName') or '',
            'telefone': entregador.get('workerPhone') or entregador.get('driverPhone') or '',
        })
    if codigo == 'REQUEST_DRIVER_FAILED':
        _gravar_meta(pedido, erro='Nenhum entregador iFood aceitou.', erro_em=timezone.now().isoformat())

    novo = _PARA_O_PEDIDO.get(codigo)
    pedido.refresh_from_db()
    if novo and pedido.status not in _FINAIS and pedido.status in _ORDEM \
            and _ORDEM.index(pedido.status) < _ORDEM.index(novo):
        from apps.stores.services.order_service import OrderService
        OrderService().update_status(pedido, novo, notes=f'Entregador iFood: {TEXTOS.get(codigo, codigo)}')
    return True


def processar_eventos() -> dict:
    """Um ciclo de polling do app de entregas para todas as lojas ativas."""
    from apps.stores.models import StoreIfoodIntegration

    resultado = {'eventos': 0, 'falhas': 0}
    if not ifood_oauth.esta_configurado(APP):
        return resultado
    merchants = list(
        StoreIfoodIntegration.objects.filter(conectado=True).exclude(merchant_id='')
        .values_list('merchant_id', flat=True)[:100]
    )
    if not merchants:
        return resultado
    try:
        eventos = ifood_oauth.api(APP, 'GET', '/events/v1.0/events:polling',
                                  cabecalhos={'x-polling-merchants': ','.join(merchants)}) or []
    except (ifood_oauth.IfoodRecusou, ifood_oauth.IfoodNaoConfigurado) as exc:
        logger.warning('entrega_ifood: polling falhou: %s', exc)
        return resultado
    if not isinstance(eventos, list):
        return resultado
    resultado['eventos'] = len(eventos)
    reconhecer = []
    for evento in eventos:
        try:
            with transaction.atomic():
                aplicar_evento(evento)
        except Exception as exc:  # sem ACK: volta no próximo ciclo
            resultado['falhas'] += 1
            logger.warning('entrega_ifood: evento %s (%s) falhou: %s',
                           evento.get('id'), evento.get('fullCode'), exc)
            continue
        if evento.get('id'):
            reconhecer.append({'id': evento['id']})
    if reconhecer:
        try:
            ifood_oauth.api(APP, 'POST', '/events/v1.0/events/acknowledgment', corpo=reconhecer)
        except (ifood_oauth.IfoodRecusou, ifood_oauth.IfoodNaoConfigurado) as exc:
            logger.warning('entrega_ifood: ACK falhou: %s', exc)
    return resultado


# ── painel ───────────────────────────────────────────────────────────────

def estado(order) -> dict:
    meta = _meta(order)
    chamado = order.external_delivery_provider == PROVEDOR and bool(order.external_delivery_id)
    status = order.external_delivery_status if chamado else ''
    valor = meta.get('valor')
    disponivel = integracao_ativa(order.store) is not None
    return {
        'disponivel': disponivel,
        'pode_chamar': disponivel and order.delivery_method == 'delivery'
        and (not chamado or status in ENCERRADOS_SEM_ENTREGA),
        'chamado': chamado,
        'status': status,
        'status_texto': TEXTOS.get(status, status.replace('_', ' ').capitalize()) if chamado else '',
        'ativo': chamado and status in ATIVOS,
        'rastreio_url': order.external_delivery_url if chamado else '',
        'codigo_entrega': order.external_delivery_code if chamado else '',
        'entregador': meta.get('entregador') if chamado else None,
        'valor': float(valor) if valor not in (None, '') else None,
        'erro': meta.get('erro') or '',
    }


def deve_chamar_sozinho(order, novo_status: str):
    """Quando o pedido muda de status: o tempo de preparo a pedir, ou None (não chamar)."""
    if order.delivery_method != 'delivery' or order.source in ('ifood', '99food'):
        return None
    if order.external_delivery_id:
        return None
    integracao = integracao_ativa(order.store)
    if integracao is None:
        return None
    modo = integracao.chamar_entregador
    if modo == 'confirmado' and novo_status == 'confirmed':
        return integracao.tempo_preparo_min * 60
    if modo == 'pronto' and novo_status == 'ready':
        return 0
    return None
