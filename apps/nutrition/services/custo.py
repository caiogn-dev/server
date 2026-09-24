"""Ficha técnica de custo: custo do prato, CMV e margem bruta.

Mesma filosofia de `incomplete_ingredients` no cálculo nutricional: nunca
inventar zero. Ingrediente sem preço deixa o custo do prato EM BRANCO e é
nomeado — um custo parcial mostraria margem maior do que a real, e é
exatamente esse o número em que o lojista confia para decidir o preço.
"""
from decimal import Decimal, ROUND_HALF_UP

CEM = Decimal("100")


def _q(valor, casas="0.01"):
    return valor.quantize(Decimal(casas), rounding=ROUND_HALF_UP) if valor is not None else None


def custo_por_g_ml(ingrediente):
    """Quanto custa 1 g (ou 1 ml) do ingrediente, na unidade da receita.

    A receita pesa na `default_unit` do ingrediente. Comprado na mesma
    unidade, é divisão direta; por unidade, usa o conteúdo de cada uma; entre
    g e ml, só com densidade — 1 ml de azeite não pesa 1 g, e supor que sim
    é inventar número. Sem como converter, devolve None.
    """
    preco, quantidade = ingrediente.preco_pago, ingrediente.quantidade_comprada
    if preco is None or not quantidade:
        return None
    base, compra = ingrediente.default_unit, ingrediente.unidade_compra
    densidade = ingrediente.density_g_ml
    if compra == base:
        na_base = quantidade
    elif compra == "un":
        na_base = quantidade * ingrediente.quantidade_por_unidade if ingrediente.quantidade_por_unidade else None
    elif compra == "ml" and base == "g" and densidade:
        na_base = quantidade * densidade
    elif compra == "g" and base == "ml" and densidade:
        na_base = quantidade / densidade
    else:
        na_base = None
    return preco / na_base if na_base else None


def custo_dos_itens(itens, peso_total, porcao_g):
    """Custo da receita a partir dos itens já carregados.

    Custo usa `quantity_g` — o que sai do estoque, cru —, e não o peso
    pronto: a água que evapora foi paga do mesmo jeito.
    """
    sem_preco = sorted({i.ingredient.display_name for i in itens if custo_por_g_ml(i.ingredient) is None})
    if not itens or sem_preco:
        return {"custo_total": None, "custo_por_porcao": None, "ingredientes_sem_preco": sem_preco}
    total = sum((i.quantity_g * custo_por_g_ml(i.ingredient) for i in itens), Decimal("0"))
    por_porcao = total * porcao_g / peso_total if peso_total else None
    return {"custo_total": _q(total), "custo_por_porcao": _q(por_porcao), "ingredientes_sem_preco": []}


def ficha_de_custo(calculo, preco_de_venda):
    """Junta o custo do cálculo ao preço do produto.

    A margem é do PRATO inteiro: a receita é a do produto vendido, então o
    preço de venda paga `custo_total`. `custo_por_porcao` é informativo.
    """
    custo = calculo["custo_total"]
    preco = Decimal(preco_de_venda) if preco_de_venda is not None else None
    margem = preco - custo if custo is not None and preco is not None else None
    divide = custo is not None and bool(preco)
    return {
        "custo_total": custo,
        "custo_por_porcao": calculo["custo_por_porcao"],
        "ingredientes_sem_preco": calculo["ingredientes_sem_preco"],
        "preco_de_venda": _q(preco),
        "margem_bruta_valor": _q(margem),
        "margem_bruta_pct": _q(margem * CEM / preco, "0.1") if divide else None,
        "cmv_pct": _q(custo * CEM / preco, "0.1") if divide else None,
    }
