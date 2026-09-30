"""Catalogo de bandeiras de vale — FONTE UNICA.

Este arquivo e o unico lugar do sistema inteiro onde uma bandeira de vale e
declarada. O cardapio e o painel recebem esta lista por API; nenhum dos dois
tem o direito de repetir um valor, um rotulo ou uma logo. Bandeira nova entra
aqui e aparece nos dois na hora, sem deploy de frontend.

SOBRE O `trilho`: e o gateway que sabe cobrar aquela bandeira. O Pagar.me
encerrou novas integracoes com a Alelo (fim do contrato Cielo/Alelo), entao ela
entra pelo trilho da Cielo (API E-commerce). Quem roteia e o `registry`, por
este campo — nao ha `if brand == 'alelo'` em lugar nenhum.

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
    {'value': 'vr', 'label': 'VR Benefícios', 'logo': 'voucher/vr.svg', 'trilho': 'pagarme'},
    {'value': 'sodexo', 'label': 'Pluxee', 'logo': 'voucher/pluxee.svg', 'trilho': 'pagarme'},
    {'value': 'ticket', 'label': 'Ticket', 'logo': 'voucher/ticket.svg', 'trilho': 'pagarme'},
    {'value': 'alelo', 'label': 'Alelo', 'logo': 'voucher/alelo.png', 'trilho': 'cielo'},
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
    {'value': 'volus', 'label': 'Vólus', 'logo': 'voucher/volus.svg'},
)


def valores_manuais():
    """Só os códigos das bandeiras cobradas por link."""
    return tuple(b['value'] for b in CATALOGO_MANUAL)


def valores(trilho=None):
    """Só os códigos, na ordem do catálogo. Com `trilho`, só os daquele gateway."""
    return tuple(
        b['value'] for b in CATALOGO
        if trilho is None or b.get('trilho') == trilho
    )


def trilho(valor):
    """Gateway que cobra a bandeira, ou '' se ela não for integrada."""
    for b in CATALOGO:
        if b['value'] == valor:
            return b.get('trilho', '')
    return ''


def rotulo(valor):
    """Nome de exibição, dos dois catálogos. Desconhecido volta como veio."""
    for b in CATALOGO + CATALOGO_MANUAL:
        if b['value'] == valor:
            return b['label']
    return valor


def logo(valor):
    """Caminho estático da logo, dos DOIS catálogos.

    Vazio para bandeira desconhecida — a tela desenha só o nome, em vez de uma
    imagem quebrada.

    🚨 Varria só o `CATALOGO` integrado, então toda bandeira manual voltava sem
    logo e o cardápio caía no texto. `rotulo()` já lia os dois; esta não. Duas
    funções irmãs com fontes diferentes é o tipo de divergência que só aparece
    na tela do cliente.
    """
    for b in CATALOGO + CATALOGO_MANUAL:
        if b['value'] == valor:
            return b.get('logo', '')
    return ''
