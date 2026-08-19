"""PIX que o Mercado Pago recusa cai no link de pagamento, não em 'pagamento falhou'.

Em 19/08 o MP passou a devolver 403 PA_UNAUTHORIZED_RESULT_FROM_POLICIES em
POST /v1/payments (conta bloqueada, chaves revogadas). Toda loja sem gateway
próprio ficou sem PIX: o pedido era criado e o cliente via "pagamento falhou",
sem nenhuma forma de pagar. O Checkout Pro (preference) seguia funcionando.

Enquanto a criação de cobrança direta estiver bloqueada, cair no link mantém a
venda de pé. Se o link também falhar, vale o comportamento antigo: FAILED e
cupom devolvido — honesto, porque aí realmente não há como pagar.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.stores.models import Store, StoreOrder, StorePayment
from apps.stores.services.checkout_service import CheckoutService

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

    def test_pix_bloqueado_cai_no_link(self):
        sdk = _sdk(BLOQUEIO_MP, PREFERENCE_OK)
        with self._credenciais(), mock.patch('mercadopago.SDK', return_value=sdk):
            res = CheckoutService.create_payment(self.order, payment_method='pix')

        self.assertTrue(res['success'], res)
        self.assertTrue(res['requires_redirect'])
        self.assertEqual(res['init_point'], 'https://mp.com/checkout/pref-123')

    def test_pedido_fica_pendente_e_nao_falhado(self):
        sdk = _sdk(BLOQUEIO_MP, PREFERENCE_OK)
        with self._credenciais(), mock.patch('mercadopago.SDK', return_value=sdk):
            CheckoutService.create_payment(self.order, payment_method='pix')

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, StoreOrder.PaymentStatus.PENDING)

    def test_cobranca_do_link_e_registrada(self):
        sdk = _sdk(BLOQUEIO_MP, PREFERENCE_OK)
        with self._credenciais(), mock.patch('mercadopago.SDK', return_value=sdk):
            CheckoutService.create_payment(self.order, payment_method='pix')

        self.assertTrue(StorePayment.objects.filter(order=self.order).exists())

    def test_pix_ok_nao_usa_fallback(self):
        """Caminho feliz intocado: PIX que funciona não vira link."""
        pix_ok = {
            'status': 201,
            'response': {
                'id': 987654,
                'status': 'pending',
                'point_of_interaction': {'transaction_data': {
                    'qr_code': 'QRCODE', 'qr_code_base64': 'BASE64', 'ticket_url': 'http://t'}},
            },
        }
        sdk = _sdk(pix_ok, PREFERENCE_OK)
        with self._credenciais(), mock.patch('mercadopago.SDK', return_value=sdk):
            res = CheckoutService.create_payment(self.order, payment_method='pix')

        self.assertEqual(res['payment_method'], 'pix')
        self.assertEqual(res['pix_code'], 'QRCODE')
        sdk.preference.return_value.create.assert_not_called()

    def test_link_tambem_falha_mantem_comportamento_antigo(self):
        sdk = _sdk(BLOQUEIO_MP, {'status': 403, 'response': {'message': 'tambem bloqueado'}})
        with self._credenciais(), mock.patch('mercadopago.SDK', return_value=sdk):
            res = CheckoutService.create_payment(self.order, payment_method='pix')

        self.assertFalse(res['success'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, StoreOrder.PaymentStatus.FAILED)
