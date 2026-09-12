from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.stores.services import pagarme_orders


def pedido_falso(itens, *, total, frete=Decimal('0.00'), numero='CE-1'):
    """Dublê leve: o payload só lê atributos, não precisa de banco."""
    return SimpleNamespace(
        order_number=numero,
        total=total,
        delivery_fee=frete,
        items=SimpleNamespace(all=lambda: itens),
    )


def item(nome, preco, qtd=1):
    return SimpleNamespace(product_name=nome, unit_price=Decimal(preco), quantity=qtd)


def test_centavos_converte_reais_para_inteiro():
    assert pagarme_orders.centavos(Decimal('29.90')) == 2990
    assert pagarme_orders.centavos('0.01') == 1
    assert pagarme_orders.centavos(10) == 1000


def test_centavos_arredonda_meio_para_cima_sem_erro_de_float():
    """0.1+0.2 em float vira 0.30000000000000004. Decimal impede isso."""
    assert pagarme_orders.centavos(Decimal('0.005')) == 1
    assert pagarme_orders.centavos(Decimal('12.345')) == 1235


def test_itens_viram_centavos():
    pedido = pedido_falso([item('Salada Cesar', '25.00')], total=Decimal('25.00'))
    itens = pagarme_orders.build_items(pedido)
    assert itens == [{'amount': 2500, 'description': 'Salada Cesar', 'quantity': 1}]


def test_frete_entra_como_item_proprio():
    pedido = pedido_falso(
        [item('Salada Cesar', '25.00')], total=Decimal('30.00'), frete=Decimal('5.00')
    )
    itens = pagarme_orders.build_items(pedido)
    assert {'amount': 500, 'description': 'Taxa de entrega', 'quantity': 1} in itens
    assert pagarme_orders.soma_dos_itens(itens) == 3000


def test_desconto_consolida_em_item_unico_para_fechar_a_conta():
    """Cupom não tem item negativo. Sem consolidar, sum(items) != amount
    e o Pagar.me recusa a order INTEIRA."""
    pedido = pedido_falso(
        [item('Salada Cesar', '25.00')], total=Decimal('20.00'), numero='CE-9'
    )
    itens = pagarme_orders.build_items(pedido)
    assert pagarme_orders.soma_dos_itens(itens) == 2000
    assert len(itens) == 1
    assert itens[0]['description'] == 'Pedido CE-9'


def test_pedido_sem_itens_usa_o_total():
    pedido = pedido_falso([], total=Decimal('42.50'), numero='CE-7')
    itens = pagarme_orders.build_items(pedido)
    assert itens == [{'amount': 4250, 'description': 'Pedido CE-7', 'quantity': 1}]


def test_payload_tem_um_unico_pagamento_com_o_total():
    """Tudo ou nada: nunca mais de um payment, nunca valor parcial."""
    pedido = pedido_falso([item('Salada', '25.00')], total=Decimal('25.00'))
    payload = pagarme_orders.build_voucher_payload(
        pedido, card_token='token_abc', brand='vr',
        holder_name='ANA SILVA', holder_document='39053344705',
    )
    assert len(payload['payments']) == 1
    pagamento = payload['payments'][0]
    assert pagamento['payment_method'] == 'voucher'
    assert pagamento['amount'] == 2500
    assert pagamento['amount'] == pagarme_orders.soma_dos_itens(payload['items'])


def test_payload_manda_o_token_e_nunca_o_cartao():
    pedido = pedido_falso([item('Salada', '25.00')], total=Decimal('25.00'))
    payload = pagarme_orders.build_voucher_payload(
        pedido, card_token='token_abc', brand='sodexo',
        holder_name='ANA SILVA', holder_document='390.533.447-05',
    )
    voucher = payload['payments'][0]['voucher']
    assert voucher['card_token'] == 'token_abc'
    assert voucher['card']['holder_document'] == '39053344705'  # só dígitos
    assert 'number' not in voucher.get('card', {})
    assert 'cvv' not in voucher.get('card', {})


def test_bandeira_invalida_e_recusada_antes_da_rede():
    pedido = pedido_falso([item('Salada', '25.00')], total=Decimal('25.00'))
    with pytest.raises(ValueError, match='alelo'):
        pagarme_orders.build_voucher_payload(
            pedido, card_token='t', brand='alelo',
            holder_name='ANA', holder_document='39053344705',
        )
