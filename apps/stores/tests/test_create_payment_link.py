"""Fase 3 — Link de pagamento (Checkout Pro / preference).

Diferente do PIX cru, `create_payment(..., 'link', ...)` gera uma PREFERENCE do
Mercado Pago e devolve o `init_point` (página hospedada onde o cliente escolhe
cartão/PIX/boleto). A cobrança vira um StorePayment (fonte da verdade) com
`payment_url` preenchida e `external_reference` único (`splink:<token>`), pra o
webhook reconciliar depois (o payment id só existe quando o cliente paga).
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder, StorePayment

User = get_user_model()


def _mp_pref_mock(pref_id='PREF1', init_point='https://mp.example/checkout/PREF1'):
    """Mock do mercadopago.SDK que devolve 201 ao criar uma preference."""
    sdk = MagicMock()
    sdk.preference().create.return_value = {
        'status': 201,
        'response': {
            'id': pref_id,
            'init_point': init_point,
            'sandbox_init_point': init_point + '?sb=1',
        },
    }
    return sdk


class CreatePaymentLinkTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-link', password='x', email='owner@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Link', slug='loja-link', owner=self.owner, status='active',
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
    def test_link_avulso_creates_storepayment_with_url(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_pref_mock('PREFAV', 'https://mp.example/checkout/PREFAV')

        result = CheckoutService.create_payment(
            None, 'link', {'payer_email': 'p@e.com', 'payer_name': 'Fulano'},
            amount=Decimal('50.00'), store=self.store, description='Sinal do evento',
        )

        self.assertTrue(result['success'], result)
        self.assertEqual(result['payment_url'], 'https://mp.example/checkout/PREFAV')
        self.assertTrue(result['requires_redirect'])
        self.assertEqual(result['payment_method'], 'link')

        sp = StorePayment.objects.get(id=result['payment_db_id'])
        self.assertIsNone(sp.order_id)
        self.assertEqual(sp.store_id, self.store.id)
        self.assertEqual(sp.amount, Decimal('50.00'))
        self.assertEqual(sp.payment_url, 'https://mp.example/checkout/PREFAV')
        self.assertEqual(sp.external_id, 'PREFAV')  # preference id (até o pagto existir)
        self.assertTrue(sp.external_reference.startswith('splink:'))
        self.assertEqual(sp.status, StorePayment.PaymentStatus.PENDING)
        # Sem gravar a descrição, a lista de cobranças do painel vira uma pilha
        # de valores sem rótulo — em prod havia 5 pendentes assim, e o lojista
        # não tinha como saber qual link era de quem.
        self.assertEqual((sp.metadata or {}).get('description'), 'Sinal do evento')

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value={'access_token': 'TOKEN', 'provider': 'mercadopago'})
    @patch('mercadopago.SDK')
    def test_link_avulso_sem_descricao_nao_inventa_rotulo(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_pref_mock('PREFAV2', 'https://mp.example/c/PREFAV2')

        result = CheckoutService.create_payment(
            None, 'link', {}, amount=Decimal('20.00'), store=self.store,
        )

        sp = StorePayment.objects.get(id=result['payment_db_id'])
        self.assertNotIn('description', sp.metadata or {})

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value={'access_token': 'TOKEN'})
    @patch('mercadopago.SDK')
    def test_link_for_order_uses_amount_due(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_pref_mock('PREFORD', 'https://mp.example/checkout/PREFORD')
        order = self._order('100.00')

        result = CheckoutService.create_payment(order, 'link')

        self.assertTrue(result['success'], result)
        self.assertEqual(result['payment_url'], 'https://mp.example/checkout/PREFORD')
        sp = StorePayment.objects.get(order=order)
        self.assertEqual(sp.amount, Decimal('100.00'))
        self.assertEqual(sp.payment_url, 'https://mp.example/checkout/PREFORD')
        order.refresh_from_db()
        self.assertEqual(order.payment_preference_id, 'PREFORD')

    @patch('apps.stores.services.checkout_service.CheckoutService.get_payment_credentials',
           return_value={'access_token': 'TOKEN'})
    @patch('mercadopago.SDK')
    def test_link_avulso_requires_amount(self, mock_sdk, _creds):
        from apps.stores.services.checkout_service import CheckoutService
        mock_sdk.return_value = _mp_pref_mock()

        with self.assertRaises(ValueError):
            CheckoutService.create_payment(None, 'link', store=self.store)

    def test_webhook_reconciles_link_by_external_reference(self):
        """O pagamento real (payment id) só existe quando o cliente paga; o
        webhook casa a cobrança-link pelo external_reference e grava o payment id."""
        from apps.stores.services.checkout_service import CheckoutService
        sp = StorePayment.objects.create(
            store=self.store,
            amount=Decimal('50.00'),
            payment_method=StorePayment.PaymentMethod.OTHER,
            status=StorePayment.PaymentStatus.PENDING,
            external_id='PREFAV',  # preference id no momento da criação
            external_reference='splink:abc123',
            payment_url='https://mp.example/checkout/PREFAV',
        )

        CheckoutService.process_payment_webhook(
            'PAYREAL999', 'approved', external_reference='splink:abc123',
        )

        sp.refresh_from_db()
        self.assertEqual(sp.status, StorePayment.PaymentStatus.COMPLETED)
        self.assertEqual(sp.external_id, 'PAYREAL999')  # agora aponta pro pagto real
        self.assertIsNotNone(sp.paid_at)
