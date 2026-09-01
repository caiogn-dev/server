"""
A comissão de 1% do Cardapidex sobre o pedido da loja conectada por OAuth.

CONTEXTO MEDIDO EM 01/SET

O primeiro pedido real da Agrião pela conta própria (AGR2609017451, R$ 1,00)
voltou do Mercado Pago com `application_fee: None` e `fee_details` só com a
taxa do próprio MP: a loja recebeu R$ 0,99 e a plataforma, nada. O campo
`marketplace_fee` EXISTE na Orders API — sondado com o token real da Agrião, o
MP respondeu `'$.marketplace_fee' - expected string, but got number`, e só
reclama de tipo em propriedade que conhece. Dentro de `transactions.payments[]`
os dois nomes (`marketplace_fee` e `application_fee`) voltam como
`unsupported_properties`: é na RAIZ e como STRING.

TRÊS REGRAS QUE OS TESTES TRAVAM

1. **Só cobra de quem conectou por OAuth.** No gateway manual a credencial é da
   própria loja sem vínculo de marketplace com o nosso app, e na conta da
   PLATAFORMA o dinheiro já é nosso — cobrar comissão de si mesmo faria o MP
   recusar o pagamento inteiro e derrubaria o checkout das lojas do dono.

2. **Arredonda para BAIXO.** 1% de R$ 35,99 é R$ 0,3599. Arredondar para cima
   cobra mais do que o combinado; num contrato de comissão isso é o erro caro.

3. **Comissão que arredonda para zero não é enviada.** Pedido de R$ 0,50 daria
   R$ 0,005 → R$ 0,00, e mandar '0.00' é pedir para o MP recusar um payload
   por um campo que não queria dizer nada.
"""
from decimal import Decimal

import pytest
from django.test import override_settings

from apps.stores.models import StoreOrder, StoreOrderItem, StorePaymentGateway
from apps.stores.services import mp_orders
from apps.stores.tests.factories import make_store

UM_PORCENTO = dict(PLATFORM_APPLICATION_FEE_PERCENT=Decimal('1.0'))


@pytest.fixture
def loja(db):
    return make_store()


def _pedido(loja, total):
    """Pedido mínimo mas COMPLETO: a Orders API exige payer e itens que somem
    o total, e um payload capenga falharia por outro motivo que não a comissão."""
    pedido = StoreOrder.objects.create(
        store=loja, customer_name='Cliente Teste',
        customer_email='cliente@ex.com', customer_phone='63999547790',
        delivery_address={'street_name': 'Quadra 101', 'number': '10',
                          'city': 'Palmas', 'state': 'TO'},
        subtotal=total, delivery_fee=Decimal('0.00'), total=total,
        status=StoreOrder.OrderStatus.PENDING,
        payment_status=StoreOrder.PaymentStatus.PENDING,
    )
    StoreOrderItem.objects.create(
        order=pedido, product_name='Item', unit_price=total, quantity=1,
    )
    return pedido


def _conecta(loja, tipo=StorePaymentGateway.ConnectionType.OAUTH):
    return StorePaymentGateway.objects.create(
        store=loja, name='Mercado Pago',
        gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
        access_token='APP_USR-loja', connection_type=tipo, is_enabled=True,
    )


# ── o cálculo ───────────────────────────────────────────────────────────────

@override_settings(**UM_PORCENTO)
def test_um_porcento_de_cem_reais(loja):
    _conecta(loja)

    assert mp_orders.comissao_da_plataforma(loja, '100.00') == '1.00'


@override_settings(**UM_PORCENTO)
def test_arredonda_para_baixo(loja):
    """R$ 35,99 → R$ 0,3599. Nunca cobrar mais do que o combinado."""
    _conecta(loja)

    assert mp_orders.comissao_da_plataforma(loja, '35.99') == '0.35'


@override_settings(**UM_PORCENTO)
def test_comissao_que_zera_nao_e_enviada(loja):
    _conecta(loja)

    assert mp_orders.comissao_da_plataforma(loja, '0.50') is None


@override_settings(**UM_PORCENTO)
def test_devolve_string_e_nao_numero(loja):
    """O MP recusa o payload inteiro com 'expected string, but got number'."""
    _conecta(loja)

    assert isinstance(mp_orders.comissao_da_plataforma(loja, '100.00'), str)


# ── quem paga e quem não paga ───────────────────────────────────────────────

@override_settings(**UM_PORCENTO)
def test_gateway_manual_nao_paga_comissao(loja):
    _conecta(loja, StorePaymentGateway.ConnectionType.MANUAL)

    assert mp_orders.comissao_da_plataforma(loja, '100.00') is None


@override_settings(**UM_PORCENTO)
def test_loja_na_conta_da_plataforma_nao_paga_comissao(db):
    """Cobrar comissão de si mesmo faz o MP recusar o pagamento inteiro."""
    propria = make_store(usa_gateway_da_plataforma=True)

    assert mp_orders.comissao_da_plataforma(propria, '100.00') is None


@override_settings(PLATFORM_APPLICATION_FEE_PERCENT=Decimal('0'))
def test_percentual_zero_desliga_a_cobranca(loja):
    """Default é 0: nenhuma loja existente muda de comportamento no deploy."""
    _conecta(loja)

    assert mp_orders.comissao_da_plataforma(loja, '100.00') is None


# ── nos payloads que vão para o Mercado Pago ────────────────────────────────

@override_settings(**UM_PORCENTO)
def test_pix_leva_a_comissao_na_raiz(loja):
    _conecta(loja)
    pedido = _pedido(loja, Decimal('100.00'))

    payload = mp_orders.build_pix_order_payload(pedido, 'cliente@ex.com')

    assert payload['marketplace_fee'] == '1.00'
    assert 'marketplace_fee' not in payload['transactions']['payments'][0]


@override_settings(**UM_PORCENTO)
def test_cartao_leva_a_comissao_na_raiz(loja):
    _conecta(loja)
    pedido = _pedido(loja, Decimal('100.00'))

    payload = mp_orders.build_order_payload(
        pedido, card_token='tok', payment_method_id='master',
        installments=1, payer_email='cliente@ex.com',
    )

    assert payload['marketplace_fee'] == '1.00'


@override_settings(**UM_PORCENTO)
def test_payload_de_loja_sem_oauth_nao_ganha_o_campo(loja):
    """Campo ausente, não '0.00': o MP recusa payload por campo à toa."""
    _conecta(loja, StorePaymentGateway.ConnectionType.MANUAL)
    pedido = _pedido(loja, Decimal('100.00'))

    payload = mp_orders.build_pix_order_payload(pedido, 'cliente@ex.com')

    assert 'marketplace_fee' not in payload


@override_settings(**UM_PORCENTO)
def test_comissao_do_pix_segue_o_valor_COBRADO(loja):
    """Cobrança parcial: 1% do que foi cobrado, não do total do pedido."""
    _conecta(loja)
    pedido = _pedido(loja, Decimal('100.00'))

    payload = mp_orders.build_pix_order_payload(pedido, 'c@ex.com', amount='50.00')

    assert payload['marketplace_fee'] == '0.50'


# ── a preference fala outro dialeto ─────────────────────────────────────────

@override_settings(**UM_PORCENTO)
def test_preference_quer_numero_e_a_orders_api_quer_string(loja):
    """As duas APIs do MP discordam do TIPO, e cada uma recusa o da outra.

    Sondado com o token real da Agrião em 01/set:
      POST /checkout/preferences  com '0.10' → 400 invalid_field_type
      POST /v1/orders             com  0.10  → 400 expected string
    Uma função só devolvendo um tipo só quebraria metade dos pagamentos.
    """
    _conecta(loja)

    da_orders = mp_orders.comissao_da_plataforma(loja, '100.00')
    da_preference = mp_orders.comissao_para_preferencia(loja, '100.00')

    assert da_orders == '1.00'
    assert da_preference == 1.0
    assert isinstance(da_preference, float)


@override_settings(**UM_PORCENTO)
def test_preference_sem_oauth_nao_ganha_comissao(loja):
    _conecta(loja, StorePaymentGateway.ConnectionType.MANUAL)

    assert mp_orders.comissao_para_preferencia(loja, '100.00') is None


@override_settings(**UM_PORCENTO)
def test_preference_com_comissao_zerada_nao_manda_campo(loja):
    _conecta(loja)

    assert mp_orders.comissao_para_preferencia(loja, '0.50') is None
