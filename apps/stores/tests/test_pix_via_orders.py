"""PIX criado pela Orders API (/v1/orders), como o cartão já faz.

O PIX nascia em POST /v1/payments desde 13/03/2026 — a API antiga. A aplicação
está registrada no MP como "Checkout Transparente via Orders", e em 19/08 o MP
passou a barrar a rota antiga para aplicações assim: 403 PolicyAgent em TODO
método (pix, boleto, cartão), enquanto /v1/orders respondia 201 com QR válido.

O cartão já andava pela Orders desde 17/06 (f0dbd18). O PIX passa a usar o
mesmo módulo, mesmo endpoint, mesma interpretação de resposta.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.stores.models import Store, StoreOrder, StorePayment
from apps.stores.services import mp_orders
from apps.stores.services.checkout_service import CheckoutService

# Resposta real capturada da Orders API em 19/08/2026.
ORDERS_PIX_201 = {
    'id': 'ORD01M0D26RV',
    'status': 'action_required',
    'status_detail': 'waiting_transfer',
    'transactions': {'payments': [{
        'id': 'PAY01M0D26RVH5P67W2W86VH5PRV3',
        'amount': '39.33',
        'date_of_expiration': '2026-08-20T13:08:42.328+00:00',
        'status': 'action_required',
        'status_detail': 'waiting_transfer',
        'payment_method': {
            'id': 'pix',
            'type': 'bank_transfer',
            'ticket_url': 'https://www.mercadopago.com.br/payments/174584002818/ticket',
            'qr_code': '00020126360014br.gov.bcb.pix...5910CARDAPIDEX6304134C',
            'qr_code_base64': 'iVBORw0KGgoAAAANSUhEUg',
        },
    }]},
}


class BuildPixOrderPayloadTests(TestCase):
    def setUp(self):
        User = get_user_model()
        owner = User.objects.create_user(username='dono_px', email='d@px.com', password='x')
        self.store = Store.objects.create(name='Loja PX', slug='loja-px', owner=owner)
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Maria Silva',
            customer_email='maria@teste.com', customer_phone='63999990000',
            subtotal=Decimal('39.33'), total=Decimal('39.33'),
            delivery_address={
                'street_name': 'Q 912 Sul Alameda 3', 'street_number': '2',
                'city': 'Palmas', 'state': 'TO', 'zip_code': '77023-442',
            },
        )

    def test_metodo_e_pix_bank_transfer(self):
        p = mp_orders.build_pix_order_payload(self.order, 'maria@teste.com')
        pm = p['transactions']['payments'][0]['payment_method']
        self.assertEqual(pm['id'], 'pix')
        self.assertEqual(pm['type'], 'bank_transfer')

    def test_nao_manda_expiration_time(self):
        """A Orders API recusa o payload inteiro com 400 unsupported_properties."""
        p = mp_orders.build_pix_order_payload(self.order, 'maria@teste.com')
        self.assertNotIn('expiration_time', p['transactions']['payments'][0]['payment_method'])

    def test_manda_endereco_do_pagador(self):
        """Requisito de qualidade do MP: payer.address.* sobe a aprovação."""
        p = mp_orders.build_pix_order_payload(self.order, 'maria@teste.com')
        addr = p['payer']['address']
        for campo in ('zip_code', 'street_name', 'street_number', 'city', 'state'):
            self.assertIn(campo, addr)

    def test_valor_bate_com_o_total(self):
        p = mp_orders.build_pix_order_payload(self.order, 'maria@teste.com')
        self.assertEqual(p['total_amount'], '39.33')
        self.assertEqual(p['transactions']['payments'][0]['amount'], '39.33')


class ExtractPixTests(TestCase):
    def test_extrai_qr_ticket_e_id(self):
        d = mp_orders.extract_pix(ORDERS_PIX_201)
        # payment_id é o id CONSULTÁVEL (numérico, do ticket_url); o ULID da
        # Orders API fica em order_payment_id. Ver IdNumericoParaConsultaTests.
        self.assertEqual(d['payment_id'], '174584002818')
        self.assertEqual(d['order_payment_id'], 'PAY01M0D26RVH5P67W2W86VH5PRV3')
        self.assertTrue(d['qr_code'].startswith('00020126'))
        self.assertEqual(d['qr_code_base64'], 'iVBORw0KGgoAAAANSUhEUg')
        self.assertIn('ticket', d['ticket_url'])

    def test_corpo_vazio_nao_explode(self):
        self.assertEqual(mp_orders.extract_pix({}), {})

    def test_interpret_trata_action_required_como_pendente(self):
        ok, st, pid, _ = mp_orders.interpret(201, ORDERS_PIX_201)
        self.assertTrue(ok)
        self.assertEqual(st, 'pending')


@override_settings(MERCADO_PAGO_ACCESS_TOKEN='APP_USR-teste', BASE_URL='https://backend.teste')
class CreatePaymentUsaOrdersTests(TestCase):
    def setUp(self):
        User = get_user_model()
        owner = User.objects.create_user(username='dono_px2', email='d2@px.com', password='x')
        self.store = Store.objects.create(name='Loja PX2', slug='loja-px2', owner=owner)
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Maria Silva',
            customer_email='maria@teste.com', customer_phone='63999990000',
            subtotal=Decimal('39.33'), total=Decimal('39.33'),
        )

    def _cred(self):
        return mock.patch.object(
            CheckoutService, 'get_payment_credentials',
            return_value={'provider': 'mercadopago', 'access_token': 'APP_USR-teste', 'sandbox': False},
        )

    def test_pix_vai_pela_orders_e_nao_pela_api_antiga(self):
        sdk = mock.MagicMock()
        with self._cred(), mock.patch('mercadopago.SDK', return_value=sdk), \
                mock.patch.object(mp_orders, 'create_order', return_value=(201, ORDERS_PIX_201)) as criar:
            res = CheckoutService.create_payment(self.order, payment_method='pix')

        criar.assert_called_once()
        sdk.payment.return_value.create.assert_not_called()
        self.assertTrue(res['success'], res)
        self.assertEqual(res['pix_code'], ORDERS_PIX_201['transactions']['payments'][0]['payment_method']['qr_code'])

    def test_espelha_no_pedido_e_cria_cobranca(self):
        sdk = mock.MagicMock()
        with self._cred(), mock.patch('mercadopago.SDK', return_value=sdk), \
                mock.patch.object(mp_orders, 'create_order', return_value=(201, ORDERS_PIX_201)):
            CheckoutService.create_payment(self.order, payment_method='pix')

        self.order.refresh_from_db()
        self.assertTrue(self.order.pix_code.startswith('00020126'))
        self.assertEqual(self.order.payment_status, StoreOrder.PaymentStatus.PENDING)
        self.assertTrue(StorePayment.objects.filter(order=self.order, payment_method='pix').exists())


class IdNumericoParaConsultaTests(TestCase):
    """O id da cobrança precisa ser consultável — senão o PIX pago nunca confirma.

    A Orders API devolve `PAY01M0D2HTZ...` (ULID). Mas GET /v1/payments/PAY01...
    responde 404: o webhook, o poller de reconciliação e o tasks.py todos fazem
    `sdk.payment().get(external_id)`. Salvar o ULID significaria cliente pagando
    e pedido preso em "pendente" para sempre.

    O id numérico consultável vive dentro do ticket_url:
    https://www.mercadopago.com.br/payments/174584705322/ticket?...
    """

    def test_extrai_id_numerico_do_ticket_url(self):
        d = mp_orders.extract_pix({'transactions': {'payments': [{
            'id': 'PAY01M0D2HTZDR0YXQKSRHRV3EZA4',
            'payment_method': {
                'qr_code': '000201',
                'ticket_url': 'https://www.mercadopago.com.br/payments/174584705322/ticket?caller_id=1',
            },
        }]}})
        self.assertEqual(d['payment_id'], '174584705322')
        self.assertEqual(d['order_payment_id'], 'PAY01M0D2HTZDR0YXQKSRHRV3EZA4')

    def test_sem_ticket_url_cai_no_ulid(self):
        d = mp_orders.extract_pix({'transactions': {'payments': [{
            'id': 'PAY01XYZ', 'payment_method': {'qr_code': '000201'},
        }]}})
        self.assertEqual(d['payment_id'], 'PAY01XYZ')

    def test_cobranca_salva_o_id_consultavel(self):
        corpo = {
            'status': 'action_required',
            'transactions': {'payments': [{
                'id': 'PAY01ULID',
                'status': 'action_required',
                'payment_method': {
                    'id': 'pix', 'type': 'bank_transfer',
                    'qr_code': '00020126ABC', 'qr_code_base64': 'B64',
                    'ticket_url': 'https://www.mercadopago.com.br/payments/999888777/ticket',
                },
            }]},
        }
        User = get_user_model()
        owner = User.objects.create_user(username='dono_num', email='d@num.com', password='x')
        store = Store.objects.create(name='Loja NUM', slug='loja-num', owner=owner)
        order = StoreOrder.objects.create(
            store=store, customer_name='Maria', customer_email='m@t.com',
            customer_phone='63999990000', subtotal=Decimal('10.00'), total=Decimal('10.00'),
        )
        with mock.patch.object(
            CheckoutService, 'get_payment_credentials',
            return_value={'provider': 'mercadopago', 'access_token': 'T', 'sandbox': False},
        ), mock.patch('mercadopago.SDK'), \
                mock.patch.object(mp_orders, 'create_order', return_value=(201, corpo)):
            CheckoutService.create_payment(order, payment_method='pix')

        sp = StorePayment.objects.get(order=order)
        self.assertEqual(sp.external_id, '999888777')
        order.refresh_from_db()
        self.assertEqual(order.payment_id, '999888777')
