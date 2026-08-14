"""Como o cliente quer pagar — dito por ele, em português de WhatsApp.

O detector de intenções só conhecia PIX. O padrão que capturava era
`quero pagar|forma de pagamento|como pago`, e "quero pagar no cartão" casa com
`quero pagar`. Resultado: o cliente pedia cartão e recebia um código PIX.

Aqui a resposta é só um rótulo. Quem gera o link, o PIX ou a maquininha é o
handler — este módulo não conversa com o cliente nem chama gateway.

Ordem de teste importa e não é alfabética:

1. **maquininha** primeiro. "não consigo pagar pelo link" contém "link" e
   "pagar"; testado depois, viraria pedido de cartão e devolveria ao cliente
   exatamente o link que ele acabou de dizer que não consegue abrir.
2. **cartão** antes de PIX, porque "não quero pix, prefiro cartão" cita os dois.
"""
import re
import unicodedata

#: Rótulos. `None` significa "não deu para saber" — e não-saber tem que ser
#: distinguível de dinheiro, senão o bot decide sozinho como o cliente paga.
MAQUININHA = 'maquininha'
CARTAO = 'cartao'
PIX = 'pix'
DINHEIRO = 'dinheiro'


def _sem_acento(texto: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', str(texto or '').lower())
        if unicodedata.category(c) != 'Mn'
    )


#: "não consigo pagar pelo link", "não abre o link", "deu erro no link",
#: "tem maquininha?", "passa na máquina", "pago na entrega no cartão".
_MAQUININHA = re.compile(
    r'\b('
    r'maquin\w*'
    r'|(nao|n)\s+(consigo|consegui|deu|abre|abriu|foi|funciona|funcionou|ta indo|vai)\b'
    r'|(deu|da)\s+erro'
    r'|link\s+(nao|n)\s+\w+'
    r'|pag\w+\s+na\s+entrega'
    r'|na\s+hora\s+da\s+entrega'
    r')\b',
)

#: "cartão", "crédito", "débito", "no crédito", "passar o cartão".
_CARTAO = re.compile(r'\b(cartao|credito|debito|visa|master\w*|elo)\b')

_PIX = re.compile(r'\b(pix)\b')

#: "dinheiro", "espécie", "vou pagar em dinheiro", "troco pra 50".
_DINHEIRO = re.compile(r'\b(dinheiro|especie|troco)\b')


def detectar(texto):
    """Devolve o rótulo da forma de pagamento, ou None quando não dá para saber.

    None é uma resposta legítima: chutar a forma de pagamento é como o cliente
    recebe PIX depois de pedir cartão.
    """
    limpo = _sem_acento(texto)
    if not limpo.strip():
        return None

    # Primeiro a reclamação sobre o link: ela CONTÉM as palavras de cartão e de
    # pagamento, e testada depois devolveria ao cliente o mesmo link que ele
    # acabou de dizer que não consegue abrir.
    if _MAQUININHA.search(limpo):
        return MAQUININHA
    if _CARTAO.search(limpo):
        return CARTAO
    if _PIX.search(limpo):
        return PIX
    if _DINHEIRO.search(limpo):
        return DINHEIRO
    return None
