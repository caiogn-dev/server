from datetime import timedelta
from django.test import SimpleTestCase
from django.utils import timezone
from apps.stores.services.subscription_lifecycle import decide_transition, Transition

NOW = timezone.now()
GRACE = 3
DUN = 3


def call(**kw):
    base = dict(
        status='trialing', trial_ends_at=None, grace_until=None,
        dunning_since=None, now=NOW, grace_days=GRACE, dunning_days=DUN,
        billing_exempt=False,
    )
    base.update(kw)
    return decide_transition(**base)


class DecideTransitionTest(SimpleTestCase):
    def test_exempt_store_never_transitions(self):
        t = call(billing_exempt=True, status='trialing',
                 trial_ends_at=NOW - timedelta(days=99))
        self.assertEqual(t.action, 'none')

    def test_active_subscription_is_kept(self):
        t = call(status='active', trial_ends_at=NOW - timedelta(days=10))
        self.assertEqual(t.action, 'keep')

    def test_trial_still_running_does_nothing(self):
        t = call(status='trialing', trial_ends_at=NOW + timedelta(days=5))
        self.assertEqual(t.action, 'none')

    def test_trial_expired_downgrades_to_free(self):
        t = call(status='trialing', trial_ends_at=NOW - timedelta(hours=1))
        self.assertEqual(t.action, 'downgrade_free')

    def test_past_due_starts_dunning_clock(self):
        t = call(status='past_due', dunning_since=None)
        self.assertEqual(t.action, 'start_grace')  # reaproveita set de relógio
        self.assertEqual(t.set_grace_until, NOW + timedelta(days=DUN))

    def test_past_due_dunning_over_downgrades_to_free(self):
        t = call(status='past_due', dunning_since=NOW - timedelta(days=DUN + 1))
        self.assertEqual(t.action, 'downgrade_free')

    def test_already_suspended_or_canceled_is_terminal(self):
        self.assertEqual(call(status='suspended').action, 'none')
        self.assertEqual(call(status='canceled').action, 'none')

    # --- billing_exempt cobre todos os status ---

    def test_exempt_past_due_never_transitions(self):
        """billing_exempt curto-circuita QUALQUER status, não só trialing."""
        t = call(billing_exempt=True, status='past_due', dunning_since=None)
        self.assertEqual(t.action, 'none')
        self.assertIsNone(t.set_grace_until)

    # --- boundary temporal ---

    def test_trial_ends_exactly_now_downgrades_to_free(self):
        """`trial_ends_at == now` não é 'ainda no trial' → rebaixa pro Grátis."""
        t = call(status='trialing', trial_ends_at=NOW)
        self.assertEqual(t.action, 'downgrade_free')


class TrialEndsToFreeTest(SimpleTestCase):
    def test_trial_vencido_vira_free(self):
        t = decide_transition(
            status='trialing', trial_ends_at=NOW - timedelta(days=1),
            grace_until=None, dunning_since=None, now=NOW,
            grace_days=3, dunning_days=3, billing_exempt=False)
        self.assertEqual(t.action, 'downgrade_free')

    def test_trial_vigente_nao_mexe(self):
        t = decide_transition(
            status='trialing', trial_ends_at=NOW + timedelta(days=2),
            grace_until=None, dunning_since=None, now=NOW,
            grace_days=3, dunning_days=3, billing_exempt=False)
        self.assertEqual(t.action, 'none')

    def test_loja_isenta_nao_mexe(self):
        t = decide_transition(
            status='trialing', trial_ends_at=NOW - timedelta(days=10),
            grace_until=None, dunning_since=None, now=NOW,
            grace_days=3, dunning_days=3, billing_exempt=True)
        self.assertEqual(t.action, 'none')

    def test_past_due_ainda_inicia_dunning(self):
        t = decide_transition(
            status='past_due', trial_ends_at=None,
            grace_until=None, dunning_since=None, now=NOW,
            grace_days=3, dunning_days=3, billing_exempt=False)
        self.assertEqual(t.action, 'start_grace')

    def test_past_due_dunning_vencido_rebaixa_para_free(self):
        t = decide_transition(
            status='past_due', trial_ends_at=None, grace_until=None,
            dunning_since=NOW - timedelta(days=3), now=NOW,
            grace_days=3, dunning_days=3, billing_exempt=False)
        self.assertEqual(t.action, 'downgrade_free')

    def test_past_due_after_dunning_downgrades_not_suspends(self):
        from datetime import datetime, timezone as dtz
        now = datetime(2026, 7, 10, tzinfo=dtz.utc)
        t = decide_transition(
            status="past_due", trial_ends_at=None,
            grace_until=None, dunning_since=now - timedelta(days=5),
            now=now, grace_days=3, dunning_days=3, billing_exempt=False,
        )
        self.assertEqual(t.action, "downgrade_free")
