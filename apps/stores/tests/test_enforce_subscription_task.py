from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.stores.models import Store, StoreSubscription
from apps.stores.tasks import enforce_subscription_lifecycle
from apps.stores.services import subscription_service


def mk(slug, **store_kw):
    owner = User.objects.create_user(username=f'owner_{slug}', password='x')
    return Store.objects.create(name=slug, slug=slug, owner=owner, **store_kw)


def _fake_create_sdk(pid='pre_x'):
    sdk = MagicMock()
    sdk.preapproval().create.return_value = {
        'status': 201,
        'response': {'id': pid, 'init_point': 'https://mp/x'},
    }
    return sdk


@override_settings(BILLING_GRACE_DAYS=3, BILLING_DUNNING_DAYS=3, BILLING_ENFORCEMENT_ENABLED=True)
class EnforceSubscriptionTaskTest(TestCase):
    def test_expired_trial_downgrades_to_free(self):
        store = mk('s1', trial_ends_at=timezone.now() - timedelta(hours=1))
        sub = StoreSubscription.objects.create(store=store, status='trialing')
        res = enforce_subscription_lifecycle()
        sub.refresh_from_db()
        store.refresh_from_db()
        self.assertEqual(store.plan, 'free')
        self.assertEqual(sub.status, 'canceled')
        self.assertEqual(res['downgraded_free'], 1)

    def test_trial_vencido_rebaixa_para_free(self):
        store = mk('s2', trial_ends_at=timezone.now() - timedelta(days=5))
        sub = StoreSubscription.objects.create(store=store, status='trialing')
        with self.settings(BILLING_ENFORCEMENT_ENABLED=True):
            enforce_subscription_lifecycle()
        sub.refresh_from_db()
        store.refresh_from_db()
        self.assertEqual(store.plan, 'free')
        self.assertEqual(sub.status, 'canceled')

    def test_exempt_store_untouched(self):
        store = mk('s3', trial_ends_at=timezone.now() - timedelta(days=99),
                   billing_exempt=True)
        StoreSubscription.objects.create(store=store, status='trialing')
        enforce_subscription_lifecycle()
        sub = StoreSubscription.objects.get(store=store)
        self.assertEqual(sub.status, 'trialing')
        self.assertIsNone(sub.grace_until)

    def test_active_untouched(self):
        store = mk('s4', trial_ends_at=timezone.now() - timedelta(days=30))
        StoreSubscription.objects.create(store=store, status='active')
        enforce_subscription_lifecycle()
        sub = StoreSubscription.objects.get(store=store)
        self.assertEqual(sub.status, 'active')

    def test_past_due_starts_dunning(self):
        """past_due sem dunning_since → grava dunning_since=now; NÃO toca grace_until."""
        store = mk('s5')
        before = timezone.now()
        sub = StoreSubscription.objects.create(
            store=store, status='past_due', dunning_since=None,
        )
        res = enforce_subscription_lifecycle()
        sub.refresh_from_db()
        after = timezone.now()
        self.assertIsNotNone(sub.dunning_since, 'dunning_since deve ser gravado')
        self.assertGreaterEqual(sub.dunning_since, before)
        self.assertLessEqual(sub.dunning_since, after)
        self.assertIsNone(sub.grace_until, 'grace_until não deve ser tocado para past_due')
        self.assertEqual(sub.status, 'past_due', 'status não deve mudar na primeira varredura')
        self.assertEqual(res['grace_started'], 1)

    def test_past_due_dunning_vencido_rebaixa_para_free(self):
        """past_due → dunning esgotado → cai pro Grátis (não suspende mais) e marca a razão."""
        store = mk('s6')
        sub = StoreSubscription.objects.create(
            store=store, status='past_due',
            dunning_since=timezone.now() - timedelta(days=10),
        )
        res = enforce_subscription_lifecycle()
        sub.refresh_from_db()
        store.refresh_from_db()
        self.assertEqual(sub.status, 'canceled')
        self.assertEqual(store.plan, 'free')
        self.assertTrue(sub.downgraded_for_nonpayment)
        self.assertEqual(res['downgraded_free'], 1)
        self.assertEqual(res['suspended'], 0)


# ---------------------------------------------------------------------------
# Fix 2: Gate BILLING_ENFORCEMENT_ENABLED
# ---------------------------------------------------------------------------

@override_settings(BILLING_GRACE_DAYS=3, BILLING_DUNNING_DAYS=3)
class EnforcementGateTest(TestCase):
    """enforce_subscription_lifecycle deve ser no-op quando flag está OFF."""

    def test_flag_off_nao_suspende_nem_inicia_carencia(self):
        """Flag OFF: loja com trial vencido + carência vencida NÃO é suspensa."""
        store = mk('gate1',
                   trial_ends_at=timezone.now() - timedelta(days=10))
        StoreSubscription.objects.create(
            store=store,
            status='trialing',
            grace_until=timezone.now() - timedelta(days=1),  # carência também vencida
        )
        with self.settings(BILLING_ENFORCEMENT_ENABLED=False):
            res = enforce_subscription_lifecycle()
        sub = StoreSubscription.objects.get(store=store)
        self.assertEqual(sub.status, 'trialing', 'status não deve mudar com flag OFF')
        self.assertEqual(res['scanned'], 0)
        self.assertEqual(res['suspended'], 0)
        self.assertEqual(res.get('skipped'), 'enforcement_disabled')

    @override_settings(BILLING_ENFORCEMENT_ENABLED=True)
    def test_flag_on_rebaixa_normalmente(self):
        """Flag ON: loja com trial vencido DEVE ser rebaixada para o plano Grátis."""
        store = mk('gate2',
                   trial_ends_at=timezone.now() - timedelta(days=10))
        StoreSubscription.objects.create(
            store=store,
            status='trialing',
        )
        res = enforce_subscription_lifecycle()
        sub = StoreSubscription.objects.get(store=store)
        store.refresh_from_db()
        self.assertEqual(sub.status, 'canceled')
        self.assertEqual(store.plan, 'free')
        self.assertEqual(res['downgraded_free'], 1)

    @override_settings(BILLING_ENFORCEMENT_ENABLED=False)
    def test_flag_off_loja_isenta_continua_intocada(self):
        """Loja isenta deve permanecer intocada em AMBOS os estados do flag."""
        store = mk('gate3',
                   trial_ends_at=timezone.now() - timedelta(days=99),
                   billing_exempt=True)
        StoreSubscription.objects.create(store=store, status='trialing')
        res = enforce_subscription_lifecycle()
        sub = StoreSubscription.objects.get(store=store)
        self.assertEqual(sub.status, 'trialing')
        self.assertIsNone(sub.grace_until)
        self.assertEqual(res.get('skipped'), 'enforcement_disabled')

    @override_settings(BILLING_ENFORCEMENT_ENABLED=True)
    def test_flag_on_loja_isenta_continua_intocada(self):
        """Loja isenta deve permanecer intocada quando flag está ON."""
        store = mk('gate4',
                   trial_ends_at=timezone.now() - timedelta(days=99),
                   billing_exempt=True)
        StoreSubscription.objects.create(store=store, status='trialing')
        enforce_subscription_lifecycle()
        sub = StoreSubscription.objects.get(store=store)
        self.assertEqual(sub.status, 'trialing')
        self.assertIsNone(sub.grace_until)


# ---------------------------------------------------------------------------
# Fix 1: Relógios de carência/dunning zerados na recuperação
# ---------------------------------------------------------------------------

@override_settings(BILLING_GRACE_DAYS=3, BILLING_DUNNING_DAYS=3, BILLING_ENFORCEMENT_ENABLED=True)
class LifecycleClocksResetTest(TestCase):
    """dunning_since e grace_until devem ser zerados ao recuperar para active."""

    def setUp(self):
        self.owner = User.objects.create_user('clk_owner', 'c@x.com', 'x')
        self.store = Store.objects.create(
            name='ClkStore', slug='clk-store', owner=self.owner,
        )

    def test_past_due_active_past_due_nao_suspende_instantaneamente(self):
        """
        Ciclo: past_due com dunning_since antigo → authorized → past_due sem dunning.
        Após a recuperação dunning_since deve ser None, e a próxima varredura
        deve INICIAR um novo dunning (grace_started) — não suspender instantaneamente.
        """
        # 1. Sub em past_due com dunning_since já velho (5 dias atrás)
        sub = StoreSubscription.objects.create(
            store=self.store,
            status='past_due',
            mp_preapproval_id='pre_clk',
            dunning_since=timezone.now() - timedelta(days=5),
        )

        # 2. Evento authorized → deve zerar dunning_since
        result = subscription_service.apply_preapproval_event('pre_clk', 'authorized')
        self.assertTrue(result['processed'])
        sub.refresh_from_db()
        self.assertIsNone(sub.dunning_since, 'dunning_since deve ser None após authorized')
        self.assertIsNone(sub.grace_until, 'grace_until deve ser None após authorized')
        self.assertEqual(sub.status, 'active')

        # 3. Volta para past_due sem dunning_since (simula nova falha de cobrança)
        sub.status = 'past_due'
        sub.dunning_since = None
        sub.save(update_fields=['status', 'dunning_since'])

        # 4. Varredura deve INICIAR dunning, não suspender
        res = enforce_subscription_lifecycle()
        sub.refresh_from_db()
        self.assertIsNotNone(sub.dunning_since, 'varredura deve iniciar dunning clock')
        self.assertNotEqual(sub.status, 'suspended', 'não deve suspender imediatamente')
        self.assertEqual(res['grace_started'], 1)
        self.assertEqual(res['suspended'], 0)

    def test_resubscribe_zera_grace_until_e_canceled_at(self):
        """
        Re-assinar uma loja que tinha grace_until e canceled_at do ciclo anterior
        deve resultar em grace_until=None e canceled_at=None.
        """
        # Estado sujo do ciclo anterior
        sub = StoreSubscription.objects.create(
            store=self.store,
            status='suspended',
            grace_until=timezone.now() - timedelta(days=1),
            canceled_at=timezone.now() - timedelta(days=2),
            dunning_since=timezone.now() - timedelta(days=5),
        )

        # Re-subscribe via create_subscription (update_or_create)
        with patch.object(subscription_service, '_sdk', return_value=_fake_create_sdk('pre_new')):
            subscription_service.create_subscription(
                self.store, 'pro', 'owner@x.com', 'http://back'
            )

        sub.refresh_from_db()
        self.assertIsNone(sub.grace_until, 'grace_until deve ser None após re-assinar')
        self.assertIsNone(sub.canceled_at, 'canceled_at deve ser None após re-assinar')
        self.assertIsNone(sub.dunning_since, 'dunning_since deve ser None após re-assinar')
