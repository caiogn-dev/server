"""
Regras de rotulagem da ANVISA que o cálculo puro não cobre.

Duas coisas separadas moram aqui:

1. **Rotulagem nutricional frontal** — RDC 429/2020, obrigatória desde
   out/2022. É a lupa preta "ALTO EM AÇÚCAR ADICIONADO / GORDURA SATURADA /
   SÓDIO" no painel principal. Os limites são por 100 g (sólido) ou 100 ml
   (líquido) e mudam entre os dois.

2. **Arredondamento** — IN 75/2020. A tabela nutricional não usa arredondamento
   comum: cada nutriente tem sua casa decimal, e abaixo de um piso o valor é
   declarado como ZERO. Sem isso a etiqueta sai "0,04 g de gordura trans" onde
   a norma manda declarar "0 g".
"""
from decimal import Decimal, ROUND_HALF_UP

# RDC 429/2020, Anexo XV. Gatilho é ">=" — exatamente no limite já leva a lupa.
LIMITES_FRONTAIS = {
    "solido": {
        "added_sugars_g": Decimal("15"),
        "saturated_fat_g": Decimal("6"),
        "sodium_mg": Decimal("600"),
    },
    "liquido": {
        "added_sugars_g": Decimal("7.5"),
        "saturated_fat_g": Decimal("3"),
        "sodium_mg": Decimal("300"),
    },
}

SELOS = {
    "added_sugars_g": "AÇÚCAR ADICIONADO",
    "saturated_fat_g": "GORDURA SATURADA",
    "sodium_mg": "SÓDIO",
}

# IN 75/2020: (casas decimais, piso abaixo do qual declara zero).
# O piso é por 100 g/ml, que é a base em que a norma expressa os limites.
ARREDONDAMENTO = {
    "energy_kcal": (0, Decimal("5")),
    "carbohydrates_g": (1, Decimal("0.5")),
    "total_sugars_g": (1, Decimal("0.5")),
    "added_sugars_g": (1, Decimal("0.5")),
    "protein_g": (1, Decimal("0.5")),
    "total_fat_g": (1, Decimal("0.5")),
    "saturated_fat_g": (1, Decimal("0.5")),
    "trans_fat_g": (1, Decimal("0.2")),
    "fiber_g": (1, Decimal("0.5")),
    "sodium_mg": (0, Decimal("5")),
}


def arredondar(campo, valor):
    """Arredonda um nutriente conforme a IN 75/2020.

    Valor abaixo do piso vira zero — é declaração legal, não perda de precisão:
    a norma considera esses traços nutricionalmente irrelevantes e proíbe
    declarar número quebrado que sugira o contrário.
    """
    if valor is None:
        return None
    valor = Decimal(valor)
    casas, piso = ARREDONDAMENTO.get(campo, (2, Decimal("0")))
    if valor < piso:
        return Decimal("0")
    exp = Decimal(1).scaleb(-casas)
    return valor.quantize(exp, rounding=ROUND_HALF_UP)


def arredondar_tabela(valores):
    """Aplica `arredondar` num dict {campo: valor}."""
    return {campo: arredondar(campo, valor) for campo, valor in valores.items()}


def alertas_frontais(por_100, forma="solido"):
    """Avalia os 3 gatilhos da lupa preta sobre os valores por 100 g/ml.

    Recebe os valores CRUS (não arredondados): arredondar antes mudaria o
    resultado bem em cima do limite — 5,96 g de saturada vira 6,0 e ganharia
    uma lupa que a norma não pede.
    """
    if forma not in LIMITES_FRONTAIS:
        raise ValueError(f"forma deve ser 'solido' ou 'liquido', veio {forma!r}")
    limites = LIMITES_FRONTAIS[forma]

    selos, indefinidos = [], []
    for campo, limite in limites.items():
        valor = por_100.get(campo)
        if valor is None:
            indefinidos.append(campo)
            continue
        if Decimal(valor) >= limite:
            selos.append({"campo": campo, "selo": SELOS[campo],
                          "valor": Decimal(valor), "limite": limite})

    return {
        "forma": forma,
        "selos": selos,
        "texto": [f"ALTO EM {s['selo']}" for s in selos],
        # Sem o dado não dá para afirmar que NÃO leva selo. Quem imprime
        # precisa saber a diferença entre "avaliado e não leva" e "não sei".
        "indefinidos": indefinidos,
        "conclusivo": not indefinidos,
    }
