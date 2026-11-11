"""O que do texto do modelo pode chegar ao cliente.

17/09 12:12: uma cliente perguntou "Tem almôndega hj?" e recebeu 2.696
caracteres do raciocínio interno do modelo, em inglês, cortado no meio da
frase. O `nemotron-3-super` raciocina por padrão e, com `max_tokens=700`,
gastou o orçamento inteiro pensando (`finish_reason=length`).

A causa se conserta desligando o raciocínio (`corpo_extra_do_modelo`). Este
módulo é a SEGUNDA camada: o próximo modelo trocado às pressas — já foram
cinco em oito semanas — pode raciocinar de outro jeito. Qualquer resposta que
chegue truncada ou com cara de raciocínio é recusada; quem chama trata como
falha da IA e passa a conversa para o atendente (17/09, `falha_da_ia`).
"""
import re


class RespostaDoModeloInvalida(Exception):
    """O modelo respondeu, mas o texto não pode ir para o cliente."""

    def __init__(self, motivo: str, texto: str = ''):
        super().__init__(motivo)
        self.motivo = motivo
        self.texto = texto


_BLOCO_THINK = re.compile(r'<think>.*?</think>', re.IGNORECASE | re.DOTALL)
_THINK_ABERTO = re.compile(r'<think>', re.IGNORECASE)

#: Frases que só aparecem quando o modelo fala SOBRE a conversa em vez de
#: falar COM o cliente. Estreitas de propósito: o custo de um falso positivo é
#: tirar do bot uma resposta boa e acordar o atendente.
_RACIOCINIO = re.compile(
    r"\bthe user (is|was|wants|asked|asks|said|says|might|may|mentioned)\b"
    r"|\blet me (check|see|think|look)\b"
    r"|\baccording to the rules\b"
    r"|^\s*(okay|ok|alright|hmm)[,.]\s",
    re.IGNORECASE,
)


#: 11/nov/2026: o `nemotron-3-ultra` na NIM passou a devolver sopa de tokens
#: ("那些Re)))))))…", "0 星-0--") e cinco saíram para clientes num dia.
#: Escrita que nunca aparece numa conversa em português: CJK, kana, hangul,
#: devanágari, pontuação ideográfica e o caractere de substituição (byte
#: quebrado).
_ESCRITA_ESTRANHA = re.compile(
    r'[ऀ-ॿ　-〿぀-ヿ㐀-䶿一-鿿'
    r'가-힯！-／�]'
)
#: Parênteses empilhados: "))))" não existe em texto de gente.
_PARENTESES_EMPILHADOS = re.compile(r'[()]{4,}')
#: Chamada de ferramenta ou código que vazou cru em vez de virar resposta.
_CODIGO_CRU = re.compile(
    r'</?tool_call>|</?function|```'
    r'|^\s*\{\s*"(name|function|tool|arguments|parameters)"\s*:',
    re.IGNORECASE,
)


def _letra_fora_do_portugues(t: str) -> bool:
    """Português cabe inteiro no Latin-1 (até U+00FF).

    No fluxo real o ultra devolveu 'ươ' (vietnamita, Latin Extended-B), que a
    lista de escritas acima não pegava. Emoji não é letra e passa.
    """
    return any(c.isalpha() and ord(c) > 0xFF for c in t)


def texto_degenerado(texto: str) -> bool:
    """True quando o texto claramente não é uma resposta para gente ler."""
    t = (texto or '').strip()
    if not t:
        return False  # vazio é tratado por quem chama
    return bool(
        not any(c.isalpha() for c in t)  # ')', '...': nenhuma palavra
        or _ESCRITA_ESTRANHA.search(t)
        or _letra_fora_do_portugues(t)
        or _PARENTESES_EMPILHADOS.search(t)
        or _CODIGO_CRU.search(t)
    )


def texto_para_o_cliente(texto, finish_reason) -> str:
    """Devolve o texto limpo, ou levanta RespostaDoModeloInvalida."""
    bruto = texto if isinstance(texto, str) else str(texto or '')

    # Resposta cortada pelo limite: o que saiu não é uma resposta inteira —
    # no caso de 17/09, nem começou a ser.
    if (finish_reason or '') == 'length':
        raise RespostaDoModeloInvalida('truncada_no_limite_de_tokens', bruto)

    limpo = _BLOCO_THINK.sub('', bruto)
    if _THINK_ABERTO.search(limpo):
        raise RespostaDoModeloInvalida('raciocinio_sem_fechamento', bruto)
    limpo = limpo.strip()

    if _RACIOCINIO.search(limpo):
        raise RespostaDoModeloInvalida('raciocinio_no_texto', bruto)
    if texto_degenerado(limpo):
        raise RespostaDoModeloInvalida('texto_degenerado', bruto)
    return limpo
