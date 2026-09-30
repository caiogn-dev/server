"""Formato de fio da API E-commerce Cielo para o vale Alelo.

Tudo aqui é sem rede e sem banco: `requests` é trocado por dublê. O que está
sendo travado é o contrato documentado em
docs.cielo.com.br/ecommerce-cielo/reference/criar-pagamento-com-voucher.
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
import requests

from apps.stores.services import cielo_ecommerce as cielo


def _pedido(**extra):
    base = dict(
        id='3f2b8c1e-0a4d-4e7b-9c2a-1b2c3d4e5f60',
        order_number='CE-2609291234',
        total=Decimal('59.90'),
        customer_name='Ana Lúcia',
        customer_email='ana@exemplo.com',
    )
    base.update(extra)
    return SimpleNamespace(**base)


def _resposta(status_code, corpo):
    r = mock.Mock()
    r.status_code = status_code
    r.json.return_value = corpo
    return r


# ── endereços ────────────────────────────────────────────────────────────────

def test_sandbox_e_producao_tem_hosts_distintos_para_transacao_e_consulta():
    assert cielo.urls(sandbox=True) == (
        'https://apisandbox.cieloecommerce.cielo.com.br',
        'https://apiquerysandbox.cieloecommerce.cielo.com.br',
    )
    assert cielo.urls(sandbox=False) == (
        'https://api.cieloecommerce.cielo.com.br',
        'https://apiquery.cieloecommerce.cielo.com.br',
    )


# ── payload ──────────────────────────────────────────────────────────────────

def test_payload_alelo_e_debito_bandeira_elo_sem_3ds_com_token_e_nao_pan():
    corpo = cielo.build_sale_payload(
        _pedido(), payment_token='tok-123', holder_name='Ana Lúcia',
        holder_document='123.456.789-09', total=Decimal('59.90'),
    )
    pagamento = corpo['Payment']
    assert pagamento['Type'] == 'DebitCard'
    assert pagamento['Authenticate'] is False
    assert pagamento['Amount'] == 5990
    assert pagamento['DebitCard'] == {'PaymentToken': 'tok-123', 'Brand': 'Elo'}
    # Nenhum campo de cartão cru pode sair daqui: é o que mantém o PCI fora.
    for campo in ('CardNumber', 'SecurityCode', 'ExpirationDate'):
        assert campo not in pagamento['DebitCard']


def test_valor_em_centavos_sem_erro_de_float():
    corpo = cielo.build_sale_payload(
        _pedido(), payment_token='t', holder_name='A', holder_document='12345678909',
        total=Decimal('29.90'),
    )
    assert corpo['Payment']['Amount'] == 2990


def test_merchant_order_id_so_alfanumerico_ate_50():
    """A Cielo recusa hífen: o UUID do pedido sai sem os traços."""
    corpo = cielo.build_sale_payload(
        _pedido(), payment_token='t', holder_name='A', holder_document='12345678909',
    )
    moid = corpo['MerchantOrderId']
    assert moid == '3f2b8c1e0a4d4e7b9c2a1b2c3d4e5f60'
    assert moid.isalnum() and len(moid) <= 50


def test_nome_do_cliente_sem_acento_nem_simbolo():
    """`Customer.Name` aceita só letras: 'Lúcia' vira 'Lucia', não 'Lcia'."""
    corpo = cielo.build_sale_payload(
        _pedido(), payment_token='t', holder_name="Ana Lúcia D'Ávila 2",
        holder_document='123.456.789-09',
    )
    assert corpo['Customer']['Name'] == 'Ana Lucia DAvila'
    assert corpo['Customer']['Identity'] == '12345678909'
    assert corpo['Customer']['IdentityType'] == 'CPF'


def test_cnpj_do_titular_vai_como_cnpj():
    corpo = cielo.build_sale_payload(
        _pedido(), payment_token='t', holder_name='Empresa',
        holder_document='12.345.678/0001-95',
    )
    assert corpo['Customer']['IdentityType'] == 'CNPJ'


def test_sem_total_usa_o_total_do_pedido():
    corpo = cielo.build_sale_payload(
        _pedido(total=Decimal('10.00')), payment_token='t', holder_name='A',
        holder_document='12345678909',
    )
    assert corpo['Payment']['Amount'] == 1000


# ── leitura da resposta ──────────────────────────────────────────────────────

RESPOSTA_APROVADA = {
    'MerchantOrderId': 'x',
    'Payment': {
        'Status': 2, 'ReturnCode': '6', 'ReturnMessage': 'Operation Successful',
        'PaymentId': 'cb024e08-22c7-4684-9bba-ec854d7fbd2a', 'Tid': '0722122543881',
    },
}


def test_status_2_e_pagamento_confirmado():
    ok, status, pid, motivo = cielo.interpret(201, RESPOSTA_APROVADA)
    assert (ok, status, pid) == (True, 'approved', 'cb024e08-22c7-4684-9bba-ec854d7fbd2a')


@pytest.mark.parametrize('codigo', [0, 1, 12])
def test_status_em_voo_e_pendente_e_nao_recusa(codigo):
    """0 NotFinished, 1 Authorized, 12 Pending: o dinheiro pode entrar ainda.
    Tratar como recusa mandaria o cliente pagar de novo no PIX."""
    corpo = {'Payment': {'Status': codigo, 'PaymentId': 'p1'}}
    ok, status, pid, _ = cielo.interpret(201, corpo)
    assert status == 'pending'
    assert pid == 'p1'


@pytest.mark.parametrize('codigo', [3, 13])
def test_negado_ou_abortado_e_falha(codigo):
    corpo = {'Payment': {'Status': codigo, 'PaymentId': 'p1', 'ReturnCode': '05',
                         'ReturnMessage': 'Nao Autorizada'}}
    ok, status, _, _ = cielo.interpret(201, corpo)
    assert (ok, status) == (False, 'failed')


@pytest.mark.parametrize('codigo', [10, 11])
def test_cancelado_ou_estornado_nao_e_a_mesma_coisa_que_negado(codigo):
    ok, status, _, _ = cielo.interpret(201, {'Payment': {'Status': codigo, 'PaymentId': 'p'}})
    assert (ok, status) == (False, 'refunded')


def test_http_400_com_lista_de_erros_e_falha_com_o_motivo():
    """Erro de validação da Cielo vem como lista [{Code, Message}]."""
    corpo = [{'Code': 126, 'Message': 'Credit Card Expiration Date is invalid'}]
    ok, status, pid, motivo = cielo.interpret(400, corpo)
    assert (ok, status, pid) == (False, 'failed', None)
    assert 'Expiration' in motivo


# ── mensagem para o cliente ──────────────────────────────────────────────────

@pytest.mark.parametrize('codigo, trecho', [
    ('51', 'saldo'),
    ('57', 'vencido'),
    ('78', 'bloqueado'),
])
def test_codigo_de_retorno_vira_orientacao_em_portugues(codigo, trecho):
    assert trecho in cielo.mensagem_de_recusa(codigo, '').lower()


def test_codigo_desconhecido_cai_na_generica_sem_vazar_codigo():
    texto = cielo.mensagem_de_recusa('XYZ', 'Internal thing 999')
    assert 'XYZ' not in texto and '999' not in texto
    assert 'PIX' in texto


# ── rede ─────────────────────────────────────────────────────────────────────

def test_criar_venda_manda_as_credenciais_da_loja_no_cabecalho():
    with mock.patch.object(cielo.requests, 'post', return_value=_resposta(201, RESPOSTA_APROVADA)) as post:
        status_code, corpo = cielo.criar_venda('mid', 'mkey', {'x': 1}, sandbox=True)
    assert status_code == 201
    url = post.call_args.args[0]
    headers = post.call_args.kwargs['headers']
    assert url == 'https://apisandbox.cieloecommerce.cielo.com.br/1/sales/'
    assert headers['MerchantId'] == 'mid'
    assert headers['MerchantKey'] == 'mkey'
    assert headers['RequestId']  # idempotência/rastreio


def test_consulta_por_merchant_order_id_usa_o_host_de_consulta():
    with mock.patch.object(cielo.requests, 'get', return_value=_resposta(200, {'Payments': []})) as get:
        cielo.consultar_por_pedido('mid', 'mkey', 'abc123', sandbox=False)
    assert get.call_args.args[0] == 'https://apiquery.cieloecommerce.cielo.com.br/1/sales'
    assert get.call_args.kwargs['params'] == {'merchantOrderId': 'abc123'}


def test_cancelar_e_sempre_do_valor_inteiro():
    with mock.patch.object(cielo.requests, 'put', return_value=_resposta(200, {'Status': 10})) as put:
        cielo.cancelar('mid', 'mkey', 'pay-1', Decimal('59.90'), sandbox=True)
    assert put.call_args.args[0] == 'https://apisandbox.cieloecommerce.cielo.com.br/1/sales/pay-1/void'
    assert put.call_args.kwargs['params'] == {'amount': 5990}


# ── Silent Order Post ────────────────────────────────────────────────────────

def _gateway_sop(**extra):
    base = dict(
        id=7, public_key='mid-7', api_key='mkey-7', api_secret='segredo-sop',
        is_sandbox=True, configuration={'sop_client_id': 'cliente-sop'},
    )
    base.update(extra)
    return SimpleNamespace(**base)


def test_token_do_sop_faz_oauth_e_pede_o_access_token_com_o_merchant_id(settings):
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    from django.core.cache import cache
    cache.clear()

    oauth = _resposta(201, {'access_token': 'bearer-x', 'expires_in': 599})
    sop = _resposta(201, {'AccessToken': 'sop-token', 'ExpiresIn': '2026-09-29T10:20:00'})
    with mock.patch.object(cielo.requests, 'post', side_effect=[oauth, sop]) as post:
        token = cielo.token_do_sop(_gateway_sop())

    assert token == 'sop-token'
    url_oauth, url_sop = post.call_args_list[0].args[0], post.call_args_list[1].args[0]
    assert url_oauth == 'https://authsandbox.braspag.com.br/oauth2/token'
    assert url_sop == 'https://transactionsandbox.pagador.com.br/post/api/public/v2/accesstoken'
    assert post.call_args_list[0].kwargs['auth'] == ('cliente-sop', 'segredo-sop')
    headers_sop = post.call_args_list[1].kwargs['headers']
    assert headers_sop['MerchantId'] == 'mid-7'
    assert headers_sop['Authorization'] == 'Bearer bearer-x'


def test_bearer_do_oauth_e_reaproveitado_entre_clientes(settings):
    """O AccessToken do SOP é de um cartão só, mas o bearer vale ~10 min.
    Pedir OAuth a cada cliente dobraria as chamadas na hora do pico."""
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    from django.core.cache import cache
    cache.clear()

    respostas = [
        _resposta(201, {'access_token': 'bearer-x', 'expires_in': 599}),
        _resposta(201, {'AccessToken': 'a'}),
        _resposta(201, {'AccessToken': 'b'}),
    ]
    with mock.patch.object(cielo.requests, 'post', side_effect=respostas) as post:
        assert cielo.token_do_sop(_gateway_sop()) == 'a'
        assert cielo.token_do_sop(_gateway_sop()) == 'b'
    assert post.call_count == 3


def test_sop_sem_credencial_nao_chama_rede():
    with mock.patch.object(cielo.requests, 'post') as post:
        with pytest.raises(cielo.SopIndisponivel):
            cielo.token_do_sop(_gateway_sop(api_secret='', configuration={}))
    post.assert_not_called()


def test_sop_com_rede_fora_vira_indisponivel_e_nao_excecao_crua(settings):
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    from django.core.cache import cache
    cache.clear()
    with mock.patch.object(cielo.requests, 'post', side_effect=requests.Timeout('x')):
        with pytest.raises(cielo.SopIndisponivel):
            cielo.token_do_sop(_gateway_sop())
