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
    'CANCELLATION_REQUESTED': 'Cancelando…',
    'DELIVERY_CANCELLATION_REQUESTED': 'Cancelando…',
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


APP_DA_LOJA_S = 6 * 3600


def _chave_app(store) -> str:
    return f'ifood:app-shipping:{store.pk}'


def _apps_para(store=None, pedido=None) -> list:
    """Apps para tentar, em ordem. Shipping foi homologado em 24/11 no app
    Cardapidex (pedidos), não no Entregas, e a Cê Saladas deu shipping só ao
    de pedidos. A entrega já criada segue no app que a criou."""
    if pedido is not None:
        criado_por = (_meta(pedido) or {}).get('app')
        if criado_por:
            return [criado_por]
        store = store or pedido.store
    ordem = [APP]
    if ifood_oauth.esta_configurado('pedidos') \
            and ifood_oauth.credenciais('pedidos')[0] != ifood_oauth.credenciais(APP)[0]:
        ordem.append('pedidos')
    lembrado = cache.get(_chave_app(store)) if store is not None else None
    if lembrado in ordem:
        ordem.remove(lembrado)
        ordem.insert(0, lembrado)
    return ordem


def _proibido(exc) -> bool:
    return exc.status == 403 and 'forbidden' in (exc.corpo or str(exc)).lower()


def _api(metodo, caminho, loja=None, pedido=None, **kw):
    apps = _apps_para(loja, pedido)
    store = loja or (pedido.store if pedido is not None else None)
    for i, app in enumerate(apps):
        ultimo = i == len(apps) - 1
        try:
            resposta = ifood_oauth.api(app, metodo, caminho, **kw)
        except ifood_oauth.IfoodNaoConfigurado as exc:
            if ultimo:
                raise EntregaIfoodRecusada('Entregador iFood não configurado na plataforma.') from exc
            continue
        except ifood_oauth.IfoodRecusou as exc:
            if _proibido(exc) and not ultimo:
                continue
            raise _recusa(exc) from exc
        if store is not None:
            cache.set(_chave_app(store), app, timeout=APP_DA_LOJA_S)
        return resposta
    raise EntregaIfoodRecusada('Entregador iFood não configurado na plataforma.')


def _app_usado(store) -> str:
    return cache.get(_chave_app(store)) or APP


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
        'GET', f'/shipping/v1.0/merchants/{integracao.merchant_id}/deliveryAvailabilities', loja=store,
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
    do_ifood = _dados_do_pedido_ifood(order)
    if do_ifood is not None and do_ifood.get('entrega_do_ifood'):
        raise EntregaIfoodRecusada('O iFood já entrega este pedido.')
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
        if do_ifood is not None:
            return _pedir_entregador_para_pedido_do_ifood(order, do_ifood)
        endereco = _endereco(order.store, order)
        coords = endereco['coordinates']
        try:
            cotacao = cotar(order.store, coords['latitude'], coords['longitude'])
            if _pagamento(order) and not cotacao['aceita_pagamento_na_entrega']:
                raise EntregaIfoodRecusada('Pagamento na entrega não aceito pelo entregador iFood aqui.')
            resposta = _api(
                'POST', f'/shipping/v1.0/merchants/{integracao.merchant_id}/orders', loja=order.store,
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
            app=_app_usado(order.store),
        )
        order.refresh_from_db()
        logger.info('entrega_ifood: %s chamado (%s)', order.order_number, entrega_id)
        _buscar_codigo_de_coleta(order)
        return order
    finally:
        cache.delete(trava)


# ── pedido que veio do iFood com entrega da loja (Shipping, cenário 2) ────

def _dados_do_pedido_ifood(order):
    """O bloco 'ifood' do metadata quando o pedido nasceu no iFood, senão None."""
    if order.source != PROVEDOR:
        return None
    dados = (order.metadata or {}).get(PROVEDOR) if isinstance(order.metadata, dict) else None
    if not isinstance(dados, dict) or not dados.get('order_id'):
        return None
    return dados


def _pedir_entregador_para_pedido_do_ifood(order, do_ifood: dict):
    """deliveryAvailabilities → requestDriver pelo orderId do iFood. O pedido
    já existe lá: criar pedido externo duplicaria a entrega."""
    from apps.stores.models import StoreOrder

    pedido_ifood = str(do_ifood['order_id'])
    try:
        dados = _api('GET', f'/shipping/v1.0/orders/{pedido_ifood}/deliveryAvailabilities', loja=order.store) or {}
        quote_id = str(dados.get('id') or '')
        if not quote_id:
            raise EntregaIfoodRecusada('iFood não devolveu cotação.')
        _api('POST', f'/shipping/v1.0/orders/{pedido_ifood}/requestDriver', loja=order.store,
             corpo={'quoteId': quote_id})
    except EntregaIfoodRecusada as exc:
        _gravar_meta(order, erro=str(exc), erro_codigo=exc.codigo, erro_em=timezone.now().isoformat())
        raise
    quote = dados.get('quote') or {}
    StoreOrder.objects.filter(pk=order.pk).update(
        external_delivery_provider=PROVEDOR, external_delivery_id=pedido_ifood[:100],
        external_delivery_status='REQUESTED', external_delivery_code='',
    )
    _gravar_meta(
        order, valor=f"{_decimal(quote.get('netValue', quote.get('grossValue'))):.2f}", quote_id=quote_id,
        chamado_em=timezone.now().isoformat(), erro='', erro_codigo='', entregador=None,
        pedido_do_ifood=True, app=_app_usado(order.store),
    )
    order.refresh_from_db()
    logger.info('entrega_ifood: %s requestDriver (pedido iFood %s)', order.order_number, pedido_ifood)
    return order


def _codigo_de_coleta(order) -> str:
    do_ifood = _dados_do_pedido_ifood(order) or {}
    return str(_meta(order).get('codigo_coleta') or do_ifood.get('codigo_coleta') or '')


def _buscar_codigo_de_coleta(order):
    """pickupCode vem nos detalhes do pedido no iFood (inclusive do pedido
    criado pelo create order). Melhor esforço: sem ele a entrega segue."""
    if not order.external_delivery_id or _codigo_de_coleta(order):
        return
    try:
        detalhe = _api('GET', f'/order/v1.0/orders/{order.external_delivery_id}', pedido=order) or {}
    except Exception as exc:  # noqa: BLE001 — informativo, nunca derruba a chamada
        logger.info('entrega_ifood: %s sem pickupCode ainda (%s)', order.order_number, exc)
        return
    codigo = str(((detalhe.get('delivery') or {}) if isinstance(detalhe, dict) else {}).get('pickupCode') or '')
    if codigo:
        _gravar_meta(order, codigo_coleta=codigo[:30])


def motivos_de_cancelamento(order) -> list:
    """Motivos que o iFood aceita AGORA para esta entrega (o painel lista)."""
    if order.external_delivery_provider != PROVEDOR or not order.external_delivery_id:
        raise EntregaIfoodRecusada('Este pedido não tem entregador iFood.')
    if _pedido_com_entregador_pedido(order):
        # requestDriver não tem motivos: o cancelamento é só antes do aceite.
        return [{'codigo': CANCELAR_SOLICITACAO, 'descricao': 'Cancelar a solicitação de entregador'}]
    motivos = _api('GET', f'/shipping/v1.0/orders/{order.external_delivery_id}/cancellationReasons', pedido=order) or []
    saida = []
    for m in motivos if isinstance(motivos, list) else []:
        codigo = m.get('cancelCodeId') or m.get('code') or m.get('cancellationCode')
        if codigo is not None:
            saida.append({'codigo': str(codigo), 'descricao': str(m.get('description') or '')})
    return saida


CANCELAR_SOLICITACAO = 'cancelRequestDriver'


def _pedido_com_entregador_pedido(order) -> bool:
    """Pedido do iFood em que a LOJA pediu o entregador (requestDriver)."""
    do_ifood = _dados_do_pedido_ifood(order)
    return do_ifood is not None and not do_ifood.get('entrega_do_ifood') \
        and order.external_delivery_id == str(do_ifood.get('order_id'))


def cancelar(order, motivo: str = '', codigo: str | None = None):
    """Cancela o entregador. `codigo` = motivo escolhido pelo lojista entre os
    do iFood; sem ele (cancelamento automático do pedido) vai o primeiro."""
    if _pedido_com_entregador_pedido(order):
        _api('POST', f'/shipping/v1.0/orders/{order.external_delivery_id}/cancelRequestDriver', pedido=order)
        from apps.stores.models import StoreOrder
        StoreOrder.objects.filter(pk=order.pk).update(external_delivery_status='CANCELLATION_REQUESTED')
        order.refresh_from_db()
        return order
    motivos = motivos_de_cancelamento(order)
    if not motivos:
        raise EntregaIfoodRecusada('O iFood não permite mais cancelar esta entrega.')
    if codigo is not None:
        escolhido = next((m for m in motivos if m['codigo'] == str(codigo)), None)
        if escolhido is None:
            raise EntregaIfoodRecusada('Escolha um dos motivos do iFood.')
    else:
        escolhido = motivos[0]
    # Texto, não número: o iFood recusa int com 400 "Unmarshal type error" (medido 20/11).
    numero = str(escolhido['codigo'] or '').strip()
    if not numero.isdigit():
        raise EntregaIfoodRecusada('iFood devolveu motivo de cancelamento inválido.')
    _api('POST', f'/shipping/v1.0/orders/{order.external_delivery_id}/cancel', pedido=order, corpo={
        'reason': ((escolhido['descricao'] if codigo is not None else motivo) or escolhido['descricao']
                   or 'Cancelado pela loja')[:250],
        'cancellationCode': numero,
    })
    from apps.stores.models import StoreOrder
    StoreOrder.objects.filter(pk=order.pk).update(external_delivery_status='CANCELLATION_REQUESTED')
    order.refresh_from_db()
    return order


# ── mudança de endereço pedida pelo cliente ──────────────────────────────

def _endereco_do_ifood(a: dict) -> dict:
    coord = a.get('coordinates') or {}
    return {k: v for k, v in {
        'street': a.get('streetName') or '', 'number': a.get('streetNumber') or '',
        'complement': a.get('complement') or '', 'neighborhood': a.get('neighborhood') or '',
        'city': a.get('city') or '', 'state': a.get('state') or '', 'zip_code': a.get('postalCode') or '',
        'reference': a.get('reference') or '',
        'lat': coord.get('latitude'), 'lng': coord.get('longitude'),
    }.items() if v not in ('', None)}


def _mudanca_de_endereco(pedido, codigo: str, extra: dict):
    atual = dict((pedido.metadata or {}).get(CHAVE_META, {}).get('mudanca_endereco') or {})
    if codigo.endswith('_REQUESTED'):
        endereco = _endereco_do_ifood(extra.get('address') or extra.get('deliveryAddress') or extra)
        texto = ', '.join(x for x in (
            f"{endereco.get('street', '')}, {endereco.get('number', '')}".strip(', '),
            endereco.get('complement'), endereco.get('neighborhood'), endereco.get('city')) if x)
        _gravar_meta(pedido, mudanca_endereco={
            'status': 'PEDIDA', 'endereco': endereco, 'texto': texto,
            'prazo': str(extra.get('timeoutAt') or extra.get('expiresAt') or ''),
            'pedida_em': timezone.now().isoformat(),
        })
    else:
        fim = codigo.rsplit('_', 1)[-1]
        atual['status'] = {'ACCEPTED': 'ACEITA', 'DENIED': 'RECUSADA', 'CONFIRMED': 'ACEITA'}.get(fim, fim)
        _gravar_meta(pedido, mudanca_endereco=atual)
        # Aceite que não passou pelo nosso botão (só o evento chega): o pedido
        # também tem que ir para o endereço novo.
        if atual['status'] == 'ACEITA' and atual.get('endereco'):
            from apps.stores.models import StoreOrder
            novo = {**(pedido.delivery_address or {}), **atual['endereco']}
            StoreOrder.objects.filter(pk=pedido.pk).update(delivery_address=novo)


def responder_endereco(order, aceitar: bool):
    mudanca = dict((order.metadata or {}).get(CHAVE_META, {}).get('mudanca_endereco') or {})
    if mudanca.get('status') != 'PEDIDA':
        raise EntregaIfoodRecusada('Não há mudança de endereço esperando resposta.')
    acao = 'acceptDeliveryAddressChange' if aceitar else 'denyDeliveryAddressChange'
    _api('POST', f'/shipping/v1.0/orders/{order.external_delivery_id}/{acao}', pedido=order)
    mudanca.update({'status': 'ACEITA' if aceitar else 'RECUSADA', 'respondida_em': timezone.now().isoformat()})
    _gravar_meta(order, mudanca_endereco=mudanca)
    if aceitar and mudanca.get('endereco'):
        from apps.stores.models import StoreOrder
        novo = {**(order.delivery_address or {}), **mudanca['endereco']}
        StoreOrder.objects.filter(pk=order.pk).update(delivery_address=novo)
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
#: Eventos depois dos quais o pedido já existe no iFood com pickupCode.
_BUSCA_COLETA = frozenset({'REQUEST_DRIVER_SUCCESS', 'ASSIGN_DRIVER', 'GOING_TO_ORIGIN'})
#: Eventos logísticos (o polling de pedidos repassa estes para cá).
LOGISTICOS = frozenset(TEXTOS) | _BUSCA_COLETA | frozenset({
    'DELIVERY_ADDRESS_CHANGE_REQUESTED', 'DELIVERY_ADDRESS_CHANGE_ACCEPTED',
    'DELIVERY_ADDRESS_CHANGE_DENIED', 'DELIVERY_ADDRESS_CHANGE_USER_CONFIRMED',
})


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

    # Mudança de endereço é uma conversa paralela à corrida: não é status da
    # entrega. Gravá-la ali apagava o "em andamento" (ao vivo 24/11).
    campos = {} if codigo.startswith('DELIVERY_ADDRESS_CHANGE') else {'external_delivery_status': codigo[:30]}
    extra = evento.get('metadata') if isinstance(evento.get('metadata'), dict) else {}
    if codigo == 'DELIVERY_DROP_CODE_REQUESTED' and extra.get('CODE'):
        campos['external_delivery_code'] = str(extra['CODE'])[:30]
    if campos:
        StoreOrder.objects.filter(pk=pedido.pk).update(**campos)

    entregador = {k: extra[k] for k in ('workerName', 'workerPhone', 'driverName', 'driverPhone') if extra.get(k)}
    if entregador:
        _gravar_meta(pedido, entregador={
            'nome': entregador.get('workerName') or entregador.get('driverName') or '',
            'telefone': entregador.get('workerPhone') or entregador.get('driverPhone') or '',
        })
    if codigo.startswith('DELIVERY_ADDRESS_CHANGE'):
        _mudanca_de_endereco(pedido, codigo, extra)
    if codigo == 'REQUEST_DRIVER_FAILED':
        _gravar_meta(pedido, erro='Nenhum entregador iFood aceitou.', erro_em=timezone.now().isoformat())

    if codigo in _BUSCA_COLETA:
        _buscar_codigo_de_coleta(pedido)

    novo = _PARA_O_PEDIDO.get(codigo)
    pedido.refresh_from_db()
    # Pedido do iFood: o status anda pelos eventos de PEDIDO (Order API); mover
    # aqui mandaria um dispatch a mais para o iFood.
    if novo and pedido.source != PROVEDOR and pedido.status not in _FINAIS and pedido.status in _ORDEM \
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
    # Mesmo app nos dois lados (modo homologação): o polling daqui confirmaria
    # o PLACED de pedido novo antes do polling de pedidos ler. Lá os eventos
    # logísticos já são repassados para esta entrega.
    if ifood_oauth.credenciais(APP)[0] == ifood_oauth.credenciais('pedidos')[0]:
        return resultado
    merchants = ifood_oauth.merchants_do_app(APP, list(
        StoreIfoodIntegration.objects.filter(conectado=True).exclude(merchant_id='')
        .values_list('merchant_id', flat=True)[:100]
    ))
    if not merchants:
        return resultado
    try:
        # excludeHeartbeat: OBRIGATÓRIO para quem só faz logística — sem ele o
        # polling conta como "PDV online" e ABRE a loja no app do iFood.
        eventos = ifood_oauth.api(APP, 'GET', '/events/v1.0/events:polling',
                                  cabecalhos={'x-polling-merchants': ','.join(merchants)},
                                  params={'excludeHeartbeat': 'true'}) or []
    except (ifood_oauth.IfoodRecusou, ifood_oauth.IfoodNaoConfigurado) as exc:
        logger.warning('entrega_ifood: polling falhou: %s', exc)
        return resultado
    if not isinstance(eventos, list):
        return resultado
    resultado['eventos'] = len(eventos)
    reconhecer = []
    for evento in eventos:
        if ifood_oauth.evento_ja_visto(evento.get('id')):
            reconhecer.append({'id': evento['id']})
            continue
        try:
            with transaction.atomic():
                aplicar_evento(evento)
            ifood_oauth.lembrar_evento(evento.get('id'))
            logger.info('entrega_ifood: evento %s %s entrega=%s ok', evento.get('id'),
                        evento.get('fullCode') or evento.get('code'), evento.get('orderId'))
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
    integracao = integracao_ativa(order.store)
    disponivel = integracao is not None
    # 'confirmado'/'pronto' = a loja chama sozinha nesse status (mesma regra de
    # `deve_chamar_sozinho`); '' = o operador chama. O cartão mostra a espera
    # em vez de um botão que parece tarefa.
    automatico = ''
    if (disponivel and order.delivery_method == 'delivery'
            and order.source not in ('ifood', '99food')
            and integracao.chamar_entregador in ('confirmado', 'pronto')):
        automatico = integracao.chamar_entregador
    return {
        'disponivel': disponivel,
        'automatico': automatico,
        'pode_chamar': disponivel and order.delivery_method == 'delivery'
        and not (_dados_do_pedido_ifood(order) or {}).get('entrega_do_ifood')
        and (not chamado or status in ENCERRADOS_SEM_ENTREGA),
        'codigo_coleta': _codigo_de_coleta(order),
        'chamado': chamado,
        'status': status,
        'status_texto': TEXTOS.get(status, status.replace('_', ' ').capitalize()) if chamado else '',
        'ativo': chamado and status in ATIVOS,
        'rastreio_url': order.external_delivery_url if chamado else '',
        'codigo_entrega': order.external_delivery_code if chamado else '',
        'entregador': meta.get('entregador') if chamado else None,
        'valor': float(valor) if valor not in (None, '') else None,
        'erro': meta.get('erro') or '',
        'mudanca_endereco': meta.get('mudanca_endereco') if (meta.get('mudanca_endereco') or {}).get('status') == 'PEDIDA' else None,
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
