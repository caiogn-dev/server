"""Impacto do programa de fidelidade: quanto custa e se está fazendo alguém voltar.

A tela de Fidelidade era um formulário: "10 itens = 1 grátis" e nada sobre o
custo, nem se funcionava. Aqui estão os números que respondem "quanto custa e
está valendo a pena", dos últimos 90 dias.

Fontes (nenhum campo novo):
- pedidos pagos = `StoreOrder` com `payment_status='paid'` e `created_at` na
  janela (a mesma régua do faturamento; `paid_at` fica nulo em pedido antigo);
- carimbos = `StoreLoyaltyTransaction` EARN da janela;
- custo real do brinde = `StoreOrder.metadata['loyalty_reward']` (`discount` ÷
  `count`), gravado pelo checkout quando o brinde vira desconto;
- participantes = `StoreLoyaltyAccount` com carimbo/resgate + telefones com
  `StoreCashbackLot`.

"Por mês" é o total da janela ÷ 3. Número sem base volta `None`, nunca zero:
zero diz "custa R$ 0", nulo diz "sem dados ainda".
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q
from django.utils import timezone

from apps.core.pii import mask_phone
from apps.core.utils import normalize_phone_number
from apps.stores.metrics import apenas_receita, soma_de_venda
from apps.stores.models import (
    StoreCashbackLot, StoreLoyaltyAccount, StoreLoyaltyTransaction, StoreOrder,
)
from apps.stores.services.cashback_service import CashbackService
from apps.stores.services.loyalty_service import LoyaltyService

JANELA_DIAS = 90
MESES_NA_JANELA = Decimal(JANELA_DIAS) / Decimal(30)
AMOSTRA_MINIMA = 30
LIMITE_A_UM_ITEM = 10


def _tel(bruto) -> str:
    """Chave de identidade pelo telefone. Nunca levanta."""
    digitos = ''.join(ch for ch in str(bruto or '') if ch.isdigit())
    if not digitos:
        return ''
    try:
        return normalize_phone_number(digitos) or digitos
    except Exception:
        return digitos


def _dinheiro(valor):
    return None if valor is None else round(float(valor), 2)


def _taxa(recompraram: int, total: int):
    return None if total == 0 else round(recompraram / total, 3)


def _telefone_do_usuario(user) -> str:
    # O mesmo critério da listagem de contas (perfil ou `cliente_<fone>`).
    from apps.stores.api.views.loyalty_views import _user_phone
    return _user_phone(user)


def calcular_impacto(store) -> dict:
    agora = timezone.now()
    desde = agora - timedelta(days=JANELA_DIAS)
    threshold, _ligado = LoyaltyService._config(store)

    pagos = apenas_receita(StoreOrder.objects.filter(store=store, created_at__gte=desde))
    agg = pagos.aggregate(n=Count('id'), receita=soma_de_venda())
    n_pedidos = agg['n']
    receita = agg['receita']
    ticket_medio = (receita / n_pedidos) if n_pedidos else None
    receita_mes = receita / MESES_NA_JANELA

    # ── Quem participa ──────────────────────────────────────────────────
    contas = (StoreLoyaltyAccount.objects
              .filter(store=store)
              .filter(Q(qualified_count__gt=0) | Q(redeemed_count__gt=0))
              .select_related('user', 'user__profile'))
    ids_participantes = set()
    identidades = set()
    tels_participantes = set()
    for conta in contas:
        ids_participantes.add(conta.user_id)
        tel = _tel(_telefone_do_usuario(conta.user))
        if tel:
            tels_participantes.add(tel)
            identidades.add(tel)
        else:
            identidades.add(f'u:{conta.user_id}')
    for bruto in (StoreCashbackLot.objects.filter(store=store)
                  .values_list('phone', flat=True).distinct()):
        tel = _tel(bruto)
        if tel:
            tels_participantes.add(tel)
            identidades.add(tel)

    # ── Recompra: clientes com 2+ pedidos pagos ÷ clientes com 1+ ──────
    por_cliente = {}   # chave -> [pedidos, participante?]
    for customer_id, telefone in pagos.values_list('customer_id', 'customer_phone'):
        tel = _tel(telefone)
        chave = tel or (f'u:{customer_id}' if customer_id else None)
        if not chave:
            continue
        linha = por_cliente.setdefault(chave, [0, False])
        linha[0] += 1
        if customer_id in ids_participantes or (tel and tel in tels_participantes):
            linha[1] = True
    part = [n for n, p in por_cliente.values() if p]
    nao_part = [n for n, p in por_cliente.values() if not p]

    # ── Projeção do carimbo ─────────────────────────────────────────────
    carimbos = StoreLoyaltyTransaction.objects.filter(
        account__store=store, kind=StoreLoyaltyTransaction.Kind.EARN, created_at__gte=desde,
    ).aggregate(t=Coalesce(Sum('quantity'), 0))['t']
    carimbos_mes = Decimal(carimbos) / MESES_NA_JANELA
    brindes_mes = carimbos_mes / Decimal(threshold)

    brindes_resgatados = 0
    desconto_resgatado = Decimal('0')
    for meta in pagos.filter(metadata__loyalty_reward__applied=True).values_list('metadata', flat=True):
        reward = (meta or {}).get('loyalty_reward') or {}
        try:
            desconto_resgatado += Decimal(str(reward.get('discount') or 0))
            brindes_resgatados += int(reward.get('count') or 1)
        except Exception:
            continue
    if brindes_resgatados and desconto_resgatado > 0:
        custo_brinde = desconto_resgatado / brindes_resgatados
        origem = 'resgates'
    else:
        custo_brinde = ticket_medio
        origem = 'ticket_medio' if ticket_medio is not None else None
    custo_mes = (brindes_mes * custo_brinde) if custo_brinde is not None else None

    # ── Cashback ────────────────────────────────────────────────────────
    percentual = Decimal(str(CashbackService.percent(store) or 0))
    saldo_mes = receita_mes * percentual / Decimal(100)

    # ── A um item do brinde ─────────────────────────────────────────────
    from apps.stores.api.views.loyalty_views import _falta_para_o_brinde
    a_um = (StoreLoyaltyAccount.objects.filter(store=store, qualified_count__gt=0)
            .annotate(_falta=_falta_para_o_brinde(threshold))
            .filter(_falta=1)
            .select_related('user', 'user__profile')
            .order_by('-qualified_count', '-updated_at'))

    return {
        'janela_dias': JANELA_DIAS,
        'pedidos_pagos': n_pedidos,
        'ticket_medio': _dinheiro(ticket_medio),
        'pedidos_por_mes': round(float(n_pedidos / MESES_NA_JANELA), 1),
        'receita_paga_mes': _dinheiro(receita_mes),
        'amostra_suficiente': n_pedidos >= AMOSTRA_MINIMA,
        'pedidos_faltando': max(0, AMOSTRA_MINIMA - n_pedidos),
        'participantes': len(identidades),
        'taxa_recompra_participantes': _taxa(sum(1 for n in part if n >= 2), len(part)),
        'taxa_recompra_nao_participantes': _taxa(sum(1 for n in nao_part if n >= 2), len(nao_part)),
        'itens_para_ganhar': threshold,
        'carimbos_por_mes': round(float(carimbos_mes), 1),
        'brindes_por_mes_projetados': round(float(brindes_mes), 1),
        'custo_por_brinde': _dinheiro(custo_brinde),
        'custo_por_brinde_origem': origem,
        'custo_projetado_mes': _dinheiro(custo_mes),
        'cashback_percentual': float(percentual),
        'saldo_gerado_mes': _dinheiro(saldo_mes),
        'a_um_item_total': a_um.count(),
        'a_um_item': [
            {
                'id': str(conta.user_id),
                'nome': conta.user.get_full_name() or conta.user.username,
                'telefone': mask_phone(_telefone_do_usuario(conta.user)),
                'faltam': 1,
            }
            for conta in a_um[:LIMITE_A_UM_ITEM]
        ],
    }
