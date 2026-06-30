from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from apps.stores.models import Store, StoreSubscription
from apps.stores.services import subscription_service


def _mp_mock():
    sdk = MagicMock()
    sdk.preapproval().create.return_value = {
        'status': 201,
        'response': {'id': 'PRE-1', 'init_point': 'https://mp/sub'},
    }
    sdk.preference().create.return_value = {
        'status': 201,
        'response': {'id': 'PREF-1', 'init_point': 'https://mp/setup'},
    }
    return sdk


@override_settings(BILLING_SETUP_FEE_ENABLED=True)
class SetupFeeChargeTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'owner@x.com', 'x')
        self.store = Store.objects.create(
            name='Loja', slug='loja', owner=self.owner,
            status=Store.StoreStatus.ACTIVE,
        )

    @patch('apps.stores.billing.charges_setup_fee', return_value=True)
    @patch('apps.stores.services.subscription_service._sdk')
    def test_setup_fee_returns_setup_init_point(self, sdk_p, _fee):
        sdk_p.return_value = _mp_mock()
        out = subscription_service.create_subscription(
            self.store, 'pro', 'dono@x.com', 'https://painel/plano')
        self.assertEqual(out['setup_init_point'], 'https://mp/setup')
        sub = StoreSubscription.objects.get(store=self.store)
        self.assertEqual(sub.mp_setup_payment_id, 'PREF-1')

    @patch('apps.stores.billing.charges_setup_fee', return_value=False)
    @patch('apps.stores.services.subscription_service._sdk')
    def test_no_setup_fee_when_plan_toggle_off(self, sdk_p, _fee):
        sdk_p.return_value = _mp_mock()
        out = subscription_service.create_subscription(
            self.store, 'pro', 'dono@x.com', 'https://painel/plano')
        self.assertNotIn('setup_init_point', out)

    @override_settings(BILLING_SETUP_FEE_ENABLED=False)
    @patch('apps.stores.billing.charges_setup_fee', return_value=True)
    @patch('apps.stores.services.subscription_service._sdk')
    def test_global_killswitch_disables_setup_fee(self, sdk_p, _fee):
        sdk_p.return_value = _mp_mock()
        out = subscription_service.create_subscription(
            self.store, 'pro', 'dono@x.com', 'https://painel/plano')
        self.assertNotIn('setup_init_point', out)
