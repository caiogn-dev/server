"""Catalogo de bandeiras de vale — FONTE UNICA.

Este arquivo e o unico lugar do sistema inteiro onde uma bandeira de vale e
declarada. O cardapio e o painel recebem esta lista por API; nenhum dos dois
tem o direito de repetir um valor ou um rotulo. Bandeira nova entra aqui e
aparece nos dois na hora, sem deploy de frontend.

A Alelo esta fora porque o Pagar.me encerrou novas integracoes com ela (fim do
contrato Cielo/Alelo). Ela sai por ausencia — nao ha `if` de excecao nenhum.
"""

CATALOGO = (
    {'value': 'vr', 'label': 'VR Benefícios'},
    {'value': 'sodexo', 'label': 'Sodexo'},
    {'value': 'ticket', 'label': 'Ticket'},
)


def valores():
    """Só os códigos, na ordem do catálogo."""
    return tuple(b['value'] for b in CATALOGO)


def rotulo(valor):
    """Nome de exibição. Valor desconhecido volta como veio, sem explodir."""
    for b in CATALOGO:
        if b['value'] == valor:
            return b['label']
    return valor
