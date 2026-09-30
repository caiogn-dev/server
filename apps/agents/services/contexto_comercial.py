"""Promoções, entrega, pagamento, fidelidade e horário — o que vale AGORA.

O cardápio dizia nome e preço. A loja tinha promoção por dia da semana, frete
grátis por raio, zona com preço fixo, vale-refeição, cashback, carimbo de
fidelidade e horário — tudo cadastrado, nada no prompt. A IA respondia "não
temos promoção do dia" com a promoção no ar (28/09/2026).

Funções puras sobre a loja e o instante. Tudo aqui é DADO do sistema: o que
não estiver cadastrado não aparece, e o texto diz para não inventar.
"""
from decimal import Decimal

from apps.agents.services.contexto_da_loja import texto_de_agora, texto_do_horario

_DIAS_PT = ('Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo')


def _reais(valor) -> str:
    try:
        return f"R$ {Decimal(str(valor)):.2f}".replace('.', ',')
    except Exception:
        return f"R$ {valor}"


def _numero(valor):
    try:
        d = Decimal(str(valor))
    except Exception:
        return None
    return int(d) if d == d.to_integral_value() else d


def promocoes(store, agora) -> str:
    from apps.stores.models import StoreProduct

    produtos = list(
        StoreProduct.disponiveis(store)
        .exclude(tags__contains=['ingrediente'])
        .only('name', 'price', 'promo_price', 'promo_weekday', 'compare_at_price')
    )
    hoje = agora.weekday()
    por_dia: dict[int, list] = {}
    for p in produtos:
        if p.promo_price is not None and p.promo_weekday is not None and p.promo_price < p.price:
            por_dia.setdefault(int(p.promo_weekday), []).append(p)
    ofertas = [p for p in produtos if p.compare_at_price and p.compare_at_price > p.price]

    linhas = []
    de_hoje = por_dia.get(hoje) or []
    if de_hoje:
        linhas.append(f"🔥 PROMOÇÃO DE HOJE ({_DIAS_PT[hoje].lower()}):")
        linhas.extend(f"• {p.name} — {_reais(p.promo_price)} (de {_reais(p.price)})" for p in de_hoje)
    else:
        linhas.append(f"Nenhuma promoção do dia hoje ({_DIAS_PT[hoje].lower()}).")
    if por_dia:
        linhas.append("Promoções da semana (cada uma vale SÓ no dia):")
        for dia in range(7):
            if dia in por_dia:
                itens = ", ".join(f"{p.name} {_reais(p.promo_price)}" for p in por_dia[dia])
                linhas.append(f"• {_DIAS_PT[dia]}: {itens}")
    if ofertas:
        linhas.append("Ofertas (preço de/por, todo dia):")
        linhas.extend(f"• {p.name} — {_reais(p.price)} (de {_reais(p.compare_at_price)})" for p in ofertas)
    if not por_dia and not ofertas:
        linhas = ["Nenhuma promoção cadastrada no momento."]
    linhas.append(
        "Não invente promoção, cupom ou desconto além destes. Se o cliente citar uma "
        "promoção que não está aqui (stories, panfleto), diga que vai confirmar com a equipe."
    )
    return "\n".join(linhas)


def condicoes_de_entrega(store) -> str:
    meta = getattr(store, 'metadata', None) or {}
    linhas = []
    if getattr(store, 'delivery_enabled', True):
        fg = meta.get('frete_gratis') or {}
        if isinstance(fg, dict) and fg.get('ativo'):
            ate = _numero(fg.get('ate_km'))
            minimo = _numero(fg.get('pedido_minimo'))
            regra = f"Frete GRÁTIS até {ate} km de rota" if ate else "Frete GRÁTIS"
            if minimo:
                regra += f" em pedidos a partir de {_reais(minimo)}"
            linhas.append(f"• {regra}.")
        zonas = [z for z in (meta.get('fixed_price_zones') or []) if isinstance(z, dict) and z.get('name')]
        if zonas:
            linhas.append("• Regiões com taxa fixa: " + "; ".join(
                f"{z['name']} {_reais(z.get('fee'))}" for z in zonas if z.get('fee') is not None
            ) + ".")
        maximo = _numero(meta.get('delivery_max_distance'))
        if maximo:
            linhas.append(f"• Entregamos até {maximo} km da loja; além disso, só retirada.")
        linhas.append("• Fora dessas regras a taxa depende do endereço: peça a localização para calcular.")
    else:
        linhas.append("• A loja NÃO faz entrega: apenas retirada.")
    endereco = (getattr(store, 'address', '') or '').strip()
    if getattr(store, 'pickup_enabled', True) and endereco:
        linhas.append(f"• Retirada na loja: {endereco}.")
    return "\n".join(linhas)


_NOMES_DE_PAGAMENTO = {
    'pix': 'PIX (o código vem ao fechar o pedido)',
    'credit_card': 'cartão de crédito pelo link do pedido',
    'cash': 'pagar na entrega ou na retirada (dinheiro ou maquininha)',
}


def formas_de_pagamento(store) -> str:
    try:
        from apps.stores.api.views.storefront_views import build_store_payment_config
        config = build_store_payment_config(store)
    except Exception:
        return ''
    metodos = config.get('enabled_methods') or []
    partes = [_NOMES_DE_PAGAMENTO[m] for m in metodos if m in _NOMES_DE_PAGAMENTO]
    marcas = [b.get('label') for b in (config.get('pagarme') or {}).get('brands') or [] if b.get('label')]
    marcas += [b.get('label') for b in (config.get('cielo') or {}).get('brands') or [] if b.get('label')]
    marcas += [b.get('label') for b in (config.get('vale_por_link') or {}).get('brands') or [] if b.get('label')]
    if marcas:
        vale = "vale-refeição/alimentação (" + ", ".join(dict.fromkeys(marcas)) + ")"
        taxa = config.get('voucher_fee_percent') or 0
        if taxa:
            vale += f" com acréscimo de {_numero(taxa)}%"
        partes.append(vale)
    if not partes:
        return ''
    return "• Aceitamos: " + "; ".join(partes) + "."


def fidelidade(store) -> str:
    meta = getattr(store, 'metadata', None) or {}
    linhas = []
    pct = _numero(meta.get('cashback_percent'))
    if meta.get('cashback_enabled') and pct:
        linhas.append(f"• Cashback: {pct}% de cada pedido volta como crédito para a próxima compra.")
    exigidas = _numero(meta.get('loyalty_salads_required'))
    if meta.get('loyalty_enabled') and exigidas:
        rotulo = (meta.get('loyalty_item_label_plural') or 'itens').strip()
        onde = ''
        ids = meta.get('loyalty_qualifying_categories') or []
        if ids:
            try:
                from apps.stores.models import StoreCategory
                nomes = list(StoreCategory.objects.filter(store=store, id__in=ids).values_list('name', flat=True))
                if nomes:
                    onde = f" (valem: {', '.join(nomes)})"
            except Exception:
                onde = ''
        linhas.append(f"• Fidelidade: a cada {exigidas} {rotulo}{onde}, 1 grátis. O cliente vê os carimbos no site.")
    # "Teste do dono: paga R$ 1 e recebe R$ 2" foi anunciado em prod (28/09).
    tiers = [
        t for t in (meta.get('carteira_tiers') or [])
        if isinstance(t, dict) and t.get('nome') and 'teste' not in str(t.get('nome')).lower()
    ]
    if tiers:
        pacotes = "; ".join(f"{t['nome']}: paga {_reais(t.get('paga'))} e recebe {_reais(t.get('credito'))}" for t in tiers)
        linhas.append(f"• Carteira pré-paga (crédito com bônus): {pacotes}.")
    return "\n".join(linhas)


def contexto_comercial(store, agora) -> str:
    """O bloco inteiro, para o prompt. Cada parte só entra se existir."""
    blocos = [("PROMOÇÕES", promocoes(store, agora))]
    horario = texto_do_horario(store)
    agora_txt = texto_de_agora(store, agora)
    if horario or agora_txt:
        blocos.append(("HORÁRIO", "\n".join(x for x in (agora_txt, horario) if x)))
    blocos.append(("ENTREGA", condicoes_de_entrega(store)))
    pagamento = formas_de_pagamento(store)
    if pagamento:
        blocos.append(("PAGAMENTO", pagamento))
    fid = fidelidade(store)
    if fid:
        blocos.append(("FIDELIDADE E CRÉDITOS", fid))
    return "\n\n".join(f"{titulo}:\n{texto}" for titulo, texto in blocos if texto)
