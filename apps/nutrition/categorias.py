"""Categorias de ingrediente: juntar duplicadas e esconder as estrangeiras.

A base mistura TACO/POF (português) com o Open Food Facts, que traz categoria
em inglês/espanhol, e digitação manual com erro ("allho", "a base" x "à base").
Esta é a regra ÚNICA; o painel espelha a mesma em
`pastita-dash/src/pages/nutrition/categoriasDeIngrediente.ts`.

Não há data migration: renomear categoria em massa na base oficial não é
reversível sem backup. O comando `normalizar_categorias_ingredientes
--dry-run` mostra o que mudaria; a exibição já sai normalizada sem tocar nos dados.
"""
import re
import unicodedata
from collections import Counter

# Palavras que só existem em inglês/espanhol (não ambíguas com o português).
PALAVRAS_ESTRANGEIRAS = frozenset({
    'and', 'the', 'of', 'based', 'plant', 'foods', 'food', 'products', 'beverages',
    'snacks', 'cereals', 'dairies', 'fruits', 'vegetables', 'sauces', 'spreads',
    'groceries', 'productos', 'los', 'las', 'del', 'con',
})


def chave(categoria: str) -> str:
    """Sem acento, minúscula, espaços únicos: 'À base' == 'a base'."""
    sem = unicodedata.normalize('NFD', categoria or '')
    sem = ''.join(c for c in sem if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', sem.lower()).strip()


def e_estrangeira(categoria: str) -> bool:
    return any(p in PALAVRAS_ESTRANGEIRAS for p in chave(categoria).split())


def _distancia_ate_1(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    curta, longa = sorted((a, b), key=len)
    return any(longa[:i] + longa[i + 1:] == curta for i in range(len(longa)))


def mapa_de_categorias(contagens: dict) -> dict:
    """{categoria_crua: categoria_final | None}. None = estrangeira (some da tela).

    `contagens` = {categoria_crua: quantos ingredientes}. Variantes que só
    diferem por acento/caixa/espaço, ou por UMA letra (palavras com 4+ letras),
    viram a mais usada; empate vai para a que tem acento.
    """
    validas = {c: n for c, n in contagens.items() if c and c.strip() and not e_estrangeira(c)}
    por_chave = {}
    for crua, n in validas.items():
        por_chave.setdefault(chave(crua), Counter())[crua.strip()] += n
    total = {k: sum(v.values()) for k, v in por_chave.items()}
    # chaves próximas (1 letra de diferença) juntam na mais usada
    alvo = {}
    for k in sorted(total, key=lambda x: (-total[x], x)):
        destino = next((a for a in alvo.values() if len(k) >= 4 and a != k and _distancia_ate_1(k, a)), None)
        alvo[k] = destino or k
    final = {}
    for k, cont in por_chave.items():
        raiz = alvo[k]
        variantes = Counter()
        for k2, c2 in por_chave.items():
            if alvo[k2] == raiz:
                variantes.update(c2)
        melhor = max(variantes, key=lambda v: (variantes[v], v != chave(v), v))
        final[k] = melhor[:1].upper() + melhor[1:]
    resultado = {}
    for crua in contagens:
        if not crua or not crua.strip():
            resultado[crua] = ''
        elif e_estrangeira(crua):
            resultado[crua] = None
        else:
            resultado[crua] = final[chave(crua)]
    return resultado
