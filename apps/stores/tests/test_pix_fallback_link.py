"""PIX recusado pelo Mercado Pago NÃO vira link de pagamento.

Histórico: em 19/08 entrou um desvio PIX→link (o MP bloqueava /v1/payments).
O PIX migrou para a Orders API e o desvio ficou — MUDO. Toda vez que o payload
do PIX quebrava (sobrenome vazio em 31/08, combo sem external_code em 17/nov)
o cliente e o atendente do PDV recebiam um link do checkout do MP no lugar do
copia-e-cola, e ninguém via que o PIX tinha morrido. O dono vetou: escolheu
PIX, é PIX. Recusa = erro honesto com o motivo do MP.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.stores.models import Store, StoreOrder, StorePayment
from apps.stores.services import mp_orders as mp_orders_mod
from apps.stores.services.checkout_service import CheckoutService

#: Recusa da Orders API — o PIX nasce lá desde a migração de 19/08.
RECUSA_ORDERS = (403, {'errors': [{'code': 'forbidden',
                                   'message': 'At least one policy returned UNAUTHORIZED.'}]})

BLOQUEIO_MP = {
    'status': 403,
    'response': {
        'status': 403,
        'blocked_by': 'PolicyAgent',
        'code': 'PA_UNAUTHORIZED_RESULT_FROM_POLICIES',
        'message': 'At least one policy returned UNAUTHORIZED.',
    },
}

PREFERENCE_OK = {
    'status': 201,
    'response': {
        'id': 'pref-123',
        'init_point': 'https://mp.com/checkout/pref-123',
        'sandbox_init_point': 'https://sandbox.mp.com/checkout/pref-123',
    },
}


def _sdk(payment_result, preference_result):
    sdk = mock.MagicMock()
    sdk.payment.return_value.create.return_value = payment_result
    sdk.preference.return_value.create.return_value = preference_result
    return sdk


@override_settings(MERCADO_PAGO_ACCESS_TOKEN='APP_USR-teste', BASE_URL='https://backend.teste')
class PixFallbackParaLinkTests(TestCase):
    def setUp(self):
        User = get_user_model()
        owner = User.objects.create_user(username='dono_fb', email='dono@fb.com', password='x')
        self.store = Store.objects.create(name='Loja FB', slug='loja-fb', owner=owner)
        self.order = StoreOrder.objects.create(
            store=self.store,
            customer_name='Cliente Teste',
            customer_email='cliente@teste.com',
            customer_phone='63999990000',
            subtotal=Decimal('39.33'),
            total=Decimal('39.33'),
        )

    def _credenciais(self):
        return mock.patch.object(
            CheckoutService, 'get_payment_credentials',
            return_value={'provider': 'mercadopago', 'access_token': 'APP_USR-teste', 'sandbox': False},
        )

    def test_pix_recusado_nao_vira_link(self):
        sdk = _sdk(BLOQUEIO_MP, PREFERENCE_OK)
        with self._credenciais(), mock.patch('mercadopago.SDK', return_value=sdk), \
                mock.patch.object(mp_orders_mod, 'create_order', return_value=RECUSA_ORDERS):
            res = CheckoutService.create_payment(self.order, payment_method='pix')

        self.assertFalse(res['success'], res)
        self.assertNotIn('init_point', res)
        sdk.preference.return_value.create.assert_not_called()
        self.assertFalse(StorePayment.objects.filter(order=self.order).exists())
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, StoreOrder.PaymentStatus.FAILED)

    def test_pix_ok_nao_usa_fallback(self):
        """Caminho feliz intocado: PIX que funciona não vira link.

        O PIX nasce na Orders API — o mock é do mp_orders.create_order, não
        mais do SDK antigo.
        """
        from apps.stores.services import mp_orders
        orders_ok = (201, {
            'status': 'action_required',
            'transactions': {'payments': [{
                'id': 'PAY01OK',
                'status': 'action_required',
                'payment_method': {
                    'id': 'pix', 'type': 'bank_transfer',
                    'qr_code': 'QRCODE', 'qr_code_base64': 'BASE64',
                    'ticket_url': 'https://www.mercadopago.com.br/payments/987654/ticket',
                },
            }]},
        })
        sdk = _sdk(BLOQUEIO_MP, PREFERENCE_OK)
        with self._credenciais(), mock.patch('mercadopago.SDK', return_value=sdk), \
                mock.patch.object(mp_orders, 'create_order', return_value=orders_ok):
            res = CheckoutService.create_payment(self.order, payment_method='pix')

        self.assertEqual(res['payment_method'], 'pix')
        self.assertEqual(res['pix_code'], 'QRCODE')
        sdk.preference.return_value.create.assert_not_called()


@override_settings(MERCADO_PAGO_ACCESS_TOKEN='APP_USR-teste', BASE_URL='https://backend.teste')
class LinkNaoDuplicaCobrancaTests(TestCase):
    """Clicar duas vezes em "Gerar cobrança" não pode criar duas cobranças.

    O PIX já reusava a cobrança pendente de mesmo valor; o link não. No pedido
    CE-2609098839 (09/set) três cliques viraram três links vivos de R$ 57,73 —
    o cliente podia pagar dois, e o painel exibia três "Aguardando" idênticos
    sem dizer qual mandar.
    """

    def setUp(self):
        User = get_user_model()
        owner = User.objects.create_user(username='dono_dup', email='dono@dup.com', password='x')
        self.store = Store.objects.create(name='Loja Dup', slug='loja-dup', owner=owner)
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Cliente Teste',
            customer_email='cliente@teste.com', customer_phone='63999990000',
            subtotal=Decimal('57.73'), total=Decimal('57.73'),
        )

    def _credenciais(self):
        return mock.patch.object(
            CheckoutService, 'get_payment_credentials',
            return_value={'provider': 'mercadopago', 'access_token': 'APP_USR-teste', 'sandbox': False},
        )

    def _gerar(self, sdk):
        with self._credenciais(), mock.patch('mercadopago.SDK', return_value=sdk), \
                mock.patch.object(mp_orders_mod, 'create_order', return_value=RECUSA_ORDERS):
            return CheckoutService.create_payment(self.order, payment_method='link')

    def test_segundo_clique_reusa_o_mesmo_link(self):
        sdk = _sdk(BLOQUEIO_MP, PREFERENCE_OK)
        primeiro = self._gerar(sdk)
        segundo = self._gerar(sdk)

        self.assertEqual(StorePayment.objects.filter(order=self.order).count(), 1,
                         'cada clique estava criando uma cobrança nova')
        self.assertEqual(segundo['payment_url'], primeiro['payment_url'])
        self.assertEqual(sdk.preference.return_value.create.call_count, 1,
                         'nao pode criar uma preference nova no MP a cada clique')

    def test_valor_diferente_gera_cobranca_nova(self):
        """Reuso é por valor: cobrar outro valor é outra cobrança."""
        sdk = _sdk(BLOQUEIO_MP, PREFERENCE_OK)
        self._gerar(sdk)
        with self._credenciais(), mock.patch('mercadopago.SDK', return_value=sdk), \
                mock.patch.object(mp_orders_mod, 'create_order', return_value=RECUSA_ORDERS):
            CheckoutService.create_payment(self.order, payment_method='link', amount=Decimal('10.00'))

        self.assertEqual(StorePayment.objects.filter(order=self.order).count(), 2)
