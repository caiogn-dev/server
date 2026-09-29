"""
Importa produtos industrializados brasileiros com marca do Open Food Facts
(openfoodfacts.org, licença ODbL) para NutritionIngredient globais.

Por que: TACO e POF medem ALIMENTO (queijo minas, molho de tomate). O lojista
compra PRODUTO (Queijo Minas Padrão Tirolez, Molho Pomarola). Sem isto, cada
cliente digitava o rótulo do fabricante à mão — e não digitava.

O que entra: produto com país Brasil, nome, marca e tabela nutricional
completa (energia, carboidratos, açúcares, proteínas, gorduras, saturadas,
sódio). Sódio vem em g/100 g e vira mg; sem sódio, usa sal ÷ 2,5. Alergênicos
saem das tags do OFF; sem tag, o ingrediente nasce "não revisado".

Usage:
    python manage.py import_openfoodfacts --dry-run --max 200
    python manage.py import_openfoodfacts --max 30000
    python manage.py import_openfoodfacts --categoria en:cheeses --categoria en:sauces
"""
import logging
import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.nutrition.models import NutritionIngredient

logger = logging.getLogger(__name__)

API = "https://world.openfoodfacts.org/api/v2/search"
UA = "Cardapidex/1.0 (cardapidex.com.br; contato@cardapidex.com.br)"
CAMPOS = "code,product_name,product_name_pt,brands,nutriments,allergens_tags,traces_tags,categories_tags,quantity,lang"

# tag do OFF -> chave interna (apps/nutrition/allergens.py)
ALERGENICO_DO_OFF = {
    "en:milk": "leite", "en:eggs": "ovo", "en:soybeans": "soja", "en:gluten": "trigo",
    "en:peanuts": "amendoim", "en:nuts": "nozes", "en:crustaceans": "crustaceos", "en:fish": "peixes",
    "en:almonds": "amendoa", "en:hazelnuts": "avela", "en:cashew-nuts": "castanha_de_caju",
    "en:brazil-nuts": "castanha_do_para", "en:macadamia-nuts": "macadamia", "en:walnuts": "nozes",
    "en:pecan-nuts": "pecas", "en:pistachios": "pistaches", "en:pine-nuts": "pinoli",
}

OBRIGATORIOS = ("energy-kcal_100g", "carbohydrates_100g", "sugars_100g", "proteins_100g", "fat_100g", "saturated-fat_100g")


def _dec(v):
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return d if d >= 0 else None


def _titulo(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s[:1].upper() + s[1:] if s else s


def alergenicos_do_off(tags) -> list:
    return sorted({ALERGENICO_DO_OFF[t] for t in (tags or []) if t in ALERGENICO_DO_OFF})


def mapear_produto_off(p: dict, hoje: date | None = None):
    """Produto do OFF -> defaults de NutritionIngredient, ou None se incompleto."""
    n = p.get("nutriments") or {}
    if any(_dec(n.get(c)) is None for c in OBRIGATORIOS):
        return None
    nome = _titulo(p.get("product_name_pt") or p.get("product_name") or "")
    marca = _titulo((p.get("brands") or "").split(",")[0])
    if not nome or not marca or not p.get("code"):
        return None
    energia = _dec(n.get("energy-kcal_100g"))
    if energia is None or energia > Decimal("900"):
        return None
    sodio_g = _dec(n.get("sodium_100g"))
    if sodio_g is None:
        sal = _dec(n.get("salt_100g"))
        sodio_g = sal / Decimal("2.5") if sal is not None else None
    if sodio_g is None:
        return None
    if sodio_g > Decimal("40"):          # 40 g de sódio por 100 g não existe: campo em mg por engano
        return None
    display = f"{nome} — {marca}"[:255]
    categoria = ""
    for tag in reversed(p.get("categories_tags") or []):
        if tag.startswith(("pt:", "en:")):
            categoria = tag.split(":", 1)[1].replace("-", " ")[:80]
            break
    alergenicos = alergenicos_do_off(p.get("allergens_tags"))
    pode_conter = [a for a in alergenicos_do_off(p.get("traces_tags")) if a not in alergenicos]
    hoje = hoje or date.today()
    return {
        "canonical_name": display.lower(),
        "display_name": display,
        "category": categoria,
        "default_unit": "g",
        "source": NutritionIngredient.Source.OFF,
        "source_code": str(p["code"])[:80],
        "source_edition": f"Open Food Facts (ODbL), {hoje:%d/%m/%Y}",
        "source_reference": f"https://br.openfoodfacts.org/produto/{p['code']}",
        "source_accessed_at": hoje,
        "notes": f"Rótulo do fabricante digitado pela comunidade do Open Food Facts. Embalagem: {p.get('quantity') or '-'}.",
        "allergens": alergenicos,
        "may_contain": pode_conter,
        "allergens_reviewed": bool(p.get("allergens_tags")),
        "is_active": True,
        "energy_kcal": energia,
        "carbohydrates_g": _dec(n.get("carbohydrates_100g")),
        "total_sugars_g": _dec(n.get("sugars_100g")),
        "added_sugars_g": _dec(n.get("added-sugars_100g")),
        "protein_g": _dec(n.get("proteins_100g")),
        "total_fat_g": _dec(n.get("fat_100g")),
        "saturated_fat_g": _dec(n.get("saturated-fat_100g")),
        "trans_fat_g": _dec(n.get("trans-fat_100g")),
        "fiber_g": _dec(n.get("fiber_100g")),
        "sodium_mg": (sodio_g * 1000).quantize(Decimal("0.0001")),
    }


def buscar_pagina(pagina: int, categoria: str | None, page_size: int = 100, tentativas: int = 5) -> dict:
    params = {
        "countries_tags": "en:brazil", "states_tags": "en:nutrition-facts-completed",
        "fields": CAMPOS, "page_size": page_size, "page": pagina, "sort_by": "unique_scans_n",
    }
    if categoria:
        params["categories_tags"] = categoria
    espera = 2
    for _ in range(tentativas):
        r = requests.get(API, params=params, headers={"User-Agent": UA}, timeout=60)
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                pass
        time.sleep(espera)          # 503 intermitente do OFF: espera e tenta de novo
        espera = min(espera * 2, 30)
    raise RuntimeError(f"OFF não respondeu a página {pagina} ({categoria or 'todas'})")


class Command(BaseCommand):
    help = "Importa produtos brasileiros com marca do Open Food Facts como ingredientes globais."

    def add_arguments(self, parser):
        parser.add_argument("--categoria", action="append", default=None, help="Tag do OFF, ex.: en:cheeses (repetível). Sem: todos.")
        parser.add_argument("--max", type=int, default=30000)
        parser.add_argument("--page-size", type=int, default=100)
        parser.add_argument("--pausa", type=float, default=1.0, help="Segundos entre páginas (respeita o rate limit do OFF)")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **o):
        categorias = o["categoria"] or [None]
        vistos, registros, descartados = set(), [], 0
        for cat in categorias:
            pagina = 1
            while len(registros) < o["max"]:
                dados = buscar_pagina(pagina, cat, o["page_size"])
                produtos = dados.get("products") or []
                if not produtos:
                    break
                for p in produtos:
                    r = mapear_produto_off(p)
                    if not r:
                        descartados += 1
                        continue
                    if r["canonical_name"] in vistos:
                        continue                      # mesmo produto em outra embalagem
                    vistos.add(r["canonical_name"])
                    registros.append(r)
                    if len(registros) >= o["max"]:
                        break
                self.stdout.write(f"{cat or 'todas'} p.{pagina}: {len(registros)} válidos, {descartados} descartados")
                pagina += 1
                if pagina * o["page_size"] > (dados.get("count") or 0):
                    break
                time.sleep(o["pausa"])
        if o["dry_run"]:
            for r in registros[:15]:
                self.stdout.write(f"  {r['display_name']} | {r['energy_kcal']} kcal | Na {r['sodium_mg']} mg | {r['allergens']}")
            self.stdout.write(self.style.WARNING(f"dry-run: {len(registros)} produtos entrariam, {descartados} descartados"))
            return
        criados, atualizados = self._gravar(registros)
        self.stdout.write(self.style.SUCCESS(f"Open Food Facts: {criados} novos, {atualizados} atualizados, {descartados} descartados"))

    @transaction.atomic
    def _gravar(self, registros):
        criados = atualizados = 0
        for r in registros:
            _, novo = NutritionIngredient.objects.update_or_create(
                store=None, canonical_name=r["canonical_name"], preparation_state="",
                defaults={k: v for k, v in r.items() if k != "canonical_name"},
            )
            criados += novo
            atualizados += not novo
        return criados, atualizados
