from django.http import Http404, HttpResponse
from django.utils.html import escape
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET

from .allergens import da_receita as allergens_da_receita
from .models import NUTRIENT_FIELDS, ProductNutritionProfile
from .services.rotulagem import alertas_frontais


LABELS = (
    ("energy_kcal", "Valor energético", "kcal"),
    ("carbohydrates_g", "Carboidratos", "g"),
    ("total_sugars_g", "Açúcares totais", "g"),
    ("added_sugars_g", "Açúcares adicionados", "g"),
    ("protein_g", "Proteínas", "g"),
    ("total_fat_g", "Gorduras totais", "g"),
    ("saturated_fat_g", "Gorduras saturadas", "g"),
    ("trans_fat_g", "Gorduras trans", "g"),
    ("fiber_g", "Fibra alimentar", "g"),
    ("sodium_mg", "Sódio", "mg"),
)


def _fmt(value):
    if value is None:
        return "Não informado"
    return f"{value:.1f}".replace(".0", "").replace(".", ",")


@require_GET
@cache_page(60 * 10)
def public_nutrition_label(request, product_id):
    profile = get_object_or_404(
        ProductNutritionProfile.objects.select_related("product", "product__store", "recipe").prefetch_related("recipe__items__ingredient"),
        product_id=product_id, is_active=True,
    )
    if not profile.recipe_id and all(getattr(profile, field) is None for field in NUTRIENT_FIELDS):
        raise Http404
    serving = profile.serving_size_g
    rows = []
    for field, label, unit in LABELS:
        per_100 = getattr(profile, field)
        per_serving = per_100 * serving / 100 if per_100 is not None else None
        rows.append(f"<tr><th>{label} ({unit})</th><td>{_fmt(per_100)}</td><td>{_fmt(per_serving)}</td></tr>")
    ingredients = []
    if profile.recipe_id:
        ingredients = [item.ingredient.display_name for item in profile.recipe.items.all()]
    status = profile.recipe.get_status_display() if profile.recipe_id else "Informado manualmente"

    # Lupa frontal (RDC 429/2020) e alergênicos (RDC 26/2015). Ambos saem do
    # que já está calculado; a página é só a vitrine. Quando o dado não dá
    # para concluir, a página diz isso em vez de omitir — omissão aqui o
    # cliente lê como "não tem".
    por_100 = {field: getattr(profile, field) for field in NUTRIENT_FIELDS}
    frontal = alertas_frontais(por_100, profile.physical_form)
    if frontal["selos"]:
        selos_html = "".join(f"<span class='selo'>ALTO EM<br><b>{escape(s['selo'])}</b></span>"
                             for s in frontal["selos"])
        frontal_html = f"<section><h2>Rotulagem frontal</h2><div class='selos'>{selos_html}</div></section>"
    elif frontal["conclusivo"]:
        frontal_html = ("<section><h2>Rotulagem frontal</h2>"
                        "<p>Este produto não atinge os limites que exigem a lupa de advertência.</p></section>")
    else:
        frontal_html = ("<section><h2>Rotulagem frontal</h2><p class='note'>Ainda não é possível "
                        "concluir: faltam dados de açúcar adicionado, gordura saturada ou sódio.</p></section>")

    alerg = allergens_da_receita(profile.recipe) if profile.recipe_id else None
    if alerg and alerg["revisado"]:
        alerg_html = f"<section><h2>Alergênicos</h2><p class='alerg'>{escape(alerg['texto'])}</p></section>"
    elif alerg:
        alerg_html = ("<section><h2>Alergênicos</h2><p class='note'>Informação em revisão. "
                      "Consulte a loja antes de consumir em caso de alergia alimentar.</p></section>")
    else:
        alerg_html = ""
    product_name = escape(profile.product.name)
    store_name = escape(profile.product.store.name)
    measure = escape(profile.household_measure)
    ingredients_text = ", ".join(escape(name) for name in ingredients)
    html = f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Informação nutricional — {product_name}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f1eb;color:#171717;font:16px/1.45 system-ui,sans-serif}}main{{max-width:720px;margin:auto;padding:24px}}header{{margin-bottom:22px}}.brand{{font-size:13px;text-transform:uppercase;letter-spacing:.12em;color:#666}}h1{{font-size:28px;line-height:1.1;margin:6px 0}}.status{{display:inline-block;padding:5px 9px;border:1px solid #777;border-radius:999px;font-size:12px}}section{{background:#fff;padding:18px;border-radius:14px;margin-top:14px}}h2{{font-size:19px;margin:0 0 12px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px 6px;border-bottom:1px solid #bbb;text-align:right}}th:first-child{{text-align:left}}thead th{{border-bottom:3px solid #111}}p{{margin:8px 0}}.note{{font-size:13px;color:#555}}.selos{{display:flex;gap:10px;flex-wrap:wrap}}.selo{{background:#111;color:#fff;padding:10px 14px;border-radius:6px;font-size:12px;line-height:1.25;text-align:center;text-transform:uppercase;letter-spacing:.04em}}.alerg{{font-weight:700;text-transform:uppercase;letter-spacing:.02em}}@media(max-width:520px){{main{{padding:16px}}h1{{font-size:23px}}th,td{{font-size:13px;padding:8px 3px}}}}
</style></head><body><main><header><div class='brand'>{store_name}</div><h1>{product_name}</h1><span class='status'>{status}</span></header><section><h2>Informação nutricional</h2><p>Porção: <b>{_fmt(serving)} g</b>{f" ({measure})" if measure else ""}</p><table><thead><tr><th></th><th>100 g</th><th>Porção</th></tr></thead><tbody>{''.join(rows)}</tbody></table><p class='note'>Valores estimados a partir da composição cadastrada, salvo quando o produto estiver marcado como aprovado.</p></section>{frontal_html}{alerg_html}{f"<section><h2>Ingredientes cadastrados</h2><p>{ingredients_text}</p></section>" if ingredients else ""}</main></body></html>"""
    return HttpResponse(html)
