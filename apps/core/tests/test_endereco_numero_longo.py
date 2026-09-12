"""Numero de endereco comprido nao pode derrubar a venda.

11/09/2026, 14:25 — a cliente SARAH ALBUQUERQUE tentou fechar pedido na Ce
Saladas TRES vezes e nas tres o servidor respondeu "Erro ao processar
checkout.". O pedido nunca existiu.

O endereco dela e de Palmas: "508 Norte, Alameda 11, HM 02" — onde o numero da
casa E o "HM 02", que ela ja tinha escrito no campo Rua. No campo Numero ela
escreveu o que faltava: "Apto 402 bloco c res trianon". Vinte e oito
caracteres numa coluna `varchar(20)`.

O Postgres recusou o INSERT, o `except Exception` do checkout virou a mensagem
generica, e ela tentou de novo identico. Em Palmas endereco com
Quadra/Alameda/Lote/HM e a regra, entao isto volta a acontecer.

Regra: o texto do cliente NUNCA se perde e NUNCA derruba a venda. O que nao
couber em `number` vai para `complement`, que e onde essa informacao pertence.
"""
from apps.core.services.customer_identity import CustomerIdentityService as CIS


#: Larguras reais das colunas de `store_customer_addresses`.
LARGURAS = {
    'street': 255, 'number': 20, 'complement': 100,
    'neighborhood': 100, 'city': 100, 'state': 2, 'zip_code': 10,
    'reference': 255,
}

CASO_SARAH = {
    'street': '508 norte alameda 11 hm 02',
    'number': 'Apto 402 bloco c rês trianon',
    'complement': '',
    'neighborhood': 'Plano diretor norte',
    'city': 'Palmas',
    'state': 'TO',
}


def test_numero_longo_nao_estoura_a_coluna():
    """Era este INSERT que o Postgres recusava."""
    r = CIS._build_address_record(CASO_SARAH)
    assert len(r['number']) <= LARGURAS['number']


def test_o_que_o_cliente_escreveu_nao_se_perde():
    """Truncar calado seria trocar uma venda perdida por um endereco errado —
    o entregador sairia sem saber o apartamento."""
    r = CIS._build_address_record(CASO_SARAH)
    junto = f"{r['number']} {r['complement']}".lower()
    assert 'apto 402' in junto
    assert 'bloco c' in junto
    assert 'trianon' in junto


def test_numero_longo_vai_para_o_complemento():
    """'Apto 402 bloco c res trianon' nao e numero, e complemento."""
    r = CIS._build_address_record(CASO_SARAH)
    assert 'apto 402' in r['complement'].lower()


def test_complemento_que_ja_existia_nao_e_atropelado():
    entrada = dict(CASO_SARAH, complement='Portao azul')
    r = CIS._build_address_record(entrada)
    assert 'portao azul' in r['complement'].lower()
    assert 'apto 402' in r['complement'].lower()


def test_numero_normal_continua_intacto():
    """O caminho feliz nao pode mudar: 'Lote 18' e 'HM 02' sao numeros de
    verdade em Palmas e continuam no campo certo."""
    for numero in ('402', 'Lote 18', 'HM 02', 'Sala 403', 'Av lo 05 lote 15'):
        r = CIS._build_address_record(dict(CASO_SARAH, number=numero, complement=''))
        assert r['number'] == numero, numero
        assert r['complement'] == '', numero


def test_todo_campo_respeita_a_largura_da_coluna():
    """Trava a CLASSE, nao so o `number`. Qualquer campo que estourar derruba a
    venda do mesmo jeito, com a mesma mensagem inutil."""
    gigante = 'x' * 600
    r = CIS._build_address_record({campo: gigante for campo in LARGURAS})
    for campo, largura in LARGURAS.items():
        assert len(r[campo]) <= largura, f'{campo}: {len(r[campo])} > {largura}'


def test_formatted_cabe_em_500():
    r = CIS._build_address_record({campo: 'y' * 600 for campo in LARGURAS})
    assert len(r['formatted']) <= 500
