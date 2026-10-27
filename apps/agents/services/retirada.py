"""O cliente do WhatsApp disse que vem BUSCAR?

27/10, Carlos (CE-2610277336): o agente não tinha como marcar retirada e
escreveu "Retirada na loja" no campo de endereço. O texto foi geocodificado e
o pedido nasceu entrega. Esta regra reconhece a frase onde quer que o LLM a
ponha — no endereço, nas observações — para o pedido nascer `pickup`.

Frase, não palavra solta: "Rua do Retiro" é endereço.
"""
import re
import unicodedata

_VERBO = r'(retirada|retirar|retiro|retira|buscar|busco|busca|pegar|pego|pega)'
_PADROES = (
    # A frase É o pedido: "Retirada", "Vou retirar", "Busco aí".
    re.compile(rf'^\s*(vou\s+|eu\s+|irei\s+)?{_VERBO}\b(\s+(ai|aqui|la|ja))?\s*[.!]*\s*$'),
    # Verbo + onde: "retirar no local", "pego na loja", "retiro no balcão".
    re.compile(rf'\b{_VERBO}\s+(na|no|em|pessoalmente)\b(\s+(loja|local|balcao|restaurante))?'),
)


def _normal(texto) -> str:
    plano = unicodedata.normalize('NFD', str(texto or '')).encode('ascii', 'ignore').decode()
    return ' '.join(plano.lower().split())


def pediu_retirada(texto) -> bool:
    t = _normal(texto)
    if not t:
        return False
    return any(p.search(t) for p in _PADROES)
