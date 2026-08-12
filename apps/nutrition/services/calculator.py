from decimal import Decimal, ROUND_HALF_UP

from apps.nutrition.allergens import da_receita as allergens_da_receita
from apps.nutrition.models import NUTRIENT_FIELDS
from apps.nutrition.services.rotulagem import (
    LIMITES_FRONTAIS as FORMAS_VALIDAS, alertas_frontais, arredondar_tabela,
)


# A TACO nunca traz açúcares nem gordura trans (colunas inexistentes), e marca
# "NA" (não analisado) espalhado no resto — 187 alimentos sem gordura saturada,
# 236 sem fibra. Por isso a regra não é uma lista de campos: num alimento da
# TACO, valor nulo JÁ significa que a fonte não mediu. O lojista não tem como
# preencher, e cobrar dele é mandá-lo procurar dado que não existe.
FONTES_COMPLETAS = {"manual", "manufacturer", "lab"}

DAILY_VALUES = {
    "energy_kcal": Decimal("2000"), "carbohydrates_g": Decimal("300"),
    "added_sugars_g": Decimal("50"), "protein_g": Decimal("50"),
    "total_fat_g": Decimal("65"), "saturated_fat_g": Decimal("20"),
    "trans_fat_g": Decimal("2"), "fiber_g": Decimal("25"),
    "sodium_mg": Decimal("2000"),
}


def _q(value, places="0.01"):
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP) if value is not None else None


def calculate_recipe(recipe):
    items = list(recipe.items.select_related("ingredient").all())
    weights = [item.prepared_quantity_g or item.quantity_g for item in items]
    total_weight = recipe.prepared_weight_g or sum(weights, Decimal("0"))
    totals, missing = {}, []
    for field in NUTRIENT_FIELDS:
        if any(getattr(item.ingredient, field) is None for item in items):
            totals[field] = None
            missing.append(field)
        else:
            # Início Decimal explícito: `sum()` de gerador vazio devolve int 0,
            # e int não tem quantize. Receita vazia nunca chegava aqui porque a
            # tela só calculava ao salvar; com a prévia ao vivo, chega a cada
            # tecla — inclusive antes de existir o primeiro ingrediente.
            totals[field] = sum(
                (getattr(item.ingredient, field) * weight / Decimal("100")
                 for item, weight in zip(items, weights)),
                Decimal("0"),
            )
    per_100g = {field: (_q(value * Decimal("100") / total_weight) if value is not None and total_weight else None) for field, value in totals.items()}
    serving = recipe.serving_size_g
    per_serving = {field: (_q(value * serving / Decimal("100")) if value is not None else None) for field, value in per_100g.items()}
    daily_values = {field: (_q(per_serving[field] * Decimal("100") / ref, "0.1") if per_serving.get(field) is not None else None) for field, ref in DAILY_VALUES.items()}

    # Um ingrediente sem dado zera o nutriente da receita inteira. Dizer só
    # QUAL nutriente sumiu deixa o lojista adivinhando em que ingrediente
    # mexer — então devolvemos o culpado, por nutriente e consolidado.
    faltando_por_nutriente = {
        field: sorted({item.ingredient.display_name for item in items
                       if getattr(item.ingredient, field) is None})
        for field in missing
    }
    # Duas ausências diferentes, que antes vinham na mesma lista e faziam
    # parecer que o lojista tinha esquecido de cadastrar:
    #   - ingrediente SEM NADA: ninguém preencheu, é trabalho dele;
    #   - nutriente que a FONTE não mede: a TACO não traz açúcares nem gordura
    #     trans, então todo alimento dela "falta" esses três. Cobrar isso do
    #     lojista é mandá-lo procurar um dado que não existe na tabela.
    # O discriminador é a FONTE do ingrediente, não "tem algum valor": um
    # ingrediente manual preenchido pela metade continua sendo trabalho do
    # lojista, enquanto um da TACO sem açúcar é limite da tabela.
    def _fonte_nao_mede(ingrediente, campo):
        return ingrediente.source not in FONTES_COMPLETAS

    nao_medidos, cobrar_do_lojista = {}, set()
    for campo in missing:
        for item in items:
            ing = item.ingredient
            if getattr(ing, campo) is not None:
                continue
            if _fonte_nao_mede(ing, campo):
                nao_medidos.setdefault(campo, set()).add(ing.display_name)
            else:
                cobrar_do_lojista.add(ing.display_name)

    faltando_com_dado = {campo: sorted(nomes) for campo, nomes in nao_medidos.items()}
    ingredientes_incompletos = sorted(cobrar_do_lojista)

    # A forma vem do perfil, que pode nem existir ainda. Validar contra a lista
    # em vez de confiar no atributo: `alertas_frontais` é estrita de propósito
    # (chamada explícita com forma inválida deve estourar), mas aqui um perfil
    # ausente ou estranho não pode derrubar o cálculo inteiro — cai no default
    # do modelo, que é sólido.
    forma = getattr(getattr(recipe, "profile", None), "physical_form", None)
    if forma not in FORMAS_VALIDAS:
        forma = "solido"
    frontal = alertas_frontais(per_100g, forma)

    return {
        "total_weight_g": _q(total_weight),
        "totals": {k: _q(v) for k, v in totals.items()},
        "per_100g": per_100g,
        "per_serving": per_serving,
        "daily_values_percent": daily_values,
        "missing_nutrients": missing,
        "missing_by_nutrient": faltando_por_nutriente,
        # Ingredientes que ninguém preencheu — o que o lojista precisa resolver.
        "incomplete_ingredients": ingredientes_incompletos,
        # Nutriente ausente em ingrediente que TEM dado: a fonte não mede.
        # Resolve com valor de fabricante ou laudo, não com cadastro.
        "unmeasured_by_nutrient": {c: n for c, n in faltando_com_dado.items() if n},
        # Valores como vão para a etiqueta impressa (IN 75/2020). Os de cima
        # continuam crus, porque relatório e conferência precisam do número real.
        "label_per_100g": arredondar_tabela(per_100g),
        "label_per_serving": arredondar_tabela(per_serving),
        "front_of_pack": frontal,
        "allergens": allergens_da_receita(recipe),
    }
