from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.stores.services.voucher.base import DadosDoVoucher
from apps.stores.services.voucher.pagarme import PagarmeVoucherProvider
from apps.stores.services.voucher import registry


def gateway_falso(secret='sk_test_x'):
    return SimpleNamespace(
        gateway_type='pagarme', api_key=secret, public_key='pk_test_y',
        is_enabled=True, is_sandbox=True, configuration={'voucher_brands': ['vr', 'sodexo']},
    )


def pedido_falso():
    return SimpleNamespace(
        order_number='CE-1', total=Decimal('25.00'), delivery_fee=Decimal('0.00'),
        store=SimpleNamespace(name='Ce Saladas'),
        items=SimpleNamespace(all=lambda: [
            SimpleNamespace(product_name='Salada', unit_price=Decimal('25.00'), quantity=1)
        ]),
    )


DADOS = DadosDoVoucher(card_token='tok_1', brand='vr',
                       holder_name='ANA SILVA', holder_document='39053344705')


def test_cobranca_aprovada():
    corpo = {'id': 'or_9', 'status': 'paid',
             'charges': [{'status': 'paid', 'last_transaction': {}}]}
    with patch('apps.stores.services.pagarme_orders.create_order',
               return_value=(200, corpo)) as chamada:
        r = PagarmeVoucherProvider(gateway_falso()).cobrar(pedido_falso(), DADOS)
    assert r.aprovado is True
    assert r.status == 'approved'
    assert r.external_id == 'or_9'
    # a secret key da LOJA foi usada, não uma global
    assert chamada.call_args[0][0] == 'sk_test_x'


def test_cobranca_recusada_devolve_portugues():
    corpo = {'id': 'or_9', 'status': 'failed', 'charges': [
        {'status': 'failed', 'last_transaction': {'acquirer_message': 'Saldo insuficiente'}}
    ]}
    with patch('apps.stores.services.pagarme_orders.create_order', return_value=(200, corpo)):
        r = PagarmeVoucherProvider(gateway_falso()).cobrar(pedido_falso(), DADOS)
    assert r.aprovado is False
    assert 'saldo' in r.mensagem.lower()


def test_bandeira_fora_da_lista_da_loja_e_recusada_sem_rede():
    dados = DadosDoVoucher('tok', 'ticket', 'ANA', '39053344705')  # loja só tem vr/sodexo
    with patch('apps.stores.services.pagarme_orders.create_order') as chamada:
        r = PagarmeVoucherProvider(gateway_falso()).cobrar(pedido_falso(), dados)
    assert r.aprovado is False
    assert chamada.call_count == 0


def test_timeout_de_rede_vira_falha_legivel_e_nao_excecao():
    import requests
    with patch('apps.stores.services.pagarme_orders.create_order',
               side_effect=requests.Timeout()):
        r = PagarmeVoucherProvider(gateway_falso()).cobrar(pedido_falso(), DADOS)
    assert r.aprovado is False
    assert r.status == 'failed'
    assert r.mensagem


def test_bruto_nunca_carrega_o_token():
    """`bruto` vai para gateway_response no banco. Token ali seria vazamento."""
    corpo = {'id': 'or_9', 'status': 'paid',
             'charges': [{'status': 'paid', 'last_transaction': {}}]}
    with patch('apps.stores.services.pagarme_orders.create_order', return_value=(200, corpo)):
        r = PagarmeVoucherProvider(gateway_falso()).cobrar(pedido_falso(), DADOS)
    assert 'tok_1' not in str(r.bruto)


def test_registry_devolve_o_provider_do_pagarme():
    assert isinstance(registry.provider_para(gateway_falso()), PagarmeVoucherProvider)


def test_registry_recusa_gateway_desconhecido():
    with pytest.raises(ValueError, match='volus'):
        registry.provider_para(SimpleNamespace(gateway_type='volus'))
