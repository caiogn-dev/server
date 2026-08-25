"""Frete grátis por DISTÂNCIA DE ROTA, com pedido mínimo opcional.

`ate_km` é comparado com `cotacao['distance_km']`, que vem do Google
Directions — percurso real de carro, não linha reta. O círculo que o painel
desenha no mapa é só referência visual: 3 km de rota cobrem menos chão do que
3 km de raio, e num bairro cortado por avenida a diferença passa de 40%.

Mora no `metadata` da loja e é aplicado DEPOIS que a taxa já foi calculada,
para não existir uma segunda matemática de frete concorrendo com
`DeliveryQuoteService.calculate_dynamic_fee`.

    store.metadata['frete_gratis'] = {
        'ativo': True,
        'ate_km': 3,             # km de ROTA, medidos pelo Directions
        'pedido_minimo': 60,     # 0 ou ausente = sem mínimo
        'inicio': '2026-08-24T00:00:00-03:00',   # opcional
        'fim': '2026-08-31T23:59:59-03:00',      # opcional
    }

Regra que não pode ser quebrada: quem NÃO conhece o subtotal (o cardápio, um
card de vitrine) só pode ANUNCIAR a promoção — nunca zerar. Prometer frete
grátis na vitrine e cobrar no checkout é pior do que não ter promoção.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)


def _decimal(valor, padrao=None):
    if valor in (None, ''):
        return padrao
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        return padrao


def _dentro_da_janela(promo) -> bool:
    """Data torta no metadata não pode derrubar o frete da loja inteira."""
    agora = timezone.now()
    for chave, comparar in (('inicio', 'depois'), ('fim', 'antes')):
        bruto = promo.get(chave)
        if not bruto:
            continue
        momento = parse_datetime(str(bruto))
        if momento is None:
            logger.warning("frete_gratis: data '%s' ilegível em '%s' — ignorada", bruto, chave)
            continue
        if timezone.is_naive(momento):
            momento = timezone.make_aware(momento)
        if comparar == 'depois' and agora < momento:
            return False
        if comparar == 'antes' and agora > momento:
            return False
    return True


def promocao_de_frete(store):
    """Promoção ativa da loja, ou None."""
    metadata = getattr(store, 'metadata', None) or {}
    promo = metadata.get('frete_gratis') or {}
    if not promo.get('ativo'):
        return None

    ate_km = _decimal(promo.get('ate_km'), Decimal('0'))
    if not ate_km or ate_km <= 0:
        return None

    if not _dentro_da_janela(promo):
        return None

    return {
        'ate_km': ate_km,
        'pedido_minimo': _decimal(promo.get('pedido_minimo'), Decimal('0')) or Decimal('0'),
    }


def aplicar_frete_gratis(cotacao: dict, store, subtotal=None) -> dict:
    """Zera o frete da cotação quando a promoção vale, ou apenas a anuncia.

    `subtotal` None significa "ainda não sei o valor do pedido" — aí a
    promoção entra só como informação, com `pedido_minimo` e `aplicado=False`.
    """
    promo = promocao_de_frete(store)
    if not promo:
        return cotacao

    ate_km = promo['ate_km']
    minimo = promo['pedido_minimo']

    # Directions fora do ar faz a distância cair para linha reta (haversine),
    # que SUBESTIMA o percurso — endereço a 3,0 km de reta pode estar a 4 km de
    # rota. A promoção continua valendo (o cliente não paga por falha nossa),
    # mas a cotação carrega a marca para o painel e os logs não mentirem.
    aproximada = bool(cotacao.get('distancia_aproximada'))

    info = {
        'aplicado': False,
        'ate_km': float(ate_km),
        'pedido_minimo': float(minimo),
        'distancia_aproximada': aproximada,
    }

    distancia = _decimal(cotacao.get('distance_km'))
    frete_atual = _decimal(cotacao.get('fee'))

    dentro_do_raio = distancia is not None and distancia <= ate_km
    ha_frete_para_zerar = frete_atual is not None and frete_atual > 0
    disponivel = cotacao.get('available', True)

    if not dentro_do_raio or not ha_frete_para_zerar or not disponivel:
        cotacao['frete_gratis'] = info
        return cotacao

    if minimo > 0:
        if subtotal is None:
            cotacao['frete_gratis'] = info
            return cotacao
        subtotal = _decimal(subtotal, Decimal('0'))
        if subtotal < minimo:
            info['faltam'] = float((minimo - subtotal).quantize(Decimal('0.01')))
            cotacao['frete_gratis'] = info
            return cotacao

    if aproximada:
        logger.warning(
            "frete_gratis: loja %s zerou frete com distância ESTIMADA (%s km) — "
            "Directions indisponível",
            getattr(store, 'slug', getattr(store, 'id', '?')), distancia,
        )

    info['aplicado'] = True
    info['frete_original'] = float(frete_atual)
    cotacao['fee'] = 0.0
    cotacao['delivery_fee'] = 0.0
    cotacao['frete_gratis'] = info
    return cotacao


def promocao_para_vitrine(store) -> dict | None:
    """Bloco que o cardápio consome, ou None quando não há promoção ativa.

    A vitrine não pode zerar frete (não conhece o carrinho nem a distância),
    mas pode ANUNCIAR e mostrar quanto falta — é o que puxa o ticket.
    """
    promo = promocao_de_frete(store)
    if not promo:
        return None
    return {
        'ate_km': float(promo['ate_km']),
        'pedido_minimo': float(promo['pedido_minimo']),
    }


def subtotal_ou_none(carrinho):
    """Subtotal do carrinho como Decimal, ou None quando não dá para saber.

    None e zero são coisas diferentes aqui: zero é "carrinho vazio, não alcança
    o mínimo"; None é "não sei", e a promoção então só é anunciada. Devolver
    zero por engano faria a cotação afirmar que o cliente não alcançou o mínimo
    quando, na verdade, ninguém perguntou ao carrinho.
    """
    if carrinho is None:
        return None
    return _decimal(getattr(carrinho, 'subtotal', None))
