"""Webhook com topic='order' (Orders API) confirma o pagamento.

Desde a migração do PIX para /v1/orders, o MP notifica com `type: order` —
não mais `payment`. O handler só conhecia payment/merchant_order e jogava o
aviso fora ("Ignoring webhook topic: order"), deixando a confirmação por conta
do poller de 180s. Cliente pagava e o pedido demorava minutos para virar, ou
ficava para trás se o poller falhasse.

O payload do `order` traz external_reference (= id do nosso pedido) e o ULID do
pagamento. O id NUMÉRICO consultável está na cobrança que gravamos, então o
caminho é: external_reference → StorePayment → external_id numérico → mesmo
fluxo de sempre (idempotência, fidelidade, broadcast).
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.stores.models import Store, StoreOrder, StorePayment


def _payload_order(order_id, acao='order.processed', status_='processed'):
    return {
        'type': 'order',
        'action': acao,
        'api_version': 'v1',
        'live_mode': True,
        'user_id': '235180147',
        'data': {
            'id': 'ORD01M0D5A21F1P7Y4X9J8F2JFZT6',
            'external_reference': str(order_id),
            'status': status_,
            'status_detail': 'accredited',
            'total_amount': '39.33',
            'transactions': {'payments': [{
                'id': 'PAY01M0D5A21QE3A2FHBF11QYFSCZ',
                'amount': '39.33',
                'status': status_,
                'payment_method': {'id': 'pix', 'type': 'bank_transfer'},
            }]},
        },
    }


@override_settings(MERCADO_PAGO_WEBHOOK_SECRET='')
class WebhookOrderTopicTests(TestCase):
    def setUp(self):
        User = get_user_model()
        owner = User.objects.create_user(username='dono_wo', email='d@wo.com', password='x')
        self.store = Store.objects.create(name='Loja WO', slug='loja-wo', owner=owner)
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Sheslley Costa',
            customer_email='s@t.com', customer_phone='63999990000',
            subtotal=Decimal('39.33'), total=Decimal('39.33'),
            payment_method='pix',
        )
        self.pagamento = StorePayment.objects.create(
            order=self.order, store=self.store, amount=Decimal('39.33'),
            payment_method=StorePayment.PaymentMethod.PIX,
            status=StorePayment.PaymentStatus.PENDING,
            external_id='173658818323',              # numérico, consultável
            external_reference=str(self.order.id),   # o que o webhook manda
        )

    def _postar(self, payload):
        return self.client.post(
            reverse('mercadopago_webhook'), data=payload,
            content_type='application/json',
        )

    def test_order_pago_nao_e_mais_ignorado(self):
        sdk = mock.MagicMock()
        sdk.payment.return_value.get.return_value = {
            'status': 200,
            'response': {'id': '173658818323', 'status': 'approved',
                         'external_reference': str(self.order.id)},
        }
        with mock.patch('mercadopago.SDK', return_value=sdk), \
                mock.patch(
                    'apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
                    return_value={'access_token': 'T', 'provider': 'mercadopago'}):
            resp = self._postar(_payload_order(self.order.id))

        self.assertEqual(resp.status_code, 200)
        self.assertNotEqual(resp.json().get('status'), 'ignored')
        # Resolveu pelo id NUMÉRICO da cobrança, não pelo ULID do payload.
        sdk.payment.return_value.get.assert_called_once_with('173658818323')

    def test_sem_cobranca_correspondente_nao_explode(self):
        with mock.patch('mercadopago.SDK'):
            resp = self._postar(_payload_order('00000000-0000-0000-0000-000000000000'))
        self.assertEqual(resp.status_code, 200)

    def test_payload_sem_external_reference_nao_explode(self):
        p = _payload_order(self.order.id)
        p['data'].pop('external_reference')
        with mock.patch('mercadopago.SDK'):
            resp = self._postar(p)
        self.assertEqual(resp.status_code, 200)
