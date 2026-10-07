"""Cliente que quer comprar e travou no pedido — vai para um atendente.

07/10, Dr. Matheus (Cê Saladas): meia hora para pedir uma salada. "desisto"
virou endereço e "meia hora pra fazer um pedido" devolveu o catálogo. Quem
diz que desistiu, que está demorando ou que não consegue é venda em risco:
gente fecha, não menu.

Não é reclamação de pedido recebido (ver `reclamacao.py`) nem cancelamento
pedido com calma ("cancela", "não quero mais" — `_early_cancel`).
"""
import re
import unicodedata

_TRAVOU = [
    re.compile(r'\bdesist(o|i)\b'),
    re.compile(r'\b(meia|uma|1)\s+hora\b'),
    re.compile(r'\b(que|muita|mt|maior)\s+demora\b'),
    re.compile(r'\bdemor(ando|ou|ado)\b'),
    re.compile(r'\bnao\s+(consigo|da|deu|to conseguindo|estou conseguindo)\s+(pedir|fazer|finalizar|fechar|comprar|terminar)'),
    re.compile(r'\b(travou|travado|travando|bugou|bugado)\b'),
    re.compile(r'\b(ta|esta|muito|que)\s+(dificil|complicado)\b'),
]


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize('NFD', texto or '')
    sem_acento = ''.join(c for c in sem_acento if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', sem_acento.lower()).strip()


def travou_no_pedido(texto: str) -> bool:
    t = _normalizar(texto)
    return bool(t) and any(p.search(t) for p in _TRAVOU)
