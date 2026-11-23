"""Comissão que o Mercado Pago COBRA de verdade (split 1:1).

Medido em 23/11: na Orders API o `marketplace_fee` é aceito e IGNORADO — o
pedido da Agrião de R$ 1,00 (01/09) creditou R$ 0,99 à loja, só a taxa do MP
saiu, e `charges_details` não tem cobrança da plataforma. O campo que o MP
documenta para marketplace é `application_fee`, na /v1/payments. Sondado com o
token OAuth da Agrião em 23/11 (cartão falso e PIX de valor zero): a rota
passa da trava de política (400 de validação, não 403) e não recusa o campo.

Por isso loja conectada por OAuth com comissão ligada cobra pela /v1/payments;
todas as outras seguem na Orders API como antes.
"""
from decimal import Decimal
from unittest import mock

import pytest
from django.test import override_settings

from apps.stores.models import StoreOrder, StoreOrderItem, StorePaymentGateway
from apps.stores.services import mp_orders
from apps.stores.tests.factories import make_store

COMISSAO = dict(PLATFORM_APPLICATION_FEE_PERCENT=Decimal('0.99'), BASE_URL='https://backend.exemplo.com')


@pytest.fixture
def loja(db):
    loja = make_store()
    StorePaymentGateway.objects.create(
        store=loja, name='Mercado Pago',
        gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
        access_token='APP_USR-loja', connection_type=StorePaymentGateway.ConnectionType.OAUTH,
        is_enabled=True, is_active=True,
    )
    return loja


def _pedido(loja, total=Decimal('100.00')):
    p = StoreOrder.objects.create(
        store=loja, customer_name='Ana Souza', customer_email='ana@exemplo.com',
        customer_phone='63999547790', subtotal=total, delivery_fee=Decimal('0.00'),
        total=total, status=StoreOrder.OrderStatus.PENDING,
        payment_status=StoreOrder.PaymentStatus.PENDING,
    )
    StoreOrderItem.objects.create(order=p, product_name='Salada', unit_price=total, quantity=1)
    return p


@override_settings(**COMISSAO)
def test_cobra_comissao_so_de_loja_oauth(loja, db):
    assert mp_orders.cobra_comissao(loja) is True
    assert mp_orders.cobra_comissao(make_store()) is False
    assert mp_orders.cobra_comissao(make_store(usa_gateway_da_plataforma=True)) is False


@override_settings(PLATFORM_APPLICATION_FEE_PERCENT=Decimal('0'))
def test_percentual_zero_nao_cobra(loja):
    assert mp_orders.cobra_comissao(loja) is False


@override_settings(**COMISSAO)
def test_cartao_com_comissao_na_payments_api(loja):
    pedido = _pedido(loja)
    p = mp_orders.build_split_card_payment(
        pedido, card_token='tok', payment_method_id='master', installments=1,
        payer_email='ana@exemplo.com',
        payer_data={'identification_type': 'CPF', 'identification_number': '529.982.247-25'},
    )
    assert p['transaction_amount'] == 100.0
    assert p['application_fee'] == 0.99
    assert p['token'] == 'tok'
    assert p['payment_method_id'] == 'master'
    assert p['installments'] == 1
    assert p['external_reference'] == str(pedido.id)
    assert p['notification_url'] == f'https://backend.exemplo.com/webhooks/payments/mercadopago/{loja.slug}/'
    assert p['payer']['identification'] == {'type': 'CPF', 'number': '52998224725'}
    assert p['additional_info']['items'][0]['unit_price'] == 100.0


@override_settings(**COMISSAO)
def test_pix_com_comissao_sobre_o_valor_cobrado(loja):
    pedido = _pedido(loja)
    p = mp_orders.build_split_pix_payment(pedido, 'ana@exemplo.com', {}, amount=Decimal('50.00'))
    assert p['payment_method_id'] == 'pix'
    assert p['transaction_amount'] == 50.0
    assert p['application_fee'] == 0.49  # 0,99% de 50 = 0,495 → para baixo


def test_interpreta_a_resposta_da_payments_api():
    assert mp_orders.interpret_payment(201, {'id': 7, 'status': 'approved', 'status_detail': 'accredited'}) == (True, 'approved', '7', 'accredited')
    assert mp_orders.interpret_payment(201, {'id': 7, 'status': 'in_process', 'status_detail': 'pending_contingency'})[:2] == (True, 'pending')
    assert mp_orders.interpret_payment(201, {'id': 7, 'status': 'pending'})[:2] == (True, 'pending')
    assert mp_orders.interpret_payment(201, {'id': 7, 'status': 'rejected', 'status_detail': 'cc_rejected_insufficient_amount'}) == (False, 'failed', '7', 'cc_rejected_insufficient_amount')
    assert mp_orders.interpret_payment(400, {'message': 'Invalid card_token_id'}) == (False, 'failed', None, 'Invalid card_token_id')


def test_extrai_o_pix_da_payments_api():
    corpo = {'id': 99, 'date_of_expiration': '2026-11-24T10:00:00.000-04:00', 'point_of_interaction': {'transaction_data': {
        'qr_code': 'copia', 'qr_code_base64': 'b64', 'ticket_url': 'https://mp/t'}}}
    assert mp_orders.extract_pix_payment(corpo) == {
        'payment_id': '99', 'qr_code': 'copia', 'qr_code_base64': 'b64',
        'ticket_url': 'https://mp/t', 'date_of_expiration': '2026-11-24T10:00:00.000-04:00',
    }


# ── o checkout escolhe a rota ──

def _cobrar_cartao(pedido):
    from apps.stores.services.checkout_service import CheckoutService
    return CheckoutService().create_payment(pedido, 'card', {
        'token': 'tok', 'payment_method_id': 'master', 'installments': 1,
        'payer': {'email': 'ana@exemplo.com'},
    })


@override_settings(**COMISSAO)
def test_loja_oauth_cobra_pela_payments_api_com_comissao(loja):
    pedido = _pedido(loja)
    with mock.patch.object(mp_orders, 'create_payment', return_value=(201, {'id': 555, 'status': 'approved', 'status_detail': 'accredited'})) as pay, \
         mock.patch.object(mp_orders, 'create_order') as orders:
        r = _cobrar_cartao(pedido)
    assert r['success'] is True and r['status'] == 'approved'
    assert orders.call_count == 0
    assert pay.call_args.args[1]['application_fee'] == 0.99
    pedido.refresh_from_db()
    assert pedido.payment_id == '555'
    assert pedido.payment_status == StoreOrder.PaymentStatus.PAID


@override_settings(PLATFORM_APPLICATION_FEE_PERCENT=Decimal('0'))
def test_sem_comissao_segue_na_orders_api(loja):
    pedido = _pedido(loja)
    corpo = {'id': 'ORD1', 'status': 'processed', 'transactions': {'payments': [{'id': '556', 'status': 'processed', 'status_detail': 'accredited'}]}}
    with mock.patch.object(mp_orders, 'create_payment') as pay, \
         mock.patch.object(mp_orders, 'create_order', return_value=(201, corpo)) as orders:
        _cobrar_cartao(pedido)
    assert pay.call_count == 0
    assert orders.call_count == 1


@override_settings(**COMISSAO)
def test_pix_de_loja_oauth_sai_pela_payments_api_com_qr(loja):
    from apps.stores.services.checkout_service import CheckoutService
    pedido = _pedido(loja)
    corpo = {'id': 777, 'status': 'pending', 'point_of_interaction': {'transaction_data': {
        'qr_code': 'copia-e-cola', 'qr_code_base64': 'b64', 'ticket_url': 'https://mp/t'}}}
    with mock.patch.object(mp_orders, 'create_payment', return_value=(201, corpo)) as pay, \
         mock.patch.object(mp_orders, 'create_order') as orders:
        r = CheckoutService().create_payment(pedido, 'pix', {})
    assert r['success'] is True
    assert orders.call_count == 0
    assert pay.call_args.args[1]['application_fee'] == 0.99
    pedido.refresh_from_db()
    assert pedido.payment_id == '777'
    assert pedido.pix_code == 'copia-e-cola'
