from decimal import Decimal, ROUND_HALF_UP

from apps.nutrition.allergens import da_receita as allergens_da_receita
from apps.nutrition.models import NUTRIENT_FIELDS
from apps.nutrition.services.rotulagem import alertas_frontais, arredondar_tabela


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
            totals[field] = sum(getattr(item.ingredient, field) * weight / Decimal("100") for item, weight in zip(items, weights))
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
    ingredientes_incompletos = sorted({nome for nomes in faltando_por_nutriente.values() for nome in nomes})

    forma = getattr(getattr(recipe, "profile", None), "physical_form", "solido") or "solido"
    frontal = alertas_frontais(per_100g, forma)

    return {
        "total_weight_g": _q(total_weight),
        "totals": {k: _q(v) for k, v in totals.items()},
        "per_100g": per_100g,
        "per_serving": per_serving,
        "daily_values_percent": daily_values,
        "missing_nutrients": missing,
        "missing_by_nutrient": faltando_por_nutriente,
        "incomplete_ingredients": ingredientes_incompletos,
        # Valores como vão para a etiqueta impressa (IN 75/2020). Os de cima
        # continuam crus, porque relatório e conferência precisam do número real.
        "label_per_100g": arredondar_tabela(per_100g),
        "label_per_serving": arredondar_tabela(per_serving),
        "front_of_pack": frontal,
        "allergens": allergens_da_receita(recipe),
    }
