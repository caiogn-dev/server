"""
Assinatura SaaS (MercadoPago preapproval) — com o SDK do MP mockado.
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from apps.stores.models import Store, StoreSubscription
from apps.stores.services import subscription_service


class SubscriptionServiceTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('o', 'o@x.com', 'x')
        self.store = Store.objects.create(
            name='Loja', slug='loja', owner=self.owner, status=Store.StoreStatus.ACTIVE
        )

    def _fake_sdk(self, init_point='https://mp/checkout/abc', pid='pre_123'):
        sdk = MagicMock()
        sdk.preapproval().create.return_value = {
            'status': 201,
            'response': {'id': pid, 'init_point': init_point},
        }
        return sdk

    def test_create_subscription_gera_init_point_e_persiste(self):
        with patch.object(subscription_service, '_sdk', return_value=self._fake_sdk()):
            res = subscription_service.create_subscription(
                self.store, 'pro', 'dono@x.com', 'https://painel/plano'
            )
        self.assertEqual(res['init_point'], 'https://mp/checkout/abc')
        self.assertEqual(res['preapproval_id'], 'pre_123')
        sub = StoreSubscription.objects.get(store=self.store)
        self.assertEqual(sub.plan, 'pro')
        self.assertEqual(sub.status, StoreSubscription.Status.TRIALING)
        self.assertEqual(sub.mp_preapproval_id, 'pre_123')
        # O plano escolhido fica SÓ na assinatura — store.plan não muda até o
        # pagamento ser autorizado (senão ganha o plano sem pagar).
        self.store.refresh_from_db()
        self.assertEqual(self.store.plan, 'starter')

    def test_loja_exempt_nao_assina(self):
        self.store.billing_exempt = True
        self.store.save()
        with self.assertRaises(subscription_service.SubscriptionError):
            subscription_service.create_subscription(self.store, 'pro', 'd@x.com', 'http://x')

    def test_apply_preapproval_event_ativa(self):
        with patch.object(subscription_service, '_sdk', return_value=self._fake_sdk()):
            subscription_service.create_subscription(self.store, 'pro', 'd@x.com', 'http://x')
        r = subscription_service.apply_preapproval_event('pre_123', 'authorized')
        self.assertTrue(r['processed'])
        sub = StoreSubscription.objects.get(store=self.store)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        self.assertTrue(sub.setup_fee_paid)
        self.assertIsNotNone(sub.started_at)
        # Só agora (pagamento autorizado) o plano é aplicado na loja.
        self.store.refresh_from_db()
        self.assertEqual(self.store.plan, 'pro')

    def test_apply_preapproval_event_cancela(self):
        with patch.object(subscription_service, '_sdk', return_value=self._fake_sdk()):
            subscription_service.create_subscription(self.store, 'pro', 'd@x.com', 'http://x')
        # ativa primeiro (aplica o plano), depois cancela
        subscription_service.apply_preapproval_event('pre_123', 'authorized')
        subscription_service.apply_preapproval_event('pre_123', 'cancelled')
        sub = StoreSubscription.objects.get(store=self.store)
        self.assertEqual(sub.status, StoreSubscription.Status.CANCELED)
        # Ao cancelar, a loja perde o plano pago e volta pro starter.
        self.store.refresh_from_db()
        self.assertEqual(self.store.plan, 'starter')
