from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.stores.models import Store, StoreSubscription
from apps.stores.services import subscription_service
from apps.webhooks.handlers.mercadopago_handler import MercadoPagoHandler

User = get_user_model()


class SetupFeePaidTest(TestCase):
    def test_marks_setup_fee_paid_on_approved(self):
        owner = User.objects.create_user(username='owner-sf1', password='x')
        store = Store.objects.create(name='Loja', slug='loja-sf', owner=owner)
        StoreSubscription.objects.create(store=store, mp_setup_payment_id='PREF-9')
        res = subscription_service.mark_setup_fee_paid('setup:loja-sf', 'approved')
        self.assertTrue(res['processed'])
        sub = StoreSubscription.objects.get(store=store)
        self.assertTrue(sub.setup_fee_paid)

    def test_ignores_non_approved(self):
        owner = User.objects.create_user(username='owner-sf2', password='x')
        store = Store.objects.create(name='Loja', slug='loja-sf2', owner=owner)
        StoreSubscription.objects.create(store=store, mp_setup_payment_id='PREF-8')
        res = subscription_service.mark_setup_fee_paid('setup:loja-sf2', 'pending')
        self.assertFalse(res['processed'])
        self.assertFalse(StoreSubscription.objects.get(store=store).setup_fee_paid)

    def test_unknown_store_is_safe(self):
        res = subscription_service.mark_setup_fee_paid('setup:nao-existe', 'approved')
        self.assertFalse(res['processed'])


class SetupFeeWebhookHandlerTest(TestCase):
    """Exercita o desvio no _handle_payment_webhook (inline e via fetch)."""

    def _store_with_sub(self, slug):
        owner = User.objects.create_user(username=f'owner-{slug}', password='x')
        store = Store.objects.create(name='Loja', slug=slug, owner=owner)
        StoreSubscription.objects.create(store=store, mp_setup_payment_id='PREF-X')
        return store

    def test_handler_inline_external_reference_marks_paid(self):
        store = self._store_with_sub('loja-h1')
        payload = {'type': 'payment', 'external_reference': 'setup:loja-h1',
                   'status': 'approved', 'data': {'id': '999'}}
        res = MercadoPagoHandler().handle(None, payload, {})
        self.assertTrue(res['processed'])
        self.assertTrue(StoreSubscription.objects.get(store=store).setup_fee_paid)

    @patch('apps.stores.services.subscription_service._sdk')
    def test_handler_fetches_setup_payment_when_payload_bare(self, sdk_p):
        # Webhook cru do MP: {type, data:{id}} sem external_reference nem status.
        store = self._store_with_sub('loja-h2')
        sdk = MagicMock()
        sdk.payment().get.return_value = {
            'status': 200,
            'response': {'external_reference': 'setup:loja-h2', 'status': 'approved'},
        }
        sdk_p.return_value = sdk
        payload = {'type': 'payment', 'data': {'id': 'PAY-1'}}
        res = MercadoPagoHandler().handle(None, payload, {})
        self.assertTrue(res['processed'])
        self.assertTrue(StoreSubscription.objects.get(store=store).setup_fee_paid)

    @patch('apps.stores.services.subscription_service._sdk')
    def test_handler_non_setup_payment_falls_through(self, sdk_p):
        # Pagamento que não é da plataforma: fetch não acha 'setup:' → order_not_found.
        sdk = MagicMock()
        sdk.payment().get.return_value = {
            'status': 200,
            'response': {'external_reference': 'pedido:123', 'status': 'approved'},
        }
        sdk_p.return_value = sdk
        payload = {'type': 'payment', 'data': {'id': 'PAY-404'}}
        res = MercadoPagoHandler().handle(None, payload, {})
        self.assertFalse(res['processed'])
        self.assertEqual(res['reason'], 'order_not_found')
