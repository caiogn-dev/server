"""De ONDE veio cada real de cashback — e para onde foi.

O dono abriu a ficha da MADU CACHEADA e não soube responder uma pergunta
simples: os R$ 3,13 dela vieram da compra DELA ou do cupom MADULASH que as
amigas usaram?

O banco sempre soube. O lote é `origin='referral'` e aponta para o pedido
CE-2609104664, que é da Juliane. O mesmo pedido gerou também um lote
`purchase` de R$ 1,88 — o cashback da própria Juliane. Duas linhas, dois
donos, uma venda. Nada disso aparecia em lugar nenhum.

Um programa de indicação que não diz QUEM indicou é só um desconto com nome
bonito: a loja não consegue agradecer quem trouxe cliente nem saber se o
programa funciona.

ENTRADAS E SAÍDAS JUNTAS. "Quanto eu tenho" só faz sentido ao lado de "o que
entrou e o que saiu" — separar em duas telas devolve o cliente à pergunta que
ele veio fazer.
"""
from apps.core.utils import phone_variants

#: Como cada origem se chama para quem lê. Vem do model (`Origin.choices`),
#: mas fixado aqui porque o rótulo é contrato de tela: mudar o texto do
#: `choices` não pode renomear coluna de extrato sem alguém decidir.
ROTULO_DA_ORIGEM = {
    'purchase': 'Compra própria',
    'referral': 'Indicação',
    'adjust': 'Ajuste manual',
    'prepaid': 'Carteira pré-paga',
}


def _pedido_resumido(order):
    """O mínimo para reconhecer o pedido — e, na indicação, QUEM comprou."""
    if order is None:
        return None
    return {
        'id': str(order.id),
        'numero': order.order_number,
        # O nome é o ponto da linha de indicação: "veio do pedido da Juliane".
        'cliente': order.customer_name or '',
        'total': str(order.total or '0.00'),
    }


def extrato_de_cashback(store, telefone: str) -> list:
    """Lançamentos do cliente, do mais novo para o mais velho.

    Aceita o telefone em qualquer grafia (com/sem o nono dígito, com/sem DDI):
    a mesma peneira que o resto do cashback usa.
    """
    from django.utils import timezone

    from apps.stores.models.cashback import StoreCashbackLot, StoreCashbackRedemption

    variantes = [p for p in phone_variants(telefone or '') if p]
    if not variantes:
        return []

    agora = timezone.now()
    linhas = []

    entradas = (
        StoreCashbackLot.objects
        .filter(store=store, phone__in=variantes)
        .select_related('order')
    )
    for lote in entradas:
        linhas.append({
            'tipo': 'entrada',
            'quando': lote.created_at.isoformat(),
            'origem': lote.origin,
            'rotulo': ROTULO_DA_ORIGEM.get(lote.origin, lote.origin),
            'valor': str(lote.amount),
            # Quanto ainda sobrou DESTE lote: o saldo é a soma disto, não dos
            # valores originais, e sem a coluna a conta não fecha na tela.
            'restante': str(lote.remaining),
            'pedido': _pedido_resumido(lote.order),
            # Crédito manual não tem pedido; o que identifica é o motivo.
            'referencia': lote.coupon_code or lote.source_ref or '',
            'vence_em': lote.expires_at.isoformat() if lote.expires_at else None,
            # Vencido SOME DO SALDO, não do extrato: o cliente pergunta "cadê
            # meus R$ 5" e a resposta é "venceram em tal dia".
            'vencido': bool(lote.expires_at and lote.expires_at <= agora),
        })

    saidas = (
        StoreCashbackRedemption.objects
        .filter(store=store, phone__in=variantes)
        .select_related('order')
    )
    for resgate in saidas:
        linhas.append({
            'tipo': 'saida',
            'quando': resgate.created_at.isoformat(),
            'origem': 'redemption',
            'rotulo': 'Usado no pedido',
            'valor': str(resgate.amount),
            'restante': None,
            'pedido': _pedido_resumido(resgate.order),
            'referencia': '',
            'vence_em': None,
            'vencido': False,
        })

    linhas.sort(key=lambda l: l['quando'], reverse=True)
    return linhas
