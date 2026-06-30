from django.test import TestCase
from apps.stores import billing


class SetupFeeToggleTest(TestCase):
    def test_charges_setup_fee_default_false(self):
        # Toggle por plano; default desligado no primeiro ship (caminho curto).
        self.assertFalse(billing.charges_setup_fee('starter'))

    def test_charges_setup_fee_respects_catalog_flag(self):
        original = billing.PLAN_CATALOG['pro'].get('charges_setup_fee')
        billing.PLAN_CATALOG['pro']['charges_setup_fee'] = True
        try:
            self.assertTrue(billing.charges_setup_fee('pro'))
        finally:
            if original is None:
                billing.PLAN_CATALOG['pro'].pop('charges_setup_fee', None)
            else:
                billing.PLAN_CATALOG['pro']['charges_setup_fee'] = original

    def test_unknown_plan_falls_back_to_default(self):
        self.assertFalse(billing.charges_setup_fee('inexistente'))
