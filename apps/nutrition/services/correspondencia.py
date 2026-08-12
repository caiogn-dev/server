"""
Casa o ingrediente que o lojista cadastrou com o alimento equivalente da TACO.

O lojista escreve "Abacaxi"; a TACO chama de "Abacaxi, cru". Escreve "Queijo
mucarela" sem cedilha; a TACO tem "Queijo, muçarela". São a mesma comida, e
sem ligar as duas a tabela nutricional do produto sai vazia.

O casamento é uma SUGESTÃO com nota de confiança, nunca uma verdade. Copiar
valor errado para dentro de uma etiqueta é pior que etiqueta vazia — por isso
quem aplica é o comando, com o dono olhando, e a origem fica gravada no
ingrediente.
"""
import re
import unicodedata
from difflib import SequenceMatcher

# Palavras que não ajudam a distinguir comida e só empurram a nota para cima
# ("de", "com") ou aparecem em quase todo nome da TACO ("cru", "cozido").
RUIDO = {"de", "da", "do", "com", "e", "a", "o", "em", "ao", "na", "no"}
PREPARO = {"cru", "crua", "cozido", "cozida", "grelhado", "grelhada",
           "assado", "assada", "frito", "frita", "refogado", "refogada"}


def normalizar(texto):
    """Minúscula, sem acento, sem pontuação, espaço único."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^\w\s]", " ", texto.lower())
    return re.sub(r"\s+", " ", texto).strip()


def _tokens(texto, tirar_preparo=False):
    fora = RUIDO | (PREPARO if tirar_preparo else set())
    return {t for t in normalizar(texto).split() if t not in fora}


def pontuar(nome_loja, nome_taco):
    """0..1 — o quanto os dois nomes falam da mesma comida.

    Combina duas medidas porque cada uma erra sozinha:
      - sobreposição de palavras acerta "queijo mucarela" x "queijo, muçarela"
        mas também casaria "molho de tomate" com "tomate" sozinho;
      - similaridade de caractere segura esse caso, porque as strings inteiras
        são bem diferentes.
    O peso maior fica na sobreposição, que é a que entende comida.
    """
    a, b = _tokens(nome_loja, tirar_preparo=True), _tokens(nome_taco, tirar_preparo=True)
    if not a or not b:
        return 0.0

    # Jaccard penaliza o candidato que traz muita palavra a mais.
    sobreposicao = len(a & b) / len(a | b)
    literal = SequenceMatcher(None, normalizar(nome_loja), normalizar(nome_taco)).ratio()
    nota = 0.7 * sobreposicao + 0.3 * literal

    # A TACO nomeia como "Alimento, variedade, preparo": a identidade está
    # ANTES da primeira vírgula. O lojista escreve só a identidade ("Manga"),
    # e Jaccard pune isso injustamente — então o caso ganha piso próprio.
    #
    # Exigir igualdade com a cabeça, e não mera contenção no nome inteiro, é o
    # que separa "Manga" de "Cajá-Manga, cru" (outra fruta) e "Repolho" de
    # "Charuto, de repolho" (prato recheado). Os dois passavam como contenção
    # e vinham empatados na frente do alimento certo.
    if a and a == _tokens(nome_taco.split(",")[0], tirar_preparo=True):
        nota = max(nota, 0.95)

    # Preparo é desempate, não filtro: "Mandioca cozida" tem que ficar acima de
    # "Mandioca, crua", mas as duas continuam candidatas plausíveis.
    prep_a = _tokens(nome_loja) & PREPARO
    prep_b = _tokens(nome_taco) & PREPARO
    if prep_a and prep_b:
        nota = nota + 0.05 if prep_a & prep_b else nota - 0.10

    return round(min(1.0, max(0.0, nota)), 3)


def sugerir(nome_loja, candidatos, minimo=0.55, quantos=3):
    """Ordena os candidatos por nota e devolve os que passam do mínimo.

    `candidatos` é uma lista de objetos com `display_name`. Devolve
    [(candidato, nota), ...] do melhor para o pior.
    """
    notas = ((c, pontuar(nome_loja, c.display_name)) for c in candidatos)
    acima = [(c, n) for c, n in notas if n >= minimo]
    acima.sort(key=lambda par: (-par[1], par[0].display_name))
    return acima[:quantos]
