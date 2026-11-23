"""Cartão de crédito pela Pagar.me (app). Mesmo molde do vale: StorePayment
nasce antes da chamada, `pending` não é recusa, o webhook confirma.

Lojas da conta da PLATAFORMA (Pastita, Ivoneth, Kero Kero) cobram pela
Pagar.me da loja definida em `PAGARME_LOJA_DA_PLATAFORMA` (a do dono)."""
from decimal import Decimal
from unittest import mock

import pytest
from django.test import override_settings

from apps.stores.models import StoreOrder, StoreOrderItem, StorePayment, StorePaymentGateway
from apps.stores.services import cartao_pagarme, pagarme_orders
from apps.stores.tests.factories import make_store


def _pagarme(loja, **extra):
    return StorePaymentGateway.objects.create(
        store=loja, name='Pagar.me', gateway_type='pagarme',
        api_key='sk_x', public_key='pk_y', is_enabled=True, **extra,
    )


@pytest.fixture
def dono(db):
    loja = make_store(slug='loja-do-dono', usa_gateway_da_plataforma=True)
    _pagarme(loja)
    return loja


def _pedido(loja, total=Decimal('45.90')):
    p = StoreOrder.objects.create(
        store=loja, customer_name='Ana Souza', customer_email='ana@exemplo.com',
        customer_phone='5563999547790', subtotal=total, delivery_fee=Decimal('0'),
        total=total, status=StoreOrder.OrderStatus.PENDING,
        payment_status=StoreOrder.PaymentStatus.PENDING,
        delivery_address={'street': 'Quadra 104 Norte', 'number': '10', 'neighborhood': 'Plano Diretor Norte',
                          'city': 'Palmas', 'state': 'TO', 'zip_code': '77006-020'},
    )
    StoreOrderItem.objects.create(order=p, product_name='Salada', unit_price=total, quantity=1)
    return p


CARTAO = {'gateway': 'pagarme', 'card_token': 'token_abc', 'holder_name': 'ANA SOUZA',
          'holder_document': '529.982.247-25'}


# ── qual conta cobra ──

@override_settings(PAGARME_LOJA_DA_PLATAFORMA='loja-do-dono')
def test_loja_da_plataforma_usa_a_pagarme_do_dono(dono, db):
    irma = make_store(usa_gateway_da_plataforma=True)
    assert cartao_pagarme.gateway_do_cartao(dono).store_id == dono.id
    assert cartao_pagarme.gateway_do_cartao(irma).store_id == dono.id


@override_settings(PAGARME_LOJA_DA_PLATAFORMA='loja-do-dono')
def test_loja_de_cliente_sem_pagarme_propria_nao_tem_cartao_pagarme(dono, db):
    assert cartao_pagarme.gateway_do_cartao(make_store()) is None


@override_settings(PAGARME_LOJA_DA_PLATAFORMA='loja-do-dono')
def test_config_publica_so_com_chave_publica(dono):
    assert cartao_pagarme.config_publica(dono) == {'gateway': 'pagarme', 'public_key': 'pk_y'}
    StorePaymentGateway.objects.filter(store=dono).update(public_key='')
    assert cartao_pagarme.config_publica(dono) is None


# ── o payload ──

def test_payload_de_credito(dono):
    pedido = _pedido(dono)
    p = cartao_pagarme.build_payload(pedido, card_token='token_abc', holder_name='ANA SOUZA',
                                     holder_document='529.982.247-25')
    pag = p['payments'][0]
    assert pag['payment_method'] == 'credit_card'
    assert pag['amount'] == 4590 == pagarme_orders.soma_dos_itens(p['items'])
    cc = pag['credit_card']
    assert cc['card_token'] == 'token_abc'
    assert cc['installments'] == 1
    assert cc['operation_type'] == 'auth_and_capture'
    assert cc['card']['billing_address'] == {
        'line_1': '10, Quadra 104 Norte, Plano Diretor Norte', 'zip_code': '77006020',
        'city': 'Palmas', 'state': 'TO', 'country': 'BR',
    }
    assert p['customer']['document'] == '52998224725'
    assert p['customer']['phones']['mobile_phone'] == {'country_code': '55', 'area_code': '63', 'number': '999547790'}


# ── o checkout ──

def _cobrar(pedido):
    from apps.stores.services.checkout_service import CheckoutService
    return CheckoutService().create_payment(pedido, 'card', dict(CARTAO))


def _resposta(status_charge, oid='or_1', msg='Transação aprovada'):
    return (200, {'id': oid, 'status': 'paid' if status_charge == 'paid' else 'pending',
                  'charges': [{'status': status_charge, 'last_transaction': {'acquirer_message': msg}}]})


@override_settings(PAGARME_LOJA_DA_PLATAFORMA='loja-do-dono')
def test_aprovado_paga_o_pedido(dono):
    pedido = _pedido(dono)
    with mock.patch.object(pagarme_orders, 'create_order', return_value=_resposta('paid')) as criar:
        r = _cobrar(pedido)
    assert criar.call_args.args[0] == 'sk_x'
    assert r['success'] is True and r['status'] == 'approved'
    assert r['payment_method'] == 'credit_card'
    pedido.refresh_from_db()
    assert pedido.payment_status == StoreOrder.PaymentStatus.PAID
    assert pedido.status == StoreOrder.OrderStatus.CONFIRMED
    pag = StorePayment.objects.get(order=pedido)
    assert pag.payment_method == StorePayment.PaymentMethod.CREDIT_CARD
    assert pag.external_id == 'or_1'
    assert pag.status == StorePayment.PaymentStatus.COMPLETED


@override_settings(PAGARME_LOJA_DA_PLATAFORMA='loja-do-dono')
def test_em_analise_nao_e_recusa(dono):
    pedido = _pedido(dono)
    with mock.patch.object(pagarme_orders, 'create_order', return_value=_resposta('processing')):
        r = _cobrar(pedido)
    assert r['success'] is True and r['status'] == 'pending'
    pedido.refresh_from_db()
    assert pedido.payment_status == StoreOrder.PaymentStatus.PENDING


@override_settings(PAGARME_LOJA_DA_PLATAFORMA='loja-do-dono')
def test_recusado_explica_ao_cliente(dono):
    pedido = _pedido(dono)
    with mock.patch.object(pagarme_orders, 'create_order', return_value=_resposta('failed', msg='Saldo insuficiente')):
        r = _cobrar(pedido)
    assert r['success'] is False
    assert 'limite' in r['error'].lower()
    pedido.refresh_from_db()
    assert pedido.payment_status == StoreOrder.PaymentStatus.FAILED


@override_settings(PAGARME_LOJA_DA_PLATAFORMA='loja-do-dono')
def test_sem_token_nem_chama_a_pagarme(dono):
    pedido = _pedido(dono)
    from apps.stores.services.checkout_service import CheckoutService
    with mock.patch.object(pagarme_orders, 'create_order') as criar:
        r = CheckoutService().create_payment(pedido, 'card', {'gateway': 'pagarme'})
    assert r['success'] is False
    assert criar.call_count == 0


# ── o webhook confirma cartão também ──

@override_settings(PAGARME_LOJA_DA_PLATAFORMA='loja-do-dono')
def test_webhook_confirma_cartao_pendente(dono):
    from apps.webhooks.handlers.pagarme_handler import PagarmeHandler
    pedido = _pedido(dono)
    with mock.patch.object(pagarme_orders, 'create_order', return_value=_resposta('processing', oid='or_7')):
        _cobrar(pedido)
    with mock.patch.object(pagarme_orders, 'consultar_order', return_value=_resposta('paid', oid='or_7')):
        r = PagarmeHandler().handle(None, {'type': 'order.paid', 'data': {'id': 'or_7'}}, {})
    assert r['status'] == 'approved'
    pedido.refresh_from_db()
    assert pedido.payment_status == StoreOrder.PaymentStatus.PAID


# ── o app-config anuncia ──

@override_settings(PAGARME_LOJA_DA_PLATAFORMA='loja-do-dono')
def test_app_config_anuncia_cartao_pagarme(dono, db):
    from rest_framework.test import APIClient
    irma = make_store(usa_gateway_da_plataforma=True)
    r = APIClient().get(f'/api/v1/stores/{irma.slug}/app-config/')
    assert r.status_code == 200
    assert r.json()['payment']['cartao'] == {'gateway': 'pagarme', 'public_key': 'pk_y'}
