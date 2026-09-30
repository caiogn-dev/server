"""CieloVoucherProvider: o trilho da Alelo.

Sem banco e sem rede. O que importa travar aqui é o que acontece quando a
resposta NÃO é a feliz — porque é aí que o dinheiro se perde (31/ago).
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import requests

from apps.stores.services import cielo_ecommerce
from apps.stores.services.voucher.base import DadosDoVoucher
from apps.stores.services.voucher.cielo import CieloVoucherProvider


def _gateway(**extra):
    base = dict(public_key='mid', api_key='mkey', api_secret='s', is_sandbox=True,
                configuration={'voucher_brands': ['alelo']})
    base.update(extra)
    return SimpleNamespace(**base)


def _pedido():
    return SimpleNamespace(
        id='11111111-2222-3333-4444-555555555555', order_number='CE-1',
        total=Decimal('30.00'), customer_email='',
    )


DADOS = DadosDoVoucher(card_token='tok', brand='alelo', holder_name='Ana', holder_document='12345678909')


def test_so_cobra_alelo():
    """Pedir VR na Cielo é engano de roteamento — recusa antes da rede."""
    with mock.patch.object(cielo_ecommerce, 'criar_venda') as venda:
        r = CieloVoucherProvider(_gateway()).cobrar(
            _pedido(), DadosDoVoucher('tok', 'vr', 'Ana', '12345678909'))
    venda.assert_not_called()
    assert r.aprovado is False and r.status == 'failed'


def test_bandeiras_da_cielo_e_so_alelo_mesmo_se_a_config_tiver_lixo():
    gw = _gateway(configuration={'voucher_brands': ['alelo', 'vr']})
    assert CieloVoucherProvider(gw).bandeiras() == ['alelo']


def test_loja_que_desmarcou_alelo_nao_aceita():
    gw = _gateway(configuration={'voucher_brands': []})
    assert CieloVoucherProvider(gw).bandeiras() == []


def test_aprovado():
    corpo = {'Payment': {'Status': 2, 'PaymentId': 'pay-1', 'ReturnCode': '6'}}
    with mock.patch.object(cielo_ecommerce, 'criar_venda', return_value=(201, corpo)) as venda:
        r = CieloVoucherProvider(_gateway()).cobrar(_pedido(), DADOS, total=Decimal('30.00'))
    assert r.aprovado is True and r.status == 'approved' and r.external_id == 'pay-1'
    args = venda.call_args
    assert args.args[:2] == ('mid', 'mkey')
    assert args.kwargs['sandbox'] is True
    assert args.args[2]['Payment']['DebitCard']['PaymentToken'] == 'tok'


def test_recusa_traz_mensagem_em_portugues():
    corpo = {'Payment': {'Status': 3, 'PaymentId': 'p', 'ReturnCode': '51',
                         'ReturnMessage': 'Saldo Insuficiente'}}
    with mock.patch.object(cielo_ecommerce, 'criar_venda', return_value=(201, corpo)):
        r = CieloVoucherProvider(_gateway()).cobrar(_pedido(), DADOS)
    assert r.aprovado is False and r.status == 'failed'
    assert 'saldo' in r.mensagem.lower()


def test_pendente_nao_fala_em_recusa():
    corpo = {'Payment': {'Status': 12, 'PaymentId': 'p'}}
    with mock.patch.object(cielo_ecommerce, 'criar_venda', return_value=(201, corpo)):
        r = CieloVoucherProvider(_gateway()).cobrar(_pedido(), DADOS)
    assert r.status == 'pending' and r.mensagem == ''


def test_timeout_consulta_antes_de_dizer_que_falhou_e_acha_a_venda_capturada():
    """A venda saiu e a resposta se perdeu. Dizer "falhou" faria o cliente
    pagar de novo no PIX com o vale já debitado. Pergunta à Cielo primeiro."""
    achada = {'Payments': [{'PaymentId': 'pay-9', 'ReceveidDate': 'x'}]}
    detalhe = {'Payment': {'Status': 2, 'PaymentId': 'pay-9'}}
    with mock.patch.object(cielo_ecommerce, 'criar_venda', side_effect=requests.Timeout('x')), \
         mock.patch.object(cielo_ecommerce, 'consultar_por_pedido', return_value=(200, achada)), \
         mock.patch.object(cielo_ecommerce, 'consultar_venda', return_value=(200, detalhe)):
        r = CieloVoucherProvider(_gateway()).cobrar(_pedido(), DADOS)
    assert r.aprovado is True and r.external_id == 'pay-9'


def test_timeout_sem_venda_la_e_falha_de_rede():
    with mock.patch.object(cielo_ecommerce, 'criar_venda', side_effect=requests.Timeout('x')), \
         mock.patch.object(cielo_ecommerce, 'consultar_por_pedido', return_value=(404, {})):
        r = CieloVoucherProvider(_gateway()).cobrar(_pedido(), DADOS)
    assert r.aprovado is False and r.status == 'failed'
    assert 'PIX' in r.mensagem


def test_timeout_e_consulta_tambem_fora_fica_pendente_e_nao_falha():
    """Não dá para saber se cobrou. Pendente segura o pedido para conferência
    em vez de liberar o cliente para pagar duas vezes."""
    with mock.patch.object(cielo_ecommerce, 'criar_venda', side_effect=requests.Timeout('x')), \
         mock.patch.object(cielo_ecommerce, 'consultar_por_pedido', side_effect=requests.ConnectionError('y')):
        r = CieloVoucherProvider(_gateway()).cobrar(_pedido(), DADOS)
    assert r.status == 'pending'


def test_erro_de_conexao_antes_de_enviar_e_falha_segura():
    """ConnectionError no POST = a venda nem saiu. Aqui dá para dizer falhou."""
    with mock.patch.object(cielo_ecommerce, 'criar_venda', side_effect=requests.ConnectionError('dns')), \
         mock.patch.object(cielo_ecommerce, 'consultar_por_pedido', return_value=(404, {})):
        r = CieloVoucherProvider(_gateway()).cobrar(_pedido(), DADOS)
    assert r.status == 'failed'
