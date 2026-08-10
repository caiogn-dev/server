"""
Combo tem que virar pedido pelo WhatsApp — pelo preço do combo.

Em 09/ago o agente descreveu o COMBO 4 RONDELLI'S quatro vezes, o cliente
confirmou três, e o pedido nunca existiu. Motivo: `order_service.py` só criava
`StoreCartItem`. Combo é `StoreCartComboItem`, e sem ele o combo não tinha como
existir no pedido.

O risco desta fatia é PREÇO: somar os 4 rondellis avulsos daria R$ 164, e o
combo é R$ 160. Por isso o primeiro teste aqui é o do total — o mesmo tipo de
defeito que já custou o commit 3f550c6 (cliente ditando preço).
"""
from decimal import Decimal

import pytest

from apps.stores.models import (
    ComboProductGroup, ComboProductGroupProductOption, StoreCombo, StoreOrderComboItem,
)
from apps.stores.tests.factories import make_store, make_product
from apps.whatsapp.services.order_service import WhatsAppOrderService


@pytest.fixture
def loja_com_combo(db):
    store = make_store()
    a = make_product(store, name="Rondelli de Frango", price=Decimal("41.00"))
    b = make_product(store, name="Rondelli 4 Queijos", price=Decimal("41.00"))
    combo = StoreCombo.objects.create(
        store=store, name="COMBO 4 RONDELLI'S", slug="combo-4",
        price=Decimal("160.00"), is_active=True,
    )
    grupo = ComboProductGroup.objects.create(
        combo=combo, title="Escolha os sabores", is_required=True,
        min_selections=4, max_selections=4, position=0,
    )
    ComboProductGroupProductOption.objects.create(group=grupo, product=a, max_selections=4)
    ComboProductGroupProductOption.objects.create(group=grupo, product=b, max_selections=4)
    return store, combo, grupo, a, b


def _pedir(store, itens):
    svc = WhatsAppOrderService(
        store=store, phone_number="5563999999999", customer_name="Cliente Teste",
    )
    return svc.create_order_from_cart(
        items=itens,
        delivery_address="Q. 110 Sul Alameda 3, 51",
        delivery_method="delivery",
        payment_method="pix",
        delivery_fee_override=0,
    )


def _entrada_de_combo(combo, grupo, produtos, quantidade=1):
    return {
        'combo_id': str(combo.id),
        'combo_name': combo.name,
        'quantity': quantidade,
        'unit_price': float(combo.price),
        'group_selections': {str(grupo.id): [str(p.id) for p in produtos]},
    }


def test_combo_vira_pedido(loja_com_combo):
    store, combo, grupo, a, b = loja_com_combo

    r = _pedir(store, [_entrada_de_combo(combo, grupo, [a, a, b, b])])

    assert r.get('success') is True, r
    assert r.get('order') is not None


def test_cobra_o_preco_do_combo_e_nao_a_soma_dos_itens(loja_com_combo):
    """4 rondellis avulsos = R$ 164. O combo é R$ 160. Tem que sair 160."""
    store, combo, grupo, a, b = loja_com_combo

    r = _pedir(store, [_entrada_de_combo(combo, grupo, [a, a, b, b])])

    pedido = r['order']
    pedido.refresh_from_db()
    assert pedido.subtotal == Decimal("160.00"), f"subtotal {pedido.subtotal} != 160"


def test_guarda_a_escolha_dos_sabores(loja_com_combo):
    """Sem o snapshot, a cozinha não sabe quais sabores montar."""
    store, combo, grupo, a, b = loja_com_combo

    r = _pedir(store, [_entrada_de_combo(combo, grupo, [a, a, b, b])])

    snap = StoreOrderComboItem.objects.get(order=r['order'])
    assert snap.combo_id == combo.id
    escolhidos = snap.group_selections.get(str(grupo.id)) or []
    assert len(escolhidos) == 4


def test_combo_e_produto_avulso_no_mesmo_pedido(loja_com_combo):
    store, combo, grupo, a, b = loja_com_combo
    avulso = make_product(store, name="Molho Branco", price=Decimal("19.90"))

    r = _pedir(store, [
        _entrada_de_combo(combo, grupo, [a, a, b, b]),
        {'product_id': str(avulso.id), 'quantity': 1, 'unit_price': 19.90},
    ])

    pedido = r['order']
    pedido.refresh_from_db()
    assert pedido.subtotal == Decimal("179.90")


def test_quantidade_maior_que_um_multiplica_o_combo(loja_com_combo):
    store, combo, grupo, a, b = loja_com_combo

    r = _pedir(store, [_entrada_de_combo(combo, grupo, [a, a, b, b], quantidade=2)])

    pedido = r['order']
    pedido.refresh_from_db()
    assert pedido.subtotal == Decimal("320.00")


def test_combo_de_outra_loja_e_recusado(loja_com_combo):
    """Não pode existir combo cross-tenant num pedido."""
    store, combo, grupo, a, b = loja_com_combo
    outra = make_store()
    intruso = StoreCombo.objects.create(
        store=outra, name="Combo alheio", slug="alheio",
        price=Decimal("10.00"), is_active=True,
    )

    r = _pedir(store, [{
        'combo_id': str(intruso.id), 'combo_name': intruso.name,
        'quantity': 1, 'unit_price': 10.0, 'group_selections': {},
    }])

    assert r.get('success') is not True


def test_preco_enviado_pelo_cliente_nao_manda_no_combo(loja_com_combo):
    """O preço do combo é o do catálogo. Cliente não dita valor — 3f550c6."""
    store, combo, grupo, a, b = loja_com_combo
    entrada = _entrada_de_combo(combo, grupo, [a, a, b, b])
    entrada['unit_price'] = 1.0

    r = _pedir(store, [entrada])

    pedido = r['order']
    pedido.refresh_from_db()
    assert pedido.subtotal == Decimal("160.00"), 'preço veio do payload do cliente'
