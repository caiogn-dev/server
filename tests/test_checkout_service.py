from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.stores.models import Store, StoreIntegration, StoreOrder
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


class CheckoutServiceTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='checkoutsvc',
            email='checkout@example.com',
            password='testpass123',
        )
        self.store = Store.objects.create(
            name='Ce Saladas',
            slug='ce-saladas',
            store_type=Store.StoreType.FOOD,
            status=Store.StoreStatus.ACTIVE,
            owner=self.user,
            metadata={'frontend_url': 'https://cesaladas.com.br'},
        )

    def _create_mp_integration(self, access_token='store-token', public_key='APP_USR-store-public'):
        integration = StoreIntegration.objects.create(
            store=self.store,
            integration_type=StoreIntegration.IntegrationType.MERCADOPAGO,
            name='Mercado Pago - Ce Saladas',
            status=StoreIntegration.IntegrationStatus.ACTIVE,
            webhook_url=f'/api/v1/stores/{self.store.slug}/webhooks/mercadopago/',
            settings={
                'public_key': public_key,
                'notification_url': f'/api/v1/stores/{self.store.slug}/webhooks/mercadopago/',
            },
        )
        integration.access_token = access_token
        integration.api_key = public_key
        integration.save()
        return integration

    def _create_order(self):
        return StoreOrder.objects.create(
            store=self.store,
            customer=self.user,
            customer_name='Teste Checkout',
            customer_email='checkout@example.com',
            customer_phone='63999999999',
            subtotal=Decimal('10.00'),
            discount=Decimal('0.00'),
            tax=Decimal('0.00'),
            delivery_fee=Decimal('0.00'),
            total=Decimal('10.00'),
        )

    @override_settings(
        MERCADO_PAGO_ACCESS_TOKEN='global-token',
        MERCADO_PAGO_GLOBAL_FALLBACK_ENABLED=True,
    )
    def test_get_payment_credentials_prefers_store_integration(self):
        self._create_mp_integration(access_token='store-token')

        credentials = CheckoutService.get_payment_credentials(self.store)

        self.assertEqual(credentials['access_token'], 'store-token')
        self.assertEqual(credentials['source'], 'store_integration')

    @override_settings(
        MERCADO_PAGO_ACCESS_TOKEN='global-token',
        MERCADO_PAGO_GLOBAL_FALLBACK_ENABLED=False,
    )
    def test_get_payment_credentials_can_disable_global_fallback(self):
        credentials = CheckoutService.get_payment_credentials(self.store)

        self.assertIsNone(credentials)

    @override_settings(
        BASE_URL='https://backend.pastita.com.br',
        FRONTEND_URL='https://pastita.com.br',
        MERCADO_PAGO_GLOBAL_FALLBACK_ENABLED=False,
    )
    def test_create_payment_uses_store_urls_for_redirect_and_webhook(self):
        self._create_mp_integration(access_token='store-token')
        order = self._create_order()

        captured = {}

        class FakePreferenceAPI:
            def create(self, payload):
                captured['payload'] = payload
                return {
                    'status': 201,
                    'response': {
                        'id': 'pref_123',
                        'init_point': 'https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=pref_123',
                    },
                }

        class FakeSDK:
            def __init__(self, access_token):
                captured['access_token'] = access_token

            def preference(self):
                return FakePreferenceAPI()

        fake_module = SimpleNamespace(SDK=FakeSDK)

        with patch.dict('sys.modules', {'mercadopago': fake_module}):
            response = CheckoutService.create_payment(order, 'credit_card')

        self.assertTrue(response['success'])
        self.assertEqual(captured['access_token'], 'store-token')
        self.assertEqual(
            captured['payload']['notification_url'],
            'https://backend.pastita.com.br/api/v1/stores/ce-saladas/webhooks/mercadopago/',
        )
        self.assertEqual(
            captured['payload']['back_urls']['success'],
            f'https://cesaladas.com.br/sucesso?order={order.id}',
        )
        self.assertEqual(
            captured['payload']['back_urls']['failure'],
            f'https://cesaladas.com.br/erro?order={order.id}',
        )
        self.assertEqual(
            captured['payload']['back_urls']['pending'],
            f'https://cesaladas.com.br/pendente?order={order.id}',
        )
