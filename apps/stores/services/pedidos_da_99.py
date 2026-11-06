"""Pedidos da 99Food dentro do Cardapidex.

O pedido feito no app da 99 cai no mesmo quadro, na mesma comanda e nos mesmos
relatórios dos pedidos do site. O que o painel faz com ele (pronto, entregue,
cancelado) volta para a 99 pela API.

Contrato (developer-food.99app.com, lido em 03/11/2026):
- `orderNew` traz o pedido inteiro. A loja tem 5 MINUTOS para confirmar, senão a
  99 cancela sozinha — por isso confirmamos logo que o pedido entra.
- Preço é inteiro em centavos.
- `delivery_type`: 0 cliente retira, 1 entregador da 99, 2 entrega da loja.
  "Entregue" só existe na API para a entrega da loja.
- Toda ação leva o `auth_token` da loja, que sai de GET /v1/auth/authtoken/get
  com app_id + app_secret + app_shop_id e vence numa data aleatória
  (errno 10102 = vencido → /refresh e buscar de novo).
- IDs de pedido são inteiros de 64 bits: guardados como texto e mandados como
  int, nunca float.
"""
from __future__ import annotations

import logging
from decimal import Decimal

import requests
from requests import RequestException
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

BASE = 'https://openapi.99food.com/v1'
CHAVE_DA_LOJA = 'app_shop_id_99'
PROVEDOR = '99food'
TOKEN_VENCIDO = 10102
TIMEOUT = 8

# Motivo que o dono escolhe no painel → código de cancelamento da 99.
_MOTIVOS = (
    ('acab', 1010), ('esgot', 1010), ('falt', 1010),
    ('fechad', 1020),
    ('ocupad', 1030), ('cheia', 1030), ('movimento', 1030),
    ('entregador', 1060), ('motoboy', 1060),
    ('fora da área', 1071), ('fora da area', 1071), ('longe', 1071),
    ('trote', 1073), ('fraude', 1073),
)
MOTIVO_OUTRO = 1080


class ErroDa99(Exception):
    pass


# ── Loja ──────────────────────────────────────────────────────────────────

def app_shop_id(store) -> str:
    metadata = store.metadata if isinstance(store.metadata, dict) else {}
    return str(metadata.get(CHAVE_DA_LOJA) or store.slug)


def loja_do_aviso(codigo):
    from apps.stores.models import Store
    codigo = str(codigo or '').strip()
    if not codigo:
        return None
    loja = Store.objects.filter(**{f'metadata__{CHAVE_DA_LOJA}': codigo}).first()
    return loja or Store.objects.filter(slug=codigo).first()


# ── API ───────────────────────────────────────────────────────────────────

def _credenciais():
    app_id = str(getattr(settings, 'NINETY_NINE_APP_ID', '') or '').strip()
    segredo = str(getattr(settings, 'NINETY_NINE_APP_SECRET', '') or '').strip()
    if not app_id or not segredo:
        raise ErroDa99('Credenciais da 99Food não configuradas.')
    return app_id, segredo


def _ler(resposta) -> dict:
    try:
        corpo = resposta.json()
    except ValueError as exc:
        raise ErroDa99(f'Resposta inválida da 99 (HTTP {resposta.status_code}).') from exc
    if not isinstance(corpo, dict):
        raise ErroDa99('Resposta inválida da 99.')
    return corpo


def _chave_do_token(store) -> str:
    return f'99food:token:{store.pk}'


def token_da_loja(store, renovar: bool = False) -> str:
    chave = _chave_do_token(store)
    if not renovar:
        guardado = cache.get(chave)
        if guardado:
            return guardado
    app_id, segredo = _credenciais()
    params = {'app_id': app_id, 'app_secret': segredo, 'app_shop_id': app_shop_id(store)}
    if renovar:
        _ler(requests.get(f'{BASE}/auth/authtoken/refresh', params=params, timeout=TIMEOUT))
    corpo = _ler(requests.get(f'{BASE}/auth/authtoken/get', params=params, timeout=TIMEOUT))
    if corpo.get('errno') != 0:
        raise ErroDa99(f"Token da 99 recusado: {corpo.get('errmsg') or corpo.get('errno')}")
    dados = corpo.get('data') or {}
    token = dados.get('auth_token') or ''
    if not token:
        raise ErroDa99('A 99 não devolveu token para esta loja.')
    vence = int(dados.get('token_expiration_time') or 0)
    # Margem de 5 min: token vencido no meio da confirmação perde o pedido.
    duracao = max(60, min(vence - int(timezone.now().timestamp()) - 300, 6 * 3600)) if vence else 3600
    cache.set(chave, token, duracao)
    return token


def _acao(store, acao: str, order_id, **extra):
    url = f'{BASE}/order/order/{acao}'
    for tentativa in (0, 1):
        corpo = _ler(requests.post(
            url, json={'auth_token': token_da_loja(store, renovar=bool(tentativa)),
                       'order_id': int(order_id), **extra},
            timeout=TIMEOUT,
        ))
        if corpo.get('errno') == TOKEN_VENCIDO and not tentativa:
            continue
        if corpo.get('errno') != 0:
            raise ErroDa99(f"99 recusou '{acao}': {corpo.get('errmsg') or corpo.get('errno')}")
        return corpo.get('data')
    raise ErroDa99(f"99 recusou '{acao}': token vencido")


# ── Pedido ────────────────────────────────────────────────────────────────

def _reais(centavos) -> Decimal:
    try:
        return (Decimal(int(centavos or 0)) / 100).quantize(Decimal('0.01'))
    except (TypeError, ValueError, ArithmeticError):
        return Decimal('0.00')


def dados_99(order) -> dict:
    metadata = order.metadata if isinstance(order.metadata, dict) else {}
    dados = metadata.get(PROVEDOR)
    return dados if isinstance(dados, dict) else {}


def pedido_da_99(store, order_id):
    from apps.stores.models import StoreOrder
    return StoreOrder.objects.filter(
        store=store, source=PROVEDOR, **{f'metadata__{PROVEDOR}__order_id': str(order_id)},
    ).first()


def _texto_dos_adicionais(sub_itens) -> str:
    partes = []
    for sub in sub_itens or []:
        nome = str(sub.get('name') or '').strip()
        if not nome:
            continue
        qtd = int(sub.get('amount') or 1)
        partes.append(f'{qtd}x {nome}' if qtd > 1 else nome)
        internos = _texto_dos_adicionais(sub.get('sub_item_list'))
        if internos:
            partes.append(internos)
    return ', '.join(partes)


def _produto(store, codigo):
    from apps.stores.models import StoreProduct
    codigo = str(codigo or '').strip()
    if not codigo:
        return None
    filtro = StoreProduct.objects.filter(store=store)
    try:
        return filtro.filter(id=codigo).first() or filtro.filter(sku=codigo).first()
    except Exception:  # id que não é UUID
        return filtro.filter(sku=codigo).first()


def _endereco(cliente: dict, lat, lng) -> dict:
    return {
        'street': cliente.get('street_name') or cliente.get('poi_display_name') or '',
        'number': cliente.get('street_number') or cliente.get('house_number') or '',
        'complement': cliente.get('complement') or '',
        'neighborhood': cliente.get('district') or '',
        'city': cliente.get('city') or '',
        'state': cliente.get('state') or '',
        'zip_code': cliente.get('postal_code') or '',
        'reference': cliente.get('reference') or '',
        'formatted': cliente.get('poi_address') or cliente.get('formatted_address') or '',
        **({'lat': lat, 'lng': lng} if lat is not None and lng is not None else {}),
    }


# O "#16" do app da 99. A doc chama de `order_index`, mas o 1º pedido real
# (05/11) chegou ao painel sem número: lemos variações e o nível de fora também.
_CHAVES_DO_NUMERO = (
    'order_index', 'orderIndex', 'order_seq', 'daily_order_index', 'day_seq',
    'order_number', 'display_order_id', 'short_order_id',
)


def numero_do_pedido(info: dict, dados: dict | None = None):
    for fonte in (info, dados or {}, info.get('order') if isinstance(info.get('order'), dict) else {}):
        for chave in _CHAVES_DO_NUMERO:
            valor = fonte.get(chave)
            if valor in (None, '', 0, '0'):
                continue
            texto = str(valor).strip().lstrip('#')
            if texto.isdigit() and len(texto) <= 6:
                return int(texto)
    return None


_QUEM_ENTREGA = {0: 'cliente retira', 1: 'entregador da 99', 2: 'entrega da loja'}


# ── Financeiro ────────────────────────────────────────────────────────────
#
# Regra do dono (plano 06/11, item 1.4): faturamento = preço de cardápio;
# desconto da 99 fica à parte e não reduz receita; desconto da loja reduz;
# comissão e taxas = venda − recebido; recebido = o que caiu no repasse.
#
# Até 06/11 o aviso de teste e o 1º real só trouxeram order_price,
# items_discount, delivery_price, delivery_discount e real_pay_price — nada
# diz quem pagou o desconto nem quanto a loja recebe. Os nomes abaixo são os
# que a 99 (DiDi Food) costuma usar para isso; se vier um deles, ele manda.
# O que não vier fica None, e o recebido chega pelo extrato de repasse
# (`repasse_99`). O bloco price inteiro fica guardado para reprocessar quando
# soubermos o nome real (scripts/precos_dos_pedidos_99.py mostra o bloco).
_CHAVES_DESCONTO_LOJA = (
    # Medido em 06/11: o aviso traz `shop_paid_money` (0 nos 6 pedidos, todo o
    # desconto foi da 99). É o único campo que separa a parte da loja.
    'shop_paid_money',
    'shop_subsidy_price', 'shop_subsidy', 'shop_discount', 'shop_discount_price',
    'merchant_subsidy', 'merchant_subsidy_price', 'merchant_discount', 'store_discount',
)
_CHAVES_DESCONTO_99 = (
    'platform_subsidy_price', 'platform_subsidy', 'platform_discount', 'platform_discount_price',
    'didi_subsidy', 'didi_discount',
)
_CHAVES_RECEBIDO = (
    'shop_income', 'shop_income_price', 'merchant_income', 'shop_settlement_price',
    'settlement_price', 'shop_receivable', 'shop_receive_price',
)


def _primeiro(preco: dict, chaves):
    for chave in chaves:
        valor = preco.get(chave)
        if valor is not None and valor != '':
            return _reais(valor)
    return None


def _texto(valor):
    return None if valor is None else str(valor)


def financeiro_do_preco(preco: dict) -> dict:
    """Separa o bloco `price` da 99 nas colunas do relatório (em texto, 2 casas)."""
    preco = preco if isinstance(preco, dict) else {}
    venda = _reais(preco.get('order_price')) if preco.get('order_price') is not None else None
    desconto = _reais(preco.get('items_discount')) + _reais(preco.get('delivery_discount'))
    da_loja = _primeiro(preco, _CHAVES_DESCONTO_LOJA)
    da_99 = _primeiro(preco, _CHAVES_DESCONTO_99)
    if da_loja is not None and da_99 is None:
        da_99 = max(desconto - da_loja, Decimal('0.00'))
    elif da_99 is not None and da_loja is None:
        da_loja = max(desconto - da_99, Decimal('0.00'))
    recebido = _primeiro(preco, _CHAVES_RECEBIDO)
    # O aviso traz comissão e taxa de serviço, mas a soma NÃO é o custo do
    # canal: no 99 #5 de 06/11 deram 2,85 + 1,16 e a loja perdeu 22,37 (venda
    # 39,99, recebido 17,62). O custo real só sai do extrato (venda − recebido).
    comissao = venda - recebido if recebido is not None and venda is not None else None
    outras = preco.get('others_fees') if isinstance(preco.get('others_fees'), dict) else {}
    taxa_servico = _reais(outras['service_price']) if outras.get('service_price') is not None else None
    return {
        'venda_cardapio': _texto(venda),
        'desconto_total': _texto(desconto),
        'desconto_plataforma': _texto(da_99),
        'desconto_loja': _texto(da_loja),
        'comissao_taxas': _texto(comissao),
        'recebido': _texto(recebido),
        'fonte_recebido': 'aviso' if recebido is not None else None,
        'comissao_99': _texto(_primeiro(preco, ('commission_price', 'commission'))),
        'taxa_servico': _texto(taxa_servico),
        'entrega_cobrada_da_loja': _texto(_primeiro(preco, ('store_charged_delivery_price',))),
        'preco': dict(preco),
    }


def desconto_da_plataforma(financeiro: dict) -> Decimal:
    """Quanto do desconto não sai da receita da loja.

    Sem dono declarado no aviso, o desconto conta como da 99: no extrato de
    06/11 a loja recebeu R$ 17,62 de um pedido que o cliente pagou R$ 8,00 —
    quem bancou foi a 99. Se o aviso disser a parte da loja, ela reduz receita.
    """
    if financeiro.get('desconto_plataforma') is not None:
        return Decimal(financeiro['desconto_plataforma'])
    if financeiro.get('desconto_loja') is not None:
        return max(Decimal(financeiro['desconto_total'] or '0') - Decimal(financeiro['desconto_loja']),
                   Decimal('0.00'))
    return Decimal(financeiro.get('desconto_total') or '0')


def receber_pedido_novo(store, dados: dict):
    """Cria o pedido a partir do `orderNew`. Aviso repetido devolve o mesmo pedido."""
    from apps.stores.models import StoreOrder, StoreOrderItem

    info = dados.get('order_info') if isinstance(dados.get('order_info'), dict) else dados
    order_id = info.get('order_id') or dados.get('order_id')
    if not order_id:
        raise ErroDa99('orderNew sem order_id.')

    with transaction.atomic():
        existente = pedido_da_99(store, order_id)
        if existente:
            return existente, False

        preco = info.get('price') or {}
        cliente = info.get('receive_address') or {}
        retirada = int(info.get('fulfillment_mode') or 0) == 1 or int(info.get('delivery_type') or 0) == 0
        entrega_da_99 = int(info.get('delivery_type') or 0) == 1
        dinheiro = int(info.get('pay_type') or 0) == 2 or int(info.get('pay_channel') or 0) == 153
        online = int(info.get('pay_method') or 0) == 1 and not dinheiro

        subtotal = _reais(preco.get('order_price'))
        desconto = _reais(preco.get('items_discount')) + _reais(preco.get('delivery_discount'))
        frete = _reais(preco.get('delivery_price'))
        # `total` = o que o cliente paga (caixa, troco, cobrança). A venda de
        # cardápio volta pela `platform_discount` — ver financeiro_do_preco.
        total = _reais(preco.get('real_pay_price')) if preco.get('real_pay_price') else None
        if total is None:
            total = max(subtotal + frete - desconto, Decimal('0.00'))
        financeiro = financeiro_do_preco(preco)

        nome = (cliente.get('name') or ' '.join(
            p for p in (cliente.get('first_name'), cliente.get('last_name')) if p) or 'Cliente 99Food')
        if 'privacy' in nome.lower():
            nome = (cliente.get('first_name') or '').replace('privacy protection', '').strip() or 'Cliente 99Food'

        telefone_virtual = cliente.get('virtual_phone_number') or ''
        ramal = cliente.get('locator') or ''
        lat, lng = cliente.get('poi_lat'), cliente.get('poi_lng')
        notas_entrega = []
        if telefone_virtual:
            notas_entrega.append(f'Ligar para {telefone_virtual}' + (f' ramal {ramal}' if ramal else ''))
        if info.get('handover_code'):
            notas_entrega.append(f"Código de entrega: {info['handover_code']}")
        if info.get('takeaway_code'):
            notas_entrega.append(f"Código de retirada: {info['takeaway_code']}")

        numero = numero_do_pedido(info, dados)
        if numero is None:
            logger.warning('99food: pedido %s sem número curto; campos: %s', order_id, sorted(info.keys()))
        pedido = StoreOrder.objects.create(
            store=store,
            customer_name=nome[:255],
            customer_phone='',
            status=StoreOrder.OrderStatus.PENDING,
            payment_status=(StoreOrder.PaymentStatus.PAID if online else StoreOrder.PaymentStatus.PENDING),
            paid_at=timezone.now() if online else None,
            payment_method='cash' if dinheiro else PROVEDOR,
            change_for=_reais(info.get('change_for')) if dinheiro and info.get('change_for') else None,
            subtotal=subtotal,
            discount=desconto,
            platform_discount=min(desconto_da_plataforma(financeiro), desconto),
            delivery_fee=frete,
            total=total,
            delivery_method=(StoreOrder.DeliveryMethod.PICKUP if retirada else StoreOrder.DeliveryMethod.DELIVERY),
            delivery_address={} if retirada else _endereco(cliente, lat, lng),
            delivery_notes=' | '.join(notas_entrega),
            customer_notes=str(info.get('remark') or ''),
            external_delivery_provider=PROVEDOR if entrega_da_99 else '',
            external_delivery_id=str(order_id) if entrega_da_99 else '',
            source=PROVEDOR,
            metadata={
                'source': PROVEDOR,
                # O cliente é da 99 e recebe os avisos dela; o número que vem é
                # mascarado ou virtual.
                'suppress_notifications': True,
                PROVEDOR: {
                    'order_id': str(order_id),
                    'numero': numero,
                    'delivery_type': int(info.get('delivery_type') or 0),
                    'pay_channel': info.get('pay_channel'),
                    'precisa_talher': bool(info.get('need_cutlery')),
                    'quem_entrega': _QUEM_ENTREGA.get(int(info.get('delivery_type') or 0), ''),
                    'codigo_entrega': str(info.get('handover_code') or ''),
                    'codigo_retirada': str(info.get('takeaway_code') or ''),
                    'confirmado': False,
                    'financeiro': financeiro,
                },
            },
        )
        for item in info.get('order_items') or []:
            qtd = max(int(item.get('amount') or 1), 1)
            linha = _reais(item.get('total_price'))
            StoreOrderItem.objects.create(
                order=pedido,
                product=_produto(store, item.get('app_item_id')),
                product_name=str(item.get('name') or 'Item 99Food')[:255],
                variant_name=_texto_dos_adicionais(item.get('sub_item_list'))[:255],
                sku=str(item.get('app_item_id') or '')[:100],
                unit_price=(linha / qtd).quantize(Decimal('0.01')),
                quantity=qtd,
                subtotal=linha,
                notes=str(item.get('remark') or ''),
                options={'origem': PROVEDOR},
            )

        pk = pedido.pk
        transaction.on_commit(lambda: imprimir_depois(pk))
        transaction.on_commit(lambda: confirmar_depois(pk))
    logger.info('99food: pedido %s (99 #%s) entrou na loja %s', pedido.order_number, order_id, store.slug)
    return pedido, True


def _registrar(pedido, **campos):
    metadata = dict(pedido.metadata or {})
    dados = dict(metadata.get(PROVEDOR) or {})
    dados.update(campos)
    metadata[PROVEDOR] = dados
    pedido.metadata = metadata
    pedido.save(update_fields=['metadata', 'updated_at'])


def _executar(pedido, acao: str, **extra):
    order_id = dados_99(pedido).get('order_id')
    try:
        resultado = _acao(pedido.store, acao, order_id, **extra)
    except (ErroDa99, RequestException) as exc:
        _registrar(pedido, ultimo_erro=f'{acao}: {exc}'[:500], ultimo_erro_em=timezone.now().isoformat())
        logger.warning('99food: %s do pedido %s falhou: %s', acao, pedido.order_number, exc)
        raise ErroDa99(str(exc)) from exc
    _registrar(pedido, ultimo_erro='')
    return resultado


def confirmar(pedido):
    if dados_99(pedido).get('confirmado'):
        return
    _executar(pedido, 'confirm')
    _registrar(pedido, confirmado=True)
    if pedido.status in ('pending', 'processing', 'paid'):
        from apps.stores.models import StoreOrder
        pedido.status = StoreOrder.OrderStatus.CONFIRMED
        pedido.confirmed_at = timezone.now()
        pedido.save(update_fields=['status', 'confirmed_at', 'updated_at'])


def _codigo_do_motivo(motivo: str) -> int:
    texto = (motivo or '').lower()
    for trecho, codigo in _MOTIVOS:
        if trecho in texto:
            return codigo
    return MOTIVO_OUTRO


def avisar_status(pedido, novo_status: str, motivo: str = ''):
    """Leva para a 99 o que o painel fez com um pedido dela."""
    dados = dados_99(pedido)
    if pedido.source != PROVEDOR or not dados.get('order_id'):
        return
    if novo_status in ('confirmed', 'preparing'):
        confirmar(pedido)
    elif novo_status == 'ready':
        if not dados.get('confirmado'):
            confirmar(pedido)
        _executar(pedido, 'ready')
    elif novo_status in ('delivered', 'completed'):
        if int(dados.get('delivery_type') or 0) == 2:
            _executar(pedido, 'delivered')
    elif novo_status == 'cancelled':
        if dados.get('cancelado_na_99'):
            return
        codigo = _codigo_do_motivo(motivo)
        _executar(pedido, 'cancel', reason_id=codigo,
                  reason=(motivo or 'Cancelado pela loja')[:200])


# ── Avisos da 99 → pedido ─────────────────────────────────────────────────

def aplicar_aviso(store, tipo: str, dados) -> bool:
    """Atualiza o pedido pelo aviso da 99. Não manda nada de volta."""
    from apps.stores.models import StoreOrder

    if not isinstance(dados, dict):
        return False
    pedido = pedido_da_99(store, dados.get('order_id'))
    if pedido is None:
        return False
    agora = timezone.now()
    if tipo == 'orderCancel':
        if pedido.status != StoreOrder.OrderStatus.CANCELLED:
            pedido.status = StoreOrder.OrderStatus.CANCELLED
            pedido.cancelled_at = agora
            pedido.cancel_reason = 'Cancelado na 99Food'
            pedido.save(update_fields=['status', 'cancelled_at', 'cancel_reason', 'updated_at'])
        _registrar(pedido, cancelado_na_99=True)
    elif tipo == 'orderFinish':
        if pedido.status not in (StoreOrder.OrderStatus.DELIVERED, StoreOrder.OrderStatus.COMPLETED,
                                 StoreOrder.OrderStatus.CANCELLED):
            pedido.status = StoreOrder.OrderStatus.DELIVERED
            pedido.delivered_at = agora
            pedido.save(update_fields=['status', 'delivered_at', 'updated_at'])
    elif tipo in ('orderConfirm', 'orderConfirmed'):
        _registrar(pedido, confirmado=True)
    elif tipo == 'deliveryStatus':
        situacao = str(dados.get('delivery_status') or dados.get('status') or '')[:30]
        if situacao:
            pedido.external_delivery_status = situacao
            pedido.save(update_fields=['external_delivery_status', 'updated_at'])
    elif tipo in ('orderCancelApply', 'orderRefundApply'):
        _registrar(pedido, pedido_do_cliente={
            'tipo': 'cancelamento' if tipo == 'orderCancelApply' else 'reembolso',
            'motivo': str(dados.get('apply_reason') or '')[:300],
            'apply_id': str(dados.get('apply_id') or ''),
            'em': agora.isoformat(),
        })
    else:
        return False
    from apps.stores.services import realtime_service
    transaction.on_commit(lambda: realtime_service.broadcast_order_event(pedido))
    return True


# ── Fila (Celery) ─────────────────────────────────────────────────────────

def imprimir_depois(order_pk):
    from apps.stores.models import StoreOrder
    from apps.stores.services.print_service import enqueue_order_print_job
    try:
        enqueue_order_print_job(StoreOrder.objects.get(pk=order_pk))
    except Exception:
        logger.exception('99food: comanda do pedido %s não foi para a fila', order_pk)


def confirmar_depois(order_pk):
    from apps.stores.tasks import confirmar_pedido_da_99
    confirmar_pedido_da_99.delay(str(order_pk))


def avisar_status_depois(order_pk, novo_status: str, motivo: str = ''):
    from apps.stores.tasks import avisar_status_a_99
    avisar_status_a_99.delay(str(order_pk), novo_status, motivo or '')
