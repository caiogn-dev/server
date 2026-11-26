"""Pedidos do iFood dentro do Cardapidex.

Mesmo desenho da 99Food (`pedidos_da_99`): o pedido do app cai no mesmo quadro,
na mesma comanda e nos mesmos relatórios, e o que o painel faz com ele volta
para o iFood pela API.

A diferença é a entrada. A 99 avisa por webhook; o iFood espera POLLING:

- GET /events/v1.0/events:polling a cada 30 s. É também o que mantém a loja
  "aberta" no app do iFood — parar o polling fecha a loja lá.
- ACK em POST /events/v1.0/events/acknowledgment de TODO evento recebido, até
  os que ignoramos; evento sem ACK volta no polling seguinte. Por isso evento
  que FALHOU ao processar fica sem ACK de propósito: é o retry de graça.
- O evento traz só código + orderId; o pedido inteiro vem de
  GET /order/v1.0/orders/{id}.
- Valores em REAIS com casas decimais (a 99 manda centavos).
- Pedido não confirmado o iFood cancela sozinho: confirmamos logo que entra.

Token da plataforma (app centralizado, `ifood_oauth.api('pedidos', ...)`).
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

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
EM_PREPARO = 'PRS'
CANCELAMENTO_PEDIDO = 'CAR'
CANCELAMENTO_NEGADO = 'CARF'
NEGOCIACAO = 'HSD'
NEGOCIACAO_RESOLVIDA = 'HSS'

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

    App centralizado: o token é o da plataforma (`ifood_oauth.api('pedidos')`);
    a loja só precisa ter o `merchant_id` informado e o app aprovado no portal.
    Devolve o JSON, ou None quando o iFood responde sem corpo (202/204).
    """
    if not ifood_oauth.token_valido(store):
        raise ErroDoIfood('Loja sem acesso ao iFood (sem ID da loja ou app sem credencial).')
    try:
        return ifood_oauth.api('pedidos', metodo, caminho, corpo=corpo, cabecalhos=cabecalhos, timeout=TIMEOUT)
    except (ifood_oauth.IfoodRecusou, ifood_oauth.IfoodNaoConfigurado) as exc:
        raise ErroDoIfood(str(exc)) from exc


def _integracao(store):
    from apps.stores.models import StoreIfoodIntegration
    return StoreIfoodIntegration.objects.filter(store=store).first()


def _marca(store, merchant_id) -> str:
    """Marca da rede de onde veio o pedido ('' = o restaurante principal)."""
    integracao = _integracao(store)
    return integracao.marca(merchant_id) if integracao is not None else ''


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


def _brl(valor: Decimal) -> str:
    return f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


_METODOS = {'CREDIT': 'Crédito', 'DEBIT': 'Débito', 'MEAL_VOUCHER': 'Vale-refeição',
            'FOOD_VOUCHER': 'Vale-alimentação', 'PIX': 'PIX', 'CASH': 'Dinheiro',
            'DIGITAL_WALLET': 'Carteira digital'}


def _notas_de_pagamento(metodos, troco, beneficios, totais) -> list:
    notas = []
    for m in metodos or []:
        nome = _METODOS.get(str(m.get('method') or '').upper(), str(m.get('method') or '').title())
        bandeira = str((m.get('card') or {}).get('brand') or (m.get('wallet') or {}).get('name') or '').strip()
        quando = 'pago online' if str(m.get('type') or '').upper() == 'ONLINE' else 'cobrar na entrega'
        linha = f"{nome}{' ' + bandeira if bandeira else ''} ({quando}) {_brl(_reais(m.get('value')))}"
        if str(m.get('method') or '').upper() == 'CASH' and troco:
            falta = troco - _reais(m.get('value'))
            if falta > 0:
                linha += f' — troco de {_brl(falta)} (para {_brl(troco)})'
        notas.append(linha)
    for beneficio in beneficios or []:
        partes = []
        for patrocinio in beneficio.get('sponsorshipValues') or []:
            valor = _reais(patrocinio.get('value'))
            if valor <= 0:
                continue
            quem = 'iFood' if str(patrocinio.get('name') or '').upper() == 'IFOOD' else 'loja'
            partes.append(f'{quem} {_brl(valor)}')
        notas.append(f"Cupom {_brl(_reais(beneficio.get('value')))}" + (f" ({' · '.join(partes)})" if partes else ''))
    return notas


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

        # Critérios do iFood: bandeira, troco, cupom (quem paga) e CPF/CNPJ na comanda.
        notas.extend(_notas_de_pagamento(metodos, troco, dados.get('benefits'), totais))
        documento = str(cliente.get('documentNumber') or '').strip()
        if documento:
            notas.append(f'CPF/CNPJ na nota: {documento}')

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
                    'documento': documento,
                    'entrega_do_ifood': entrega_do_ifood,
                    'merchant_id': str((dados.get('merchant') or {}).get('id') or ''),
                    'marca': _marca(store, (dados.get('merchant') or {}).get('id')),
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


def _nossa_entrega_externa(store, order_id):
    from apps.stores.models import StoreOrder
    if not order_id:
        return None
    return StoreOrder.objects.filter(
        store=store, external_delivery_provider=PROVEDOR, external_delivery_id=str(order_id),
    ).exclude(source=PROVEDOR).first()


def _evento_do_entregador_pedido_pela_loja(pedido, evento: dict) -> bool:
    from apps.stores.services import entrega_ifood
    completo = str(evento.get('fullCode') or '').upper()
    meta = (pedido.metadata or {}).get(entrega_ifood.CHAVE_META) or {}
    return completo in entrega_ifood.LOGISTICOS and bool(meta.get('quote_id')) \
        and pedido.external_delivery_provider == PROVEDOR


def aplicar_evento(store, evento: dict) -> bool:
    """Aplica um evento do polling. Levanta ErroDoIfood se precisa tentar de novo."""
    from apps.stores.models import StoreOrder

    codigo = str(evento.get('code') or '').upper()
    order_id = evento.get('orderId')

    # A entrega que a LOJA criou no Shipping (pedido do site/WhatsApp) também
    # existe como pedido no iFood e gera PLC/CFM/CAN aqui. Não é pedido novo:
    # o que interessa dela vai para a entrega.
    nossa_entrega = _nossa_entrega_externa(store, order_id)
    if nossa_entrega is not None:
        from apps.stores.services import entrega_ifood
        completo = str(evento.get('fullCode') or '').upper()
        if completo in entrega_ifood.LOGISTICOS:
            return entrega_ifood.aplicar_evento(evento)
        return False

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
        info = _info_do_cancelamento(evento)
        cancelamento = dict(dados_ifood(pedido).get('cancelamento') or {})
        cancelamento.update({'status': 'CANCELADO', 'em': agora.isoformat(), **info})
        if pedido.status != StoreOrder.OrderStatus.CANCELLED:
            pedido.status = StoreOrder.OrderStatus.CANCELLED
            pedido.cancelled_at = agora
            pedido.cancel_reason = _texto_do_cancelamento(cancelamento)[:500]
            pedido.save(update_fields=['status', 'cancelled_at', 'cancel_reason', 'updated_at'])
        _registrar(pedido, cancelado_no_ifood=True, cancelamento=cancelamento)
        logger.info('ifood: pedido %s CANCELADO origem=%s codigo=%s motivo=%s', order_id,
                    cancelamento.get('origem'), cancelamento.get('codigo'), cancelamento.get('motivo'))
    elif codigo == CONCLUIDO:
        if pedido.status not in finais:
            pedido.status = StoreOrder.OrderStatus.DELIVERED
            pedido.delivered_at = agora
            pedido.save(update_fields=['status', 'delivered_at', 'updated_at'])
    elif codigo == CONFIRMADO:
        _registrar(pedido, confirmado=True)
    elif codigo in (EM_PREPARO, PRONTO, DESPACHADO):
        # Mudado no Gestor de Pedidos do iFood (ou eco do nosso): só avança.
        from apps.stores.services.status_da_plataforma import avancar
        retirada = str(dados_ifood(pedido).get('tipo') or '').upper() not in ('', 'DELIVERY')
        novo = {EM_PREPARO: 'preparing', PRONTO: 'ready',
                DESPACHADO: 'ready' if retirada else 'out_for_delivery'}[codigo]
        if not avancar(pedido, novo):
            return False
    elif codigo == CANCELAMENTO_PEDIDO:
        # CAR = o iFood recebeu o pedido de cancelamento DA LOJA e está processando.
        cancelamento = dict(dados_ifood(pedido).get('cancelamento') or {})
        if cancelamento.get('status') != 'CANCELADO':
            cancelamento.update({'status': 'EM_ANALISE', 'em': agora.isoformat()})
            _registrar(pedido, cancelamento=cancelamento)
        logger.info('ifood: pedido %s cancelamento EM_ANALISE codigo=%s', order_id, cancelamento.get('codigo'))
    elif codigo == CANCELAMENTO_NEGADO:
        info = _info_do_cancelamento(evento)
        cancelamento = dict(dados_ifood(pedido).get('cancelamento') or {})
        cancelamento.update({'status': 'NEGADO', 'em': agora.isoformat(),
                             'motivo_negado': info.get('motivo', '')})
        aviso = 'O iFood negou o cancelamento pedido pela loja.'
        if info.get('motivo'):
            aviso += f" {info['motivo']}"
        _registrar(pedido, cancelamento=cancelamento, ultimo_erro=aviso)
        logger.warning('ifood: pedido %s cancelamento NEGADO: %s', order_id, info.get('motivo'))
    elif codigo == NEGOCIACAO:
        disputa = evento.get('metadata') if isinstance(evento.get('metadata'), dict) else {}
        _registrar(pedido, disputa={
            'id': str(disputa.get('id') or ''),
            'status': 'ABERTA',
            'acao': str(disputa.get('action') or ''),
            'tipo': str(disputa.get('handshakeType') or ''),
            'mensagem': str(disputa.get('message') or ''),
            'expira_em': str(disputa.get('expiresAt') or ''),
            'se_nao_responder': str(disputa.get('timeoutAction') or ''),
            'motivos_aceite': list(disputa.get('acceptCancellationReasons') or []),
            'alternativas': list(disputa.get('alternatives') or []),
            'itens': list((disputa.get('metadata') or {}).get('items') or disputa.get('items') or []),
            'evidencias': [e.get('url') for e in (disputa.get('evidences') or []) if isinstance(e, dict)],
            'recebida_em': agora.isoformat(),
        })
    elif codigo == NEGOCIACAO_RESOLVIDA:
        resultado = evento.get('metadata') if isinstance(evento.get('metadata'), dict) else {}
        disputa = dict(dados_ifood(pedido).get('disputa') or {})
        if not disputa.get('id') or disputa.get('id') == resultado.get('disputeId'):
            disputa.update({'status': str(resultado.get('status') or 'RESOLVIDA'),
                            'resultado_motivo': str(resultado.get('reason') or ''),
                            'resolvida_em': agora.isoformat()})
            _registrar(pedido, disputa=disputa)
    elif _evento_do_entregador_pedido_pela_loja(pedido, evento):
        # Mesmo app nos dois pollings (homologação): o evento do entregador
        # que a loja pediu (requestDriver) pode chegar por aqui.
        from apps.stores.services import entrega_ifood
        return entrega_ifood.aplicar_evento(evento)
    else:
        return False
    from apps.stores.services import realtime_service
    transaction.on_commit(lambda: realtime_service.broadcast_order_event(pedido))
    return True


_ORIGENS = {'RESTAURANT': 'loja', 'MERCHANT': 'loja', 'CONSUMER': 'cliente', 'CUSTOMER': 'cliente',
            'IFOOD': 'iFood', 'LOGISTIC': 'iFood (entrega)'}


def _info_do_cancelamento(evento: dict) -> dict:
    """Quem cancelou e por quê, como vier no metadata do evento (chaves variam)."""
    meta = evento.get('metadata') if isinstance(evento.get('metadata'), dict) else {}
    plano = {str(k).upper(): v for k, v in meta.items()}
    def pegar(*nomes):
        for nome in nomes:
            if plano.get(nome) not in (None, ''):
                return str(plano[nome])
        return ''
    info = {
        'origem': pegar('CANCELLATION_ORIGIN', 'CANCEL_ORIGIN', 'ORIGIN'),
        'codigo': pegar('CANCEL_CODE', 'CANCELLATION_CODE', 'REASON_CODE'),
        'motivo': pegar('CANCEL_REASON', 'CANCELLATION_REASON', 'REASON', 'DESCRIPTION', 'DETAILS'),
    }
    return {k: v for k, v in info.items() if v}


def _texto_do_cancelamento(cancelamento: dict) -> str:
    quem = _ORIGENS.get(str(cancelamento.get('origem') or '').upper(), '')
    texto = 'Cancelado no iFood' + (f' pela {quem}' if quem in ('loja',) else f' pelo {quem}' if quem else '')
    motivo = cancelamento.get('motivo') or cancelamento.get('descricao') or ''
    if motivo:
        texto += f': {motivo}'
    if cancelamento.get('codigo'):
        texto += f" ({cancelamento['codigo']})"
    return texto


#: Até 100 lojas por chamada de polling (limite do iFood para x-polling-merchants).
LOJAS_POR_POLLING = 100
#: Evento que falha N vezes seguidas recebe ACK mesmo assim (senão volta para sempre).
TENTATIVAS_POR_EVENTO = 5


def _momento(evento) -> str:
    return str(evento.get('createdAt') or '')


def processar_eventos(lojas) -> dict:
    """Um ciclo de polling para várias lojas: busca, aplica em ordem e dá ACK."""
    from django.core.cache import cache

    resultado = {'eventos': 0, 'pedidos_novos': 0, 'falhas': 0}
    por_merchant = {}
    for store in lojas:
        integracao = _integracao(store)
        if integracao is not None and integracao.conectado:
            for merchant in integracao.todos_os_merchants():
                por_merchant[merchant] = store
    visiveis = set(ifood_oauth.merchants_do_app('pedidos', por_merchant))
    por_merchant = {m: loja for m, loja in por_merchant.items() if m in visiveis}
    if not por_merchant:
        return resultado
    lojas_ativas = list(por_merchant.values())
    merchants = [m for m in por_merchant if m]
    cabecalhos = {'x-polling-merchants': ','.join(merchants)} if merchants else None
    primeira = lojas_ativas[0]
    try:
        eventos = _chamar(primeira, 'GET', '/events/v1.0/events:polling', cabecalhos=cabecalhos) or []
    except ErroDoIfood as exc:
        logger.warning('ifood: polling de %s falhou: %s', ','.join(merchants) or primeira.slug, exc)
        return resultado
    if not isinstance(eventos, list) or not eventos:
        return resultado

    resultado['eventos'] = len(eventos)
    reconhecer = []
    for evento in sorted(eventos, key=_momento):
        evento_id = evento.get('id')
        store = por_merchant.get(str(evento.get('merchantId') or '')) or (
            lojas_ativas[0] if len(lojas_ativas) == 1 else None)
        if store is None:
            logger.warning('ifood: evento %s de merchant desconhecido %s — ACK sem aplicar',
                           evento_id, evento.get('merchantId'))
        elif ifood_oauth.evento_ja_visto(evento_id):
            pass
        else:
            try:
                with transaction.atomic():
                    if aplicar_evento(store, evento) and str(evento.get('code') or '').upper() == PEDIDO_NOVO:
                        resultado['pedidos_novos'] += 1
                ifood_oauth.lembrar_evento(evento_id)
                logger.info('ifood: evento %s %s pedido=%s loja=%s ok', evento_id, evento.get('code'),
                            evento.get('orderId'), store.slug)
            except Exception as exc:  # sem ACK: o iFood manda de novo no próximo ciclo
                resultado['falhas'] += 1
                chave = f'ifood:evento-falhas:{evento_id}'
                falhas = (cache.get(chave) or 0) + 1
                cache.set(chave, falhas, timeout=60 * 60 * 6)
                if falhas < TENTATIVAS_POR_EVENTO:
                    logger.warning('ifood: evento %s (%s) pedido=%s de %s falhou (%s/%s): %s',
                                   evento_id, evento.get('code'), evento.get('orderId'), store.slug,
                                   falhas, TENTATIVAS_POR_EVENTO, exc)
                    continue
                logger.error('ifood: evento %s (%s) pedido=%s desistido após %s falhas: %s',
                             evento_id, evento.get('code'), evento.get('orderId'), falhas, exc)
        if evento_id:
            reconhecer.append({'id': evento_id})

    if reconhecer:
        try:
            _chamar(primeira, 'POST', '/events/v1.0/events/acknowledgment', corpo=reconhecer)
        except ErroDoIfood as exc:
            # Sem ACK os eventos voltam; tudo é idempotente pelo eventId/orderId.
            logger.warning('ifood: ACK de %s eventos falhou: %s', len(reconhecer), exc)
    return resultado


def processar_eventos_da_loja(store) -> dict:
    return processar_eventos([store])


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
        _avisar_pronto(pedido)
    elif novo_status in ('out_for_delivery', 'shipped'):
        confirmar(pedido)
        # Entrega própria: o iFood exige "pronto" ANTES do despacho. Com o
        # entregador do iFood quem despacha é ele; a loja não manda dispatch.
        if not retirada and not dados.get('entrega_do_ifood', pedido.external_delivery_provider == PROVEDOR):
            _avisar_pronto(pedido)
            _executar(pedido, 'dispatch')
    elif novo_status == 'cancelled':
        if dados.get('cancelado_no_ifood') or (dados.get('cancelamento') or {}).get('status') in (
                'ENVIADO', 'EM_ANALISE', 'CANCELADO'):
            return
        codigo, descricao = _codigo_de_cancelamento(pedido, motivo)
        _executar(pedido, 'requestCancellation', corpo={
            'reason': (motivo or descricao or 'Cancelado pela loja')[:250],
            'cancellationCode': codigo,
        })


def _avisar_pronto(pedido):
    if dados_ifood(pedido).get('pronto_avisado'):
        return
    _executar(pedido, 'readyToPickup')
    _registrar(pedido, pronto_avisado=True)


def motivos_de_cancelamento(pedido) -> list:
    """Os motivos que o iFood aceita para ESTE pedido (o painel mostra ao lojista)."""
    order_id = dados_ifood(pedido).get('order_id')
    opcoes = _chamar(pedido.store, 'GET', f'/order/v1.0/orders/{order_id}/cancellationReasons') or []
    return [{'codigo': str(o.get('cancelCodeId')), 'descricao': str(o.get('description') or '')}
            for o in opcoes if isinstance(o, dict) and o.get('cancelCodeId') is not None]


def cancelar_no_ifood(pedido, codigo: str, detalhe: str = ''):
    """Pede ao iFood o cancelamento com o motivo que o lojista escolheu.

    Fluxo exigido na homologação: GET cancellationReasons → escolha → POST
    requestCancellation (202). O pedido NÃO é cancelado aqui: quem decide é o
    iFood, pelos eventos CAR (em análise) → CAN (cancelado) ou CARF (negado).
    """
    from apps.stores.models import StoreOrder
    if pedido.status == StoreOrder.OrderStatus.CANCELLED or dados_ifood(pedido).get('cancelado_no_ifood'):
        raise ErroDoIfood('Este pedido já está cancelado.')
    if (dados_ifood(pedido).get('cancelamento') or {}).get('status') in ('ENVIADO', 'EM_ANALISE'):
        raise ErroDoIfood('O cancelamento já foi pedido; aguardando o iFood.')
    motivos = {m['codigo']: m['descricao'] for m in motivos_de_cancelamento(pedido)}
    codigo = str(codigo or '')
    if codigo not in motivos:
        raise ErroDoIfood('Escolha um dos motivos do iFood.')
    _executar(pedido, 'requestCancellation', corpo={
        'reason': (detalhe or motivos[codigo])[:250], 'cancellationCode': codigo,
    })
    _registrar(pedido, cancelamento_solicitado=codigo, cancelamento={
        'status': 'ENVIADO', 'codigo': codigo, 'descricao': motivos[codigo],
        'detalhe': detalhe[:250], 'origem': 'RESTAURANT', 'pedido_em': timezone.now().isoformat(),
    })
    logger.info('ifood: pedido %s requestCancellation codigo=%s (%s) enviado; aguardando CAN/CARF',
                dados_ifood(pedido).get('order_id'), codigo, motivos[codigo])
    return pedido


#: Respostas da Plataforma de Negociação → endpoint.
_RESPOSTAS = {'aceitar': 'accept', 'recusar': 'reject', 'alternativa': 'alternative'}


def responder_disputa(pedido, resposta: str, motivo: str = '', detalhe: str = '',
                      tipo: str = '', valor_centavos: int | None = None, minutos: int | None = None):
    disputa = dict(dados_ifood(pedido).get('disputa') or {})
    if not disputa.get('id') or disputa.get('status') != 'ABERTA':
        raise ErroDoIfood('Não há negociação aberta neste pedido.')
    if resposta not in _RESPOSTAS:
        raise ErroDoIfood('Resposta inválida.')
    if resposta == 'aceitar':
        corpo = {'reason': motivo or (disputa.get('motivos_aceite') or ['CUSTOMER_SATISFACTION'])[0]}
        if detalhe:
            corpo['detailReason'] = detalhe[:250]
    elif resposta == 'recusar':
        corpo = {'reason': motivo or 'UNKNOWN_ISSUE'}
    else:
        tipo = (tipo or '').upper()
        if tipo in ('REFUND', 'BENEFIT'):
            if not valor_centavos or int(valor_centavos) <= 0:
                raise ErroDoIfood('Informe o valor da contraproposta.')
            corpo = {'type': tipo, 'metadata': {'amount': {'value': str(int(valor_centavos)), 'currency': 'BRL'}}}
        elif tipo == 'ADDITIONAL_TIME':
            if not minutos or int(minutos) <= 0:
                raise ErroDoIfood('Informe os minutos a mais.')
            corpo = {'type': tipo, 'metadata': {'additionalTimeInMinutes': int(minutos),
                                                'reason': motivo or 'HIGH_STORE_DEMAND'}}
        else:
            raise ErroDoIfood('Tipo de contraproposta inválido.')
    try:
        _chamar(pedido.store, 'POST', f"/order/v1.0/disputes/{disputa['id']}/{_RESPOSTAS[resposta]}", corpo=corpo)
    except ErroDoIfood as exc:
        _registrar(pedido, ultimo_erro=f'negociação: {exc}'[:500])
        raise
    disputa.update({'status': 'RESPONDIDA', 'resposta': resposta, 'respondida_em': timezone.now().isoformat()})
    _registrar(pedido, disputa=disputa, ultimo_erro='')
    return pedido


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
