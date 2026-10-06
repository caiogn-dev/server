"""Reajuste de preço em massa: somar ou reduzir, em R$ ou %, nos itens escolhidos.

Pedido do dono (06/10), visto no Prefiro. Antes, reajustar o cardápio era abrir
produto por produto. Regras:
- tudo ou nada: se algum preço ficaria R$ 0 ou negativo, nada é gravado;
- variantes com preço próprio seguem a mesma regra;
- avisa promoção que fica igual/acima do preço novo e "de" (compare_at) que fica abaixo;
- guarda o último reajuste para desfazer — só item que ninguém mexeu depois.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

CENTAVO = Decimal('0.01')
CHAVE = 'ultimo_reajuste_de_preco'
MAX_ITENS = 1000


class ReajusteInvalido(ValueError):
    def __init__(self, mensagem, recusados=None):
        super().__init__(mensagem)
        self.recusados = recusados or []


def _ler_valor(bruto) -> Decimal:
    try:
        valor = Decimal(str(bruto).replace(',', '.'))
    except (InvalidOperation, TypeError, ValueError):
        raise ReajusteInvalido('Informe um valor numérico.')
    if not valor.is_finite() or valor <= 0:
        raise ReajusteInvalido('O valor precisa ser maior que zero.')
    return valor


def _novo_preco(antes: Decimal, operacao: str, modo: str, valor: Decimal) -> Decimal:
    if modo == 'percentual':
        fator = (Decimal(100) + valor) / 100 if operacao == 'acrescentar' else (Decimal(100) - valor) / 100
        novo = antes * fator
    else:
        novo = antes + valor if operacao == 'acrescentar' else antes - valor
    return novo.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _avisos(produto, depois: Decimal) -> list:
    avisos = []
    if produto.promo_price is not None and produto.promo_price >= depois:
        avisos.append(f'A promoção (R$ {produto.promo_price}) fica igual ou acima do preço novo.')
    if produto.compare_at_price is not None and produto.compare_at_price <= depois:
        avisos.append(f'O preço "de" (R$ {produto.compare_at_price}) fica abaixo do preço novo.')
    return avisos


def reajustar(loja, ids, operacao: str, modo: str, valor, previa: bool = False, usuario=None) -> dict:
    from apps.stores.models import StoreProduct

    if operacao not in ('acrescentar', 'reduzir'):
        raise ReajusteInvalido('Operação deve ser acrescentar ou reduzir.')
    if modo not in ('valor', 'percentual'):
        raise ReajusteInvalido('Modo deve ser valor (R$) ou percentual (%).')
    valor = _ler_valor(valor)
    if modo == 'percentual' and operacao == 'reduzir' and valor >= 100:
        raise ReajusteInvalido('Reduzir 100% ou mais zera o preço.')
    if modo == 'percentual' and valor > 1000:
        raise ReajusteInvalido('Percentual alto demais — confira o valor.')
    ids = [str(i) for i in (ids or [])][:MAX_ITENS]
    if not ids:
        raise ReajusteInvalido('Escolha ao menos um produto.')

    with transaction.atomic():
        produtos = list(
            StoreProduct.objects.select_for_update()
            .filter(store=loja, id__in=ids).prefetch_related('variants').order_by('name')
        )
        if not produtos:
            raise ReajusteInvalido('Nenhum dos produtos escolhidos é desta loja.')

        itens, recusados = [], []
        for p in produtos:
            depois = _novo_preco(p.price, operacao, modo, valor)
            variantes = [
                (v, v.price, _novo_preco(v.price, operacao, modo, valor))
                for v in p.variants.all() if v.price is not None
            ]
            if depois <= 0 or any(nv <= 0 for _, _, nv in variantes):
                recusados.append({'id': str(p.id), 'nome': p.name, 'antes': str(p.price)})
                continue
            itens.append({
                'produto': p, 'antes': p.price, 'depois': depois, 'variantes': variantes,
                'avisos': _avisos(p, depois),
            })

        if recusados:
            raise ReajusteInvalido('Alguns preços ficariam zerados ou negativos.', recusados)

        resposta = {
            'aplicado': not previa,
            'itens': [
                {
                    'id': str(i['produto'].id), 'nome': i['produto'].name,
                    'antes': str(i['antes']), 'depois': str(i['depois']), 'avisos': i['avisos'],
                    'variantes': [{'nome': v.name, 'antes': str(a), 'depois': str(d)} for v, a, d in i['variantes']],
                }
                for i in itens
            ],
        }
        if previa:
            return resposta

        registro = []
        for i in itens:
            p = i['produto']
            p.price = i['depois']
            p.save(update_fields=['price', 'updated_at'])  # save(): sinais (catálogo da Meta etc.)
            for v, antes, depois in i['variantes']:
                v.price = depois
                v.save(update_fields=['price'])
            registro.append({
                'id': str(p.id), 'antes': str(i['antes']), 'depois': str(i['depois']),
                'variantes': {str(v.id): [str(a), str(d)] for v, a, d in i['variantes']},
            })

        meta = dict(loja.metadata or {})
        meta[CHAVE] = {
            'quando': timezone.now().isoformat(),
            'por': getattr(usuario, 'id', None),
            'descricao': f"{'+' if operacao == 'acrescentar' else '−'}{valor}{'%' if modo == 'percentual' else ' R$'}",
            'itens': registro,
        }
        loja.metadata = meta
        loja.save(update_fields=['metadata', 'updated_at'])
        return resposta


def desfazer(loja) -> dict:
    """Volta o último reajuste. Item editado depois (preço ≠ o que o reajuste pôs) fica como está."""
    from apps.stores.models import StoreProduct
    from apps.stores.models.product import StoreProductVariant

    with transaction.atomic():
        loja = type(loja).objects.select_for_update().get(pk=loja.pk)
        ultimo = (loja.metadata or {}).get(CHAVE)
        if not ultimo:
            raise ReajusteInvalido('Não há reajuste para desfazer.')
        desfeitos, mantidos = [], []
        produtos = {str(p.id): p for p in StoreProduct.objects.select_for_update().filter(
            store=loja, id__in=[i['id'] for i in ultimo['itens']])}
        for item in ultimo['itens']:
            p = produtos.get(item['id'])
            if p is None:
                continue
            if p.price != Decimal(item['depois']):
                mantidos.append(p.name)
                continue
            p.price = Decimal(item['antes'])
            p.save(update_fields=['price', 'updated_at'])
            for vid, (antes, depois) in (item.get('variantes') or {}).items():
                StoreProductVariant.objects.filter(pk=vid, product=p, price=Decimal(depois)).update(price=Decimal(antes))
            desfeitos.append(p.name)
        meta = dict(loja.metadata or {})
        meta.pop(CHAVE, None)
        loja.metadata = meta
        loja.save(update_fields=['metadata', 'updated_at'])
    return {'desfeitos': desfeitos, 'mantidos': mantidos}
