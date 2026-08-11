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
    "batata palha": "Batata palha (aproximação TACO chips)",
    "batata inglesa": "Batata cozida",
    "batata": "Batata cozida",
    "talharim": "Macarrão cozido",
    "macarrao": "Macarrão cozido",
    "ovo cozido": "Ovo cozido",
}

WEIGHT_RE = re.compile(r"(?<!\d)(?P<value>\d+(?:[,.]\d+)?)\s*g\b", re.I)
RANGE_RE = re.compile(r"\d+(?:[,.]\d+)?\s*~\s*\d+(?:[,.]\d+)?\s*g\b", re.I)
LIST_COMPONENT_RE = re.compile(
    r"(?:^|[,;\n])\s*[-*]?\s*(?P<name>[a-z][^,;\n]{1,55}?)\s+(?P<value>\d+(?:[,.]\d+)?)\s*g\b",
    re.I,
)
WEIGHT_FIRST_RE = re.compile(
    r"(?P<value>\d+(?:[,.]\d+)?)\s*g\s+(?:de\s+)?(?P<name>[a-z][^,;\n.]*?)(?=\s+\d+(?:[,.]\d+)?\s*g\b|[,;\n.]|$)",
    re.I,
)
AND_COMPONENT_RE = re.compile(
    r"\be\s+(?P<name>[a-z][^,;\n]{1,45}?)\s+(?P<value>\d+(?:[,.]\d+)?)\s*g\b",
    re.I,
)


def normalize(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", value)


def parse_raw_components(description):
    """Extract explicit component names and fixed gram weights for drafting.

    This intentionally ignores ranges and total/package weights. It does not
    claim nutritional equivalence: unresolved names become pending ingredients.
    """
    original = description or ""
    normalized = unicodedata.normalize("NFKD", original).encode("ascii", "ignore").decode().lower()
    normalized = re.sub(r"[ \t]+", " ", normalized)
    range_spans = [match.span() for match in RANGE_RE.finditer(normalized)]
    found = []
    occupied_weights = set()
    for pattern in (LIST_COMPONENT_RE, AND_COMPONENT_RE, WEIGHT_FIRST_RE):
        for match in pattern.finditer(normalized):
            value_span = match.span("value")
            if any(start <= value_span[0] < end for start, end in range_spans):
                continue
            name = re.sub(r"^[-*\s]+|\s+$", "", match.group("name"))
            name = re.sub(r"^(?:de|do|da)\s+", "", name)
            if re.search(r"\b(?:porcao total|peso liquido|total)\b", name) or not name:
                continue
            key = (value_span[0], value_span[1])
            if key in occupied_weights:
                continue
            occupied_weights.add(key)
            found.append({"raw_name": name, "quantity_g": Decimal(match.group("value").replace(",", ".")), "position": match.start()})
    found.sort(key=lambda item: item["position"])
    return found


def format_recipe_description(product_name, components, original_description):
    lines = [f"- {item['raw_name'].strip().capitalize()} {item['quantity_g']:g} g" for item in components]
    notes = []
    for pattern in (r"acompanha[^.!\n]*(?:[.!]|$)", r"al[eé]rgicos?[^.\n]*(?:[.]|$)", r"cont[eé]m\s+[^.\n]*(?:[.]|$)"):
        for match in re.finditer(pattern, original_description or "", re.I):
            note = match.group(0).strip().strip("*")
            if note and note.lower() not in {value.lower() for value in notes}:
                notes.append(note)
    total = sum((item["quantity_g"] for item in components), Decimal("0"))
    footer = [f"*Porção total cadastrada: {total:g} g*"]
    footer.extend(f"*{note}*" for note in notes)
    return "\n".join(lines + [""] + footer)


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
        if re.search(r"\b(?:pure|creme|molho|gratinad\w*|estrogonofe|bobo)\b", f"{before} {after}"):
            unmatched.append(weight_match.group(0))
            continue
        before_candidates = []
        after_candidates = []
        for alias, display in ALIASES.items():
            pattern = re.compile(rf"(?<![\w-]){re.escape(alias)}(?![\w-])")
            before_hits = list(pattern.finditer(before))
            after_hit = pattern.search(after)
            before_pos = before_hits[-1].start() if before_hits else -1
            after_pos = after_hit.start() if after_hit else -1
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
