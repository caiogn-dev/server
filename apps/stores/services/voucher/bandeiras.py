"""Catalogo de bandeiras de vale — FONTE UNICA.

Este arquivo e o unico lugar do sistema inteiro onde uma bandeira de vale e
declarada. O cardapio e o painel recebem esta lista por API; nenhum dos dois
tem o direito de repetir um valor, um rotulo ou uma logo. Bandeira nova entra
aqui e aparece nos dois na hora, sem deploy de frontend.

A Alelo esta fora porque o Pagar.me encerrou novas integracoes com ela (fim do
contrato Cielo/Alelo). Ela sai por ausencia — nao ha `if` de excecao nenhum.

SOBRE O `value` DA PLUXEE: a Sodexo Beneficios virou Pluxee em 2024, e o
cartao que o cliente tem hoje diz "Pluxee". Mas o `value` continua 'sodexo'
porque ele JA ESTA GRAVADO em `configuration.voucher_brands` das lojas — trocar
a chave orfanaria a configuracao de quem ja marcou a bandeira. O cliente ve o
`label`; o banco guarda o `value`. So o rotulo mudou.

SOBRE A LOGO: e um CAMINHO ESTATICO relativo, nao uma URL absoluta. Quem monta
a URL e a camada de API, que sabe o dominio. Assim este modulo continua puro —
sem importar Django — e os testes rodam sem settings.
"""

CATALOGO = (
    {'value': 'vr', 'label': 'VR Benefícios', 'logo': 'voucher/vr.svg'},
    {'value': 'sodexo', 'label': 'Pluxee', 'logo': 'voucher/pluxee.svg'},
    {'value': 'ticket', 'label': 'Ticket', 'logo': 'voucher/ticket.svg'},
)


#: Bandeiras que EXISTEM mas que ninguem consegue cobrar automaticamente.
#: A Volus nao tem API publica — `api.volus.com.br` nao existe nem em DNS — e
#: nenhum gateway brasileiro a lista. O cliente que tem o cartao existe assim
#: mesmo, entao o caminho e: pedido criado, cobranca por link no WhatsApp.
#:
#: Fica SEPARADO do CATALOGO de proposito. Misturar faria o checkout abrir o
#: formulario de cartao para uma bandeira que nao tem como ser cobrada, e a
#: falha apareceria so no clique — com o cliente ja tendo digitado o cartao.
CATALOGO_MANUAL = (
    {'value': 'volus', 'label': 'Volus'},
)


def valores_manuais():
    """Só os códigos das bandeiras cobradas por link."""
    return tuple(b['value'] for b in CATALOGO_MANUAL)


def valores():
    """Só os códigos, na ordem do catálogo."""
    return tuple(b['value'] for b in CATALOGO)


def rotulo(valor):
    """Nome de exibição, dos dois catálogos. Desconhecido volta como veio."""
    for b in CATALOGO + CATALOGO_MANUAL:
        if b['value'] == valor:
            return b['label']
    return valor


def logo(valor):
    """Caminho estático da logo. Vazio para bandeira desconhecida — a tela
    desenha só o nome, em vez de uma imagem quebrada."""
    for b in CATALOGO:
        if b['value'] == valor:
            return b['logo']
    return ''
