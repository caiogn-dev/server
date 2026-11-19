"""Pedidos do iFood dentro do Cardapidex.

Mesmo desenho da 99Food (`pedidos_da_99`): o pedido do app cai no mesmo quadro,
na mesma comanda e nos mesmos relatórios, e o que o painel faz com ele volta
para o iFood pela API.

A diferença é a entrada. A 99 avisa por webhook; o iFood espera POLLING:

- GET /order/v1.0/events:polling a cada 30 s. É também o que mantém a loja
  "aberta" no app do iFood — parar o polling fecha a loja lá.
- ACK em POST /order/v1.0/events/acknowledgment de TODO evento recebido, até
  os que ignoramos; evento sem ACK volta no polling seguinte. Por isso evento
  que FALHOU ao processar fica sem ACK de propósito: é o retry de graça.
- O evento traz só código + orderId; o pedido inteiro vem de
  GET /order/v1.0/orders/{id}.
- Valores em REAIS com casas decimais (a 99 manda centavos).
- Pedido não confirmado o iFood cancela sozinho: confirmamos logo que entra.

O token é de cada loja (fluxo distribuído, `ifood_oauth.token_valido`).
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from requests import RequestException

from . import ifood_oauth

logger = logging.getLogger(__name__)

BASE = ifood_oauth.BASE
PROVEDOR = 'ifood'
TIMEOUT = 10

# Evento do iFood → o que fazer no pedido.
PEDIDO_NOVO = 'PLC'
CONFIRMADO = 'CFM'
CANCELADO = 'CAN'
CONCLUIDO = 'CON'
DESPACHADO = 'DSP'
PRONTO = 'RTP'
CANCELAMENTO_PEDIDO = 'CAR'
CANCELAMENTO_NEGADO = 'CARF'

# Motivo que o dono escolhe no painel → trecho da descrição do iFood.
_MOTIVOS = (
    (('acab', 'esgot', 'falt', 'indispon'), 'indispon'),
    (('fechad',), 'fechad'),
    (('ocupad', 'cheia', 'movimento', 'demora'), 'demora'),
    (('fora da área', 'fora da area', 'longe', 'endereço', 'endereco'), 'área de entrega'),
    (('sistema',), 'sistema'),
)


class ErroDoIfood(Exception):
    pass


# ── API ───────────────────────────────────────────────────────────────────

def _chamar(store, metodo: str, caminho: str, corpo=None, cabecalhos=None):
    """A chamada crua. Isolada para o teste substituir sem tocar em rede.

    Devolve o JSON, ou None quando o iFood responde sem corpo (204/202).
    """
    import requests

    token = ifood_oauth.token_valido(store)
    if not token:
        raise ErroDoIfood('Loja sem acesso ao iFood (desconectada ou token recusado).')
    headers = {'Authorization': f'Bearer {token}', **(cabecalhos or {})}
    try:
        resposta = requests.request(metodo, f'{BASE}{caminho}', json=corpo, headers=headers, timeout=TIMEOUT)
    except RequestException as exc:
        raise ErroDoIfood(f'iFood fora do ar: {exc}') from exc
    if resposta.status_code >= 400:
        raise ErroDoIfood(f'{resposta.status_code}: {resposta.text[:300]}')
    if resposta.status_code in (202, 204) or not resposta.content:
        return None
    try:
        return resposta.json()
    except ValueError:
        return None


def _integracao(store):
    from apps.stores.models import StoreIfoodIntegration
    return StoreIfoodIntegration.objects.filter(store=store).first()


def descobrir_loja_no_ifood(store):
    """Depois do vínculo: qual restaurante do iFood este token enxerga."""
    integracao = _integracao(store)
    if integracao is None:
        return None
    lojas = _chamar(store, 'GET', '/merchant/v1.0/merchants') or []
    if isinstance(lojas, list) and lojas:
        primeira = lojas[0]
        integracao.merchant_id = str(primeira.get('id') or '')[:64]
        integracao.merchant_name = str(primeira.get('name') or '')[:255]
        integracao.save(update_fields=['merchant_id', 'merchant_name', 'updated_at'])
    return integracao


# ── Pedido ────────────────────────────────────────────────────────────────

def _reais(valor) -> Decimal:
    try:
        return Decimal(str(valor if valor not in (None, '') else 0)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0.00')


def dados_ifood(order) -> dict:
    metadata = order.metadata if isinstance(order.metadata, dict) else {}
    dados = metadata.get(PROVEDOR)
    return dados if isinstance(dados, dict) else {}


def pedido_do_ifood(store, order_id):
    from apps.stores.models import StoreOrder
    if not order_id:
        return None
    return StoreOrder.objects.filter(
        store=store, source=PROVEDOR, **{f'metadata__{PROVEDOR}__order_id': str(order_id)},
    ).first()


def _produto(store, codigo):
    from apps.stores.models import StoreProduct
    codigo = str(codigo or '').strip()
    if not codigo:
        return None
    filtro = StoreProduct.objects.filter(store=store)
    try:
        return filtro.filter(sku=codigo).first() or filtro.filter(id=codigo).first()
    except Exception:  # código que não é UUID
        return filtro.filter(sku=codigo).first()


def _texto_das_opcoes(opcoes) -> str:
    partes = []
    for opcao in opcoes or []:
        nome = str(opcao.get('name') or '').strip()
        if not nome:
            continue
        qtd = int(opcao.get('quantity') or 1)
        partes.append(f'{qtd}x {nome}' if qtd > 1 else nome)
        internas = _texto_das_opcoes(opcao.get('customizations') or opcao.get('options'))
        if internas:
            partes.append(internas)
    return ', '.join(partes)


def _endereco(endereco: dict) -> dict:
    coordenadas = endereco.get('coordinates') or {}
    lat, lng = coordenadas.get('latitude'), coordenadas.get('longitude')
    return {
        'street': endereco.get('streetName') or '',
        'number': endereco.get('streetNumber') or '',
        'complement': endereco.get('complement') or '',
        'neighborhood': endereco.get('neighborhood') or '',
        'city': endereco.get('city') or '',
        'state': endereco.get('state') or '',
        'zip_code': endereco.get('postalCode') or '',
        'reference': endereco.get('reference') or '',
        'formatted': endereco.get('formattedAddress') or '',
        **({'lat': lat, 'lng': lng} if lat is not None and lng is not None else {}),
    }


def _descontos(beneficios) -> tuple[Decimal, Decimal]:
    """(desconto total, parte bancada pelo iFood)."""
    total = Decimal('0.00')
    do_ifood = Decimal('0.00')
    for beneficio in beneficios or []:
        total += _reais(beneficio.get('value'))
        for patrocinio in beneficio.get('sponsorshipValues') or []:
            if str(patrocinio.get('name') or '').upper() == 'IFOOD':
                do_ifood += _reais(patrocinio.get('value'))
    return total, min(do_ifood, total)


def receber_pedido_novo(store, dados: dict):
    """Cria o pedido a partir do detalhe do iFood. Repetido devolve o mesmo."""
    from apps.stores.models import StoreOrder, StoreOrderItem

    order_id = dados.get('id')
    if not order_id:
        raise ErroDoIfood('Pedido do iFood sem id.')

    with transaction.atomic():
        existente = pedido_do_ifood(store, order_id)
        if existente:
            return existente, False

        totais = dados.get('total') or {}
        pagamentos = dados.get('payments') or {}
        metodos = pagamentos.get('methods') or []
        entrega = dados.get('delivery') or {}
        cliente = dados.get('customer') or {}
        telefone = cliente.get('phone') or {}

        retirada = str(dados.get('orderType') or '').upper() != 'DELIVERY'
        entrega_do_ifood = not retirada and str(entrega.get('deliveredBy') or '').upper() == 'IFOOD'
        dinheiro = next((m for m in metodos if str(m.get('method') or '').upper() == 'CASH'), None)
        pendente = _reais(pagamentos.get('pending'))
        pago_online = pendente == 0 and dinheiro is None

        subtotal = _reais(totais.get('subTotal'))
        frete = _reais(totais.get('deliveryFee'))
        desconto, do_ifood = _descontos(dados.get('benefits'))
        if not desconto and totais.get('benefits'):
            desconto = _reais(totais.get('benefits'))
        total = _reais(totais.get('orderAmount')) if totais.get('orderAmount') is not None else max(
            subtotal + frete - desconto, Decimal('0.00'))

        notas = []
        if telefone.get('number'):
            notas.append(f"Ligar para {telefone['number']}"
                         + (f" código {telefone['localizer']}" if telefone.get('localizer') else ''))
        if entrega.get('pickupCode'):
            notas.append(f"Código de coleta: {entrega['pickupCode']}")
        if entrega.get('observations'):
            notas.append(str(entrega['observations']))

        troco = None
        if dinheiro:
            troco_para = (dinheiro.get('cash') or {}).get('changeFor')
            troco = _reais(troco_para) if troco_para else None

        pedido = StoreOrder.objects.create(
            store=store,
            customer_name=(str(cliente.get('name') or '').strip() or 'Cliente iFood')[:255],
            customer_phone='',
            status=StoreOrder.OrderStatus.PENDING,
            payment_status=StoreOrder.PaymentStatus.PAID if pago_online else StoreOrder.PaymentStatus.PENDING,
            paid_at=timezone.now() if pago_online else None,
            payment_method='cash' if dinheiro else PROVEDOR,
            change_for=troco,
            subtotal=subtotal,
            discount=desconto,
            platform_discount=do_ifood,
            delivery_fee=frete,
            total=total,
            delivery_method=StoreOrder.DeliveryMethod.PICKUP if retirada else StoreOrder.DeliveryMethod.DELIVERY,
            delivery_address={} if retirada else _endereco(entrega.get('deliveryAddress') or {}),
            delivery_notes=' | '.join(notas),
            customer_notes=str((dados.get('extraInfo') or '')),
            external_delivery_provider=PROVEDOR if entrega_do_ifood else '',
            external_delivery_id=str(order_id) if entrega_do_ifood else '',
            source=PROVEDOR,
            metadata={
                'source': PROVEDOR,
                # O cliente é do iFood e recebe os avisos dele; o telefone é virtual.
                'suppress_notifications': True,
                PROVEDOR: {
                    'order_id': str(order_id),
                    'numero': str(dados.get('displayId') or '') or None,
                    'tipo': str(dados.get('orderType') or ''),
                    'agendado': str(dados.get('orderTiming') or '') == 'SCHEDULED',
                    'quem_entrega': 'entregador do iFood' if entrega_do_ifood else (
                        'cliente retira' if retirada else 'entrega da loja'),
                    'codigo_coleta': str(entrega.get('pickupCode') or ''),
                    'merchant_id': str((dados.get('merchant') or {}).get('id') or ''),
                    'confirmado': False,
                    'financeiro': {
                        'venda_cardapio': str(subtotal),
                        'desconto_total': str(desconto),
                        'desconto_plataforma': str(do_ifood),
                        'desconto_loja': str(desconto - do_ifood),
                    },
                },
            },
        )
        for item in dados.get('items') or []:
            qtd = max(int(Decimal(str(item.get('quantity') or 1))), 1)
            linha = _reais(item.get('totalPrice'))
            StoreOrderItem.objects.create(
                order=pedido,
                product=_produto(store, item.get('externalCode')),
                product_name=str(item.get('name') or 'Item iFood')[:255],
                variant_name=_texto_das_opcoes(item.get('options'))[:255],
                sku=str(item.get('externalCode') or '')[:100],
                unit_price=(linha / qtd).quantize(Decimal('0.01')),
                quantity=qtd,
                subtotal=linha,
                notes=str(item.get('observations') or ''),
                options={'origem': PROVEDOR},
            )

        pk = pedido.pk
        transaction.on_commit(lambda: imprimir_depois(pk))
        transaction.on_commit(lambda: confirmar_depois(pk))
    logger.info('ifood: pedido %s (iFood #%s) entrou na loja %s',
                pedido.order_number, dados.get('displayId'), store.slug)
    return pedido, True


# ── Eventos do iFood → pedido ─────────────────────────────────────────────

def _registrar(pedido, **campos):
    metadata = dict(pedido.metadata or {})
    dados = dict(metadata.get(PROVEDOR) or {})
    dados.update(campos)
    metadata[PROVEDOR] = dados
    pedido.metadata = metadata
    pedido.save(update_fields=['metadata', 'updated_at'])


def aplicar_evento(store, evento: dict) -> bool:
    """Aplica um evento do polling. Levanta ErroDoIfood se precisa tentar de novo."""
    from apps.stores.models import StoreOrder

    codigo = str(evento.get('code') or '').upper()
    order_id = evento.get('orderId')

    if codigo == PEDIDO_NOVO:
        if pedido_do_ifood(store, order_id):
            return False
        detalhe = _chamar(store, 'GET', f'/order/v1.0/orders/{order_id}')
        if not isinstance(detalhe, dict):
            raise ErroDoIfood(f'Pedido {order_id} sem detalhe.')
        _, criado = receber_pedido_novo(store, detalhe)
        return criado

    pedido = pedido_do_ifood(store, order_id)
    if pedido is None:
        return False
    agora = timezone.now()
    finais = (StoreOrder.OrderStatus.DELIVERED, StoreOrder.OrderStatus.COMPLETED,
              StoreOrder.OrderStatus.CANCELLED)

    if codigo == CANCELADO:
        if pedido.status != StoreOrder.OrderStatus.CANCELLED:
            pedido.status = StoreOrder.OrderStatus.CANCELLED
            pedido.cancelled_at = agora
            pedido.cancel_reason = 'Cancelado no iFood'
            pedido.save(update_fields=['status', 'cancelled_at', 'cancel_reason', 'updated_at'])
        _registrar(pedido, cancelado_no_ifood=True)
    elif codigo == CONCLUIDO:
        if pedido.status not in finais:
            pedido.status = StoreOrder.OrderStatus.DELIVERED
            pedido.delivered_at = agora
            pedido.save(update_fields=['status', 'delivered_at', 'updated_at'])
    elif codigo == CONFIRMADO:
        _registrar(pedido, confirmado=True)
    elif codigo == CANCELAMENTO_PEDIDO:
        _registrar(pedido, pedido_do_cliente={'tipo': 'cancelamento', 'em': agora.isoformat()})
    elif codigo == CANCELAMENTO_NEGADO:
        _registrar(pedido, ultimo_erro='O iFood negou o cancelamento pedido pela loja.')
    else:
        return False
    from apps.stores.services import realtime_service
    transaction.on_commit(lambda: realtime_service.broadcast_order_event(pedido))
    return True


def processar_eventos_da_loja(store) -> dict:
    """Um ciclo de polling: busca, aplica e dá ACK no que deu certo."""
    resultado = {'eventos': 0, 'pedidos_novos': 0, 'falhas': 0}
    integracao = _integracao(store)
    if integracao is None or not integracao.conectado:
        return resultado

    cabecalhos = {'x-polling-merchants': integracao.merchant_id} if integracao.merchant_id else None
    try:
        eventos = _chamar(store, 'GET', '/order/v1.0/events:polling', cabecalhos=cabecalhos) or []
    except ErroDoIfood as exc:
        logger.warning('ifood: polling de %s falhou: %s', store.slug, exc)
        return resultado
    if not isinstance(eventos, list) or not eventos:
        return resultado

    resultado['eventos'] = len(eventos)
    reconhecer = []
    for evento in eventos:
        try:
            with transaction.atomic():
                if aplicar_evento(store, evento) and str(evento.get('code') or '').upper() == PEDIDO_NOVO:
                    resultado['pedidos_novos'] += 1
        except Exception as exc:  # sem ACK: o iFood manda de novo no próximo ciclo
            resultado['falhas'] += 1
            logger.warning('ifood: evento %s (%s) de %s falhou: %s',
                           evento.get('id'), evento.get('code'), store.slug, exc)
            continue
        if evento.get('id'):
            reconhecer.append({'id': evento['id']})

    if reconhecer:
        try:
            _chamar(store, 'POST', '/order/v1.0/events/acknowledgment', corpo=reconhecer)
        except ErroDoIfood as exc:
            # Sem ACK os eventos voltam; o pedido novo é idempotente pelo order_id.
            logger.warning('ifood: ACK de %s falhou: %s', store.slug, exc)
    return resultado


# ── Painel → iFood ────────────────────────────────────────────────────────

def _executar(pedido, acao: str, corpo=None):
    order_id = dados_ifood(pedido).get('order_id')
    try:
        resultado = _chamar(pedido.store, 'POST', f'/order/v1.0/orders/{order_id}/{acao}', corpo=corpo)
    except ErroDoIfood as exc:
        _registrar(pedido, ultimo_erro=f'{acao}: {exc}'[:500], ultimo_erro_em=timezone.now().isoformat())
        logger.warning('ifood: %s do pedido %s falhou: %s', acao, pedido.order_number, exc)
        raise
    _registrar(pedido, ultimo_erro='')
    return resultado


def confirmar(pedido):
    if dados_ifood(pedido).get('confirmado'):
        return
    _executar(pedido, 'confirm')
    _registrar(pedido, confirmado=True)
    if pedido.status in ('pending', 'processing', 'paid'):
        from apps.stores.models import StoreOrder
        pedido.status = StoreOrder.OrderStatus.CONFIRMED
        pedido.confirmed_at = timezone.now()
        pedido.save(update_fields=['status', 'confirmed_at', 'updated_at'])


def _codigo_de_cancelamento(pedido, motivo: str) -> tuple[str, str]:
    order_id = dados_ifood(pedido).get('order_id')
    opcoes = _chamar(pedido.store, 'GET', f'/order/v1.0/orders/{order_id}/cancellationReasons') or []
    if not isinstance(opcoes, list) or not opcoes:
        raise ErroDoIfood('O iFood não ofereceu motivo de cancelamento para este pedido.')
    texto = (motivo or '').lower()
    for gatilhos, trecho in _MOTIVOS:
        if any(g in texto for g in gatilhos):
            for opcao in opcoes:
                if trecho in str(opcao.get('description') or '').lower():
                    return str(opcao.get('cancelCodeId')), str(opcao.get('description'))
    primeira = opcoes[0]
    return str(primeira.get('cancelCodeId')), str(primeira.get('description'))


def avisar_status(pedido, novo_status: str, motivo: str = ''):
    """Leva para o iFood o que o painel fez com um pedido dele."""
    dados = dados_ifood(pedido)
    if pedido.source != PROVEDOR or not dados.get('order_id'):
        return
    retirada = str(dados.get('tipo') or '').upper() != 'DELIVERY'
    if novo_status == 'confirmed':
        confirmar(pedido)
    elif novo_status == 'preparing':
        confirmar(pedido)
        _executar(pedido, 'startPreparation')
    elif novo_status == 'ready':
        confirmar(pedido)
        if retirada:
            _executar(pedido, 'readyToPickup')
    elif novo_status in ('out_for_delivery', 'shipped'):
        confirmar(pedido)
        if not retirada:
            _executar(pedido, 'dispatch')
    elif novo_status == 'cancelled':
        if dados.get('cancelado_no_ifood'):
            return
        codigo, descricao = _codigo_de_cancelamento(pedido, motivo)
        _executar(pedido, 'requestCancellation', corpo={
            'reason': (motivo or descricao or 'Cancelado pela loja')[:250],
            'cancellationCode': codigo,
        })


# ── Fila (Celery) ─────────────────────────────────────────────────────────

def imprimir_depois(order_pk):
    from apps.stores.models import StoreOrder
    from apps.stores.services.print_service import enqueue_order_print_job
    try:
        enqueue_order_print_job(StoreOrder.objects.get(pk=order_pk))
    except Exception:
        logger.exception('ifood: comanda do pedido %s não foi para a fila', order_pk)


def confirmar_depois(order_pk):
    from apps.stores.tasks import confirmar_pedido_do_ifood
    confirmar_pedido_do_ifood.delay(str(order_pk))


def avisar_status_depois(order_pk, novo_status: str, motivo: str = ''):
    from apps.stores.tasks import avisar_status_ao_ifood
    avisar_status_ao_ifood.delay(str(order_pk), novo_status, motivo or '')
