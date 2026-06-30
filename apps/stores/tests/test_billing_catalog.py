from django.test import TestCase
from apps.stores import billing


class SetupFeeToggleTest(TestCase):
    def test_charges_setup_fee_enabled_per_plan(self):
        # Decisão 2026-06-30: adesão (setup fee) cobrada nos 3 planos.
        self.assertTrue(billing.charges_setup_fee('starter'))
        self.assertTrue(billing.charges_setup_fee('pro'))
        self.assertTrue(billing.charges_setup_fee('premium'))

    def test_charges_setup_fee_respects_catalog_flag(self):
        # O toggle funciona nos dois sentidos: desligar um plano zera a cobrança.
        original = billing.PLAN_CATALOG['pro'].get('charges_setup_fee')
        billing.PLAN_CATALOG['pro']['charges_setup_fee'] = False
        try:
            self.assertFalse(billing.charges_setup_fee('pro'))
        finally:
            billing.PLAN_CATALOG['pro']['charges_setup_fee'] = original

    def test_unknown_plan_falls_back_to_default(self):
        # Plano desconhecido cai no DEFAULT_PLAN (starter) — segue o flag dele.
        self.assertEqual(
            billing.charges_setup_fee('inexistente'),
            billing.charges_setup_fee(billing.DEFAULT_PLAN),
        )
