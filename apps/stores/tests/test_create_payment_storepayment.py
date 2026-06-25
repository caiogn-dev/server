"""Fase 3 — B2: CheckoutService.create_payment cria StorePayment (PIX).

- Cria 1 StorePayment(pending) com amount = amount_due (default) ou amount param.
- Espelha order.pix_* (compat storefront/print/bot).
- Reuso de PENDING não-expirada (idempotência): 2x não duplica.
- Suporta order=None (cobrança avulsa) com store + amount.
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StorePayment

User = get_user_model()


def _mp_sdk_mock(payment_id='MP123'):
    """Mock do mercadopago.SDK que devolve 201 com dados PIX."""
    sdk = MagicMock()
    sdk.payment().create.return_value = {
        'status': 201,
        'response': {
            'id': payment_id,
            'status': 'pending',
            'point_of_interaction': {
                'transaction_data': {
                    'qr_code': f'PIXCOPIACOLA-{payment_id}',
                    'qr_code_base64': 'BASE64IMG',
                    'ticket_url': f'https://mp.example/{payment_id}',
                    'expiration_date': '2026-12-31T23:59:59.000-03:00',
                }
            },
        },
    }
    return sdk


class CreatePaymentStorePaymentTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-cp', password='x', email='owner@real.com',
        )
        self.store = Store.objects.create(
            name='Loja CP', slug='loja-cp', owner=self.owner, status='active',
        )

    def _order(self, total='100.00'):
        return StoreOrder.objects.create(
            store=self.store, customer_name='Cliente', customer_phone='5599999999999',
            customer_email='cli@real.com',
            subtotal=Decimal(total), total=Decimal(total),
        )

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value={'access_token': 'TOKEN', 'provider': 'mercadopago'})
    @patch('mercadopago.SDK')
    def test_pix_creates_storepayment_and_mirrors_order(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_sdk_mock('MPONE')
        order = self._order('100.00')

        result = CheckoutService.create_payment(order, 'pix')

        self.assertTrue(result['success'], result)
        payments = StorePayment.objects.filter(order=order)
        self.assertEqual(payments.count(), 1)
        sp = payments.first()
        self.assertEqual(sp.status, StorePayment.PaymentStatus.PENDING)
        self.assertEqual(sp.amount, Decimal('100.00'))  # default = amount_due
        self.assertEqual(sp.external_id, 'MPONE')
        self.assertEqual(sp.qr_code, 'PIXCOPIACOLA-MPONE')
        self.assertEqual(sp.ticket_url, 'https://mp.example/MPONE')
        self.assertEqual(sp.store_id, self.store.id)
        # espelho no pedido
        order.refresh_from_db()
        self.assertEqual(order.pix_code, 'PIXCOPIACOLA-MPONE')
        self.assertEqual(order.payment_id, 'MPONE')
        # contrato de retorno
        self.assertEqual(result['payment_db_id'], str(sp.id))
        self.assertEqual(Decimal(str(result['amount'])), Decimal('100.00'))

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value={'access_token': 'TOKEN'})
    @patch('mercadopago.SDK')
    def test_amount_param_charges_partial(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_sdk_mock('MPPART')
        order = self._order('100.00')

        result = CheckoutService.create_payment(order, 'pix', amount=Decimal('30.00'))

        self.assertTrue(result['success'])
        sp = StorePayment.objects.get(order=order)
        self.assertEqual(sp.amount, Decimal('30.00'))

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value={'access_token': 'TOKEN'})
    @patch('mercadopago.SDK')
    def test_reuse_pending_does_not_duplicate(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        sdk = _mp_sdk_mock('MPREUSE')
        mock_sdk.return_value = sdk
        order = self._order('100.00')

        CheckoutService.create_payment(order, 'pix')
        CheckoutService.create_payment(order, 'pix')

        self.assertEqual(StorePayment.objects.filter(order=order).count(), 1)
        # SDK só chamado uma vez (segunda reusou a cobrança pendente)
        self.assertEqual(sdk.payment().create.call_count, 1)

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value={'access_token': 'TOKEN'})
    @patch('mercadopago.SDK')
    def test_avulso_order_none(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_sdk_mock('MPAVULSO')

        result = CheckoutService.create_payment(
            None, 'pix', amount=Decimal('25.00'),
            store=self.store, description='Cobrança avulsa teste',
        )

        self.assertTrue(result['success'], result)
        sp = StorePayment.objects.get(external_id='MPAVULSO')
        self.assertIsNone(sp.order_id)
        self.assertEqual(sp.store_id, self.store.id)
        self.assertEqual(sp.amount, Decimal('25.00'))
