"""Reclamação do pedido recebido — vai para um atendente, não para o menu.

25/09, Cê Saladas: "Vieram com cebola, batata palha e frango desfiado" recebeu
"Como posso te ajudar? 👇" duas vezes; "Veio errado meu pedido" virava rastreio.

Só o que descreve um pedido que CHEGOU com problema. "Quero sem cebola" e
"vem com molho?" são pedido, não reclamação.
"""
import re
import unicodedata

_ELOGIO = re.compile(r'\b(certinh|perfeit|delicios|amei|maravilh|tudo certo|tudo ok)')

_RECLAMACAO = [
    # veio/vieram + o problema. "com/sem" só depois de veio/vieram — "chegou com
    # tudo" é elogio, "vem com molho?" é pergunta.
    re.compile(r'\b(veio|vieram)\s+(com|sem)\b(?!\s+tudo)'),
    re.compile(
        r'\b(veio|vieram|chegou|chegaram|esta|estava|tava|ta)\b.{0,30}?'
        r'\b(errad|trocad|estragad|azed|amassad|derramad|incomplet|podre|vencid|cru|crua|frio|fria|gelad)'
    ),
    re.compile(r'\bfalt(ou|aram)\s+(o|a|os|as|um|uma|meu|minha|\d)\b'),
    re.compile(r'\bfaltando\b'),
    re.compile(r'\bnao\s+(veio|vieram)\b'),
    re.compile(r'\breclam(ar|acao|acoes)\b'),
    re.compile(r'\b(cabelo|inseto|barata|mosca)\b'),
]


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize('NFD', texto or '')
    sem_acento = ''.join(c for c in sem_acento if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', sem_acento.lower()).strip()


def eh_reclamacao(texto: str) -> bool:
    t = _normalizar(texto)
    if not t:
        return False
    if _ELOGIO.search(t) and not re.search(r'\b(errad|falt|reclam|cabelo)', t):
        return False
    return any(p.search(t) for p in _RECLAMACAO)
