"""
Declaração de lactose — RDC 136/2017.

Lactose NÃO é alergênico. Intolerância é deficiência de enzima, não resposta
imune, e por isso ela ficou fora da RDC 26/2015. Tem norma própria, que exige
declarar a presença no rótulo.

**Por que estado declarado e não miligrama:** a norma trabalha com faixas de
mg de lactose, mas nem a TACO nem a POF medem lactose — não existe o número
para comparar. O que existe é o que está impresso na embalagem que o lojista
compra ("zero lactose" vem escrito lá). Inventar limiar sobre um número que
ninguém mediu seria o mesmo erro que evitamos na lupa frontal.

**Por que a derivação é conservadora:** um ingrediente com lactose faz o prato
inteiro conter lactose, e "zero" só pode ser afirmado quando TODOS os
ingredientes são isentos. Errar para o lado de declarar a mais faz o cliente
intolerante evitar um prato que talvez pudesse comer; errar para o outro faz
ele passar mal. As duas pontas não são simétricas.
"""

CONTEM = "contem"
BAIXO_TEOR = "baixo_teor"
ZERO = "zero"
ISENTO = "isento"          # não tem lactose por natureza (alface, arroz, carne)
NAO_REVISADO = "nao_revisado"

ESTADOS = {
    CONTEM: "Contém lactose",
    BAIXO_TEOR: "Baixo teor de lactose",
    ZERO: "Zero lactose",
    ISENTO: "Não contém lactose",
    NAO_REVISADO: "Não revisado",
}

# Do mais restritivo ao menos: a declaração do prato é o pior caso entre os
# ingredientes, nunca a média.
SEVERIDADE = {CONTEM: 4, BAIXO_TEOR: 3, ZERO: 2, ISENTO: 1}

FRASES = {
    CONTEM: "CONTÉM LACTOSE.",
    BAIXO_TEOR: "BAIXO TEOR DE LACTOSE.",
    ZERO: "ZERO LACTOSE.",
    ISENTO: "NÃO CONTÉM LACTOSE.",
}


def declaracao(estados):
    """Monta a linha de lactose a partir dos estados dos ingredientes.

    Um único ingrediente não revisado impede a declaração inteira, pela mesma
    razão do alergênico: afirmar "não contém" sobre cadastro que ninguém olhou
    é pior que não afirmar nada.
    """
    estados = list(estados)
    if not estados:
        return {"estado": NAO_REVISADO, "texto": "", "revisado": False, "pendentes": 0}

    pendentes = sum(1 for e in estados if e not in SEVERIDADE)
    if pendentes:
        return {"estado": NAO_REVISADO, "texto": "", "revisado": False, "pendentes": pendentes}

    pior = max(estados, key=lambda e: SEVERIDADE[e])
    return {"estado": pior, "texto": FRASES[pior], "revisado": True, "pendentes": 0}


def da_receita(recipe):
    """Deriva a declaração de lactose dos ingredientes da receita."""
    itens = list(recipe.items.select_related("ingredient").all())
    estados = [getattr(item.ingredient, "lactose", NAO_REVISADO) or NAO_REVISADO for item in itens]
    resultado = declaracao(estados)
    resultado["ingredientes_sem_revisao"] = sorted({
        item.ingredient.display_name for item in itens
        if (getattr(item.ingredient, "lactose", NAO_REVISADO) or NAO_REVISADO) not in SEVERIDADE
    })
    return resultado
