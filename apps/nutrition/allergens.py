"""
Alergênicos obrigatórios — RDC 26/2015 (ANVISA).

A norma lista os alimentos que causam alergias alimentares e exige declaração
em destaque logo abaixo da lista de ingredientes:

    "ALÉRGICOS: CONTÉM DERIVADOS DE LEITE E TRIGO."
    "ALÉRGICOS: PODE CONTER SOJA."

Duas listas separadas de propósito. `contem` é o que está NA receita.
`pode_conter` é contaminação cruzada — cozinha que também manipula o alergênico
—, e a norma proíbe usar a segunda para se esquivar da primeira: se o
ingrediente está na receita, é CONTÉM, ponto.

Glúten tem regra própria (Lei 10.674/2003): a declaração "CONTÉM GLÚTEN" ou
"NÃO CONTÉM GLÚTEN" é obrigatória em TODO alimento embalado, mesmo quando
nenhum cereal do grupo aparece na receita — por isso ela sai sempre, enquanto
os demais alergênicos só aparecem quando existem.
"""

# chave interna -> (rótulo na declaração, tem glúten?)
ALERGENICOS = {
    "leite": ("leite", False),
    "ovo": ("ovos", False),
    "soja": ("soja", False),
    "trigo": ("trigo", True),
    "aveia": ("aveia", True),
    "cevada": ("cevada", True),
    "centeio": ("centeio", True),
    "triticale": ("triticale", True),
    "amendoim": ("amendoim", False),
    "amendoa": ("amêndoa", False),
    "avela": ("avelã", False),
    "castanha_de_caju": ("castanha-de-caju", False),
    "castanha_do_para": ("castanha-do-pará", False),
    "macadamia": ("macadâmia", False),
    "nozes": ("nozes", False),
    "pecas": ("pecã", False),
    "pistaches": ("pistaches", False),
    "pinoli": ("pinoli", False),
    "crustaceos": ("crustáceos", False),
    "peixes": ("peixes", False),
    "latex": ("látex natural", False),
}

CEREAIS_COM_GLUTEN = tuple(chave for chave, (_, gluten) in ALERGENICOS.items() if gluten)


def validar(chaves):
    """Devolve as chaves desconhecidas — o model usa para recusar lixo."""
    return sorted(set(chaves) - set(ALERGENICOS))


def _rotulos(chaves):
    """Ordena pela ordem da norma, não alfabética, e remove repetido."""
    vistos = [c for c in ALERGENICOS if c in set(chaves)]
    return [ALERGENICOS[c][0] for c in vistos]


def _frase(prefixo, chaves):
    rotulos = _rotulos(chaves)
    if not rotulos:
        return ""
    if len(rotulos) == 1:
        lista = rotulos[0]
    else:
        lista = f"{', '.join(rotulos[:-1])} e {rotulos[-1]}"
    return f"{prefixo} {lista.upper()}."


def declaracao(contem=(), pode_conter=()):
    """Monta o bloco de alergênicos da etiqueta.

    Um alergênico que está em `contem` nunca aparece também em `pode_conter` —
    a advertência de traço seria ruído em cima de uma certeza.
    """
    contem = set(contem)
    pode_conter = set(pode_conter) - contem

    linhas = []
    if contem:
        linhas.append(_frase("ALÉRGICOS: CONTÉM", contem))
    if pode_conter:
        linhas.append(_frase("ALÉRGICOS: PODE CONTER", pode_conter))

    tem_gluten = any(c in CEREAIS_COM_GLUTEN for c in contem)
    pode_ter_gluten = any(c in CEREAIS_COM_GLUTEN for c in pode_conter)
    if tem_gluten:
        linhas.append("CONTÉM GLÚTEN.")
    elif pode_ter_gluten:
        linhas.append("PODE CONTER GLÚTEN.")
    else:
        linhas.append("NÃO CONTÉM GLÚTEN.")

    return {
        "contem": sorted(contem),
        "pode_conter": sorted(pode_conter),
        "gluten": "contem" if tem_gluten else ("pode_conter" if pode_ter_gluten else "nao_contem"),
        "linhas": linhas,
        "texto": " ".join(linhas),
    }


def da_receita(recipe):
    """Deriva a declaração dos ingredientes da receita.

    O lojista não digita a frase: ela cai do que ele já cadastrou em cada
    ingrediente. Digitar à mão é como se esquece o leite do purê.

    Se algum ingrediente ainda não teve os alergênicos revisados, a declaração
    sai marcada como não confiável e SEM as frases — "NÃO CONTÉM GLÚTEN"
    impresso em cima de cadastro não revisado é pior que nenhuma etiqueta.
    """
    contem, pode_conter, pendentes = set(), set(), []
    for item in recipe.items.select_related("ingredient"):
        ing = item.ingredient
        if not ing.allergens_reviewed:
            pendentes.append(ing.display_name)
        contem.update(ing.allergens or [])
        pode_conter.update(ing.may_contain or [])

    resultado = declaracao(contem, pode_conter)
    resultado["revisado"] = not pendentes
    resultado["ingredientes_sem_revisao"] = sorted(set(pendentes))
    if pendentes:
        resultado["linhas"] = []
        resultado["texto"] = ""
    return resultado
