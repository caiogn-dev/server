import re
import unicodedata
from decimal import Decimal


ALIASES = {
    "file de frango grelhado": "Frango grelhado",
    "frango grelhado": "Frango grelhado",
    "frango desfiado": "Frango cozido",
    "peito de frango": "Frango cozido",
    "patinho moido": "Carne moída (patinho)",
    "carne desfiada": "Carne bovina cozida",
    "carne de panela": "Carne bovina cozida",
    "arroz integral": "Arroz integral cozido",
    "arroz com curcuma": "Arroz branco cozido",
    "arroz branco": "Arroz branco cozido",
    "feijao carioca": "Feijão carioca cozido",
    "feijao preto": "Feijão preto cozido",
    "brocolis": "Brócolis",
    "couve refogada": "Couve",
    "couve": "Couve",
    "abobrinha": "Abobrinha",
    "cenoura": "Cenoura",
    "pepino": "Pepino",
    "alface": "Alface",
    "tomate": "Tomate",
    "batata doce": "Batata doce",
    "batata inglesa": "Batata cozida",
    "batata": "Batata cozida",
    "talharim": "Macarrão cozido",
    "macarrao": "Macarrão cozido",
    "ovo cozido": "Ovo cozido",
}

WEIGHT_RE = re.compile(r"(?<!\d)(?P<value>\d+(?:[,.]\d+)?)\s*g\b", re.I)
RANGE_RE = re.compile(r"\d+(?:[,.]\d+)?\s*~\s*\d+(?:[,.]\d+)?\s*g\b", re.I)


def normalize(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", value)


def parse_weighted_ingredients(description):
    """Return matched components and unmatched gram mentions.

    Explicit totals ("peso líquido", "porção total") are ignored. Ranges such
    as 30~50 g remain unmatched so a human chooses the production standard.
    """
    text = normalize(description or "")
    matches, unmatched = [], []
    weight_matches = list(WEIGHT_RE.finditer(text))
    ranges = [match.span() for match in RANGE_RE.finditer(text)]
    for index, weight_match in enumerate(weight_matches):
        if any(start <= weight_match.start() < end for start, end in ranges):
            unmatched.append(weight_match.group(0))
            continue
        previous_end = weight_matches[index - 1].end() if index else 0
        next_start = weight_matches[index + 1].start() if index + 1 < len(weight_matches) else len(text)
        before = text[max(previous_end, weight_match.start() - 70):weight_match.start()]
        after = text[weight_match.end():min(next_start, weight_match.end() + 70)]
        # Comma/semicolon/newline delimit components in salad descriptions.
        before = re.split(r"[,;\n]", before)[-1]
        after = re.split(r"[,;\n]", after)[0]
        if re.search(r"(?:porcao total|peso liquido|total)\s*:?\s*$", before):
            continue
        before_candidates = []
        after_candidates = []
        for alias, display in ALIASES.items():
            before_pos = before.rfind(alias)
            after_pos = after.find(alias)
            if before_pos >= 0:
                before_candidates.append((len(before) - (before_pos + len(alias)), -len(alias), display, alias))
            if 0 <= after_pos <= 18:
                after_candidates.append((after_pos, -len(alias), display, alias))
        # If words follow the weight ("20 g de muçarela"), only an alias on
        # that side is valid. Falling back to the left would reuse the prior
        # component ("frango ... 20 g de muçarela") and corrupt the recipe.
        has_words_after = bool(re.search(r"[a-z]", after))
        candidates = after_candidates if has_words_after else before_candidates
        if not candidates:
            unmatched.append(weight_match.group(0))
            continue
        _, _, display, alias = min(candidates)
        matches.append({"ingredient_name": display, "matched_alias": alias, "quantity_g": Decimal(weight_match.group("value").replace(",", "."))})
    # A repeated ingredient is summed (e.g. two separately declared portions).
    merged = {}
    for item in matches:
        merged.setdefault(item["ingredient_name"], {**item, "quantity_g": Decimal("0")})
        merged[item["ingredient_name"]]["quantity_g"] += item["quantity_g"]
    return {"items": list(merged.values()), "unmatched_weights": unmatched}
