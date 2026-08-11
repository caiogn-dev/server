from django.test import SimpleTestCase

from apps.nutrition.management.commands.enrich_salad_taco_ingredients import QUERIDINHA_600G, ROWS


class SaladTacoRowsTests(SimpleTestCase):
    def test_rows_keep_approximations_explicit(self):
        self.assertFalse(ROWS["milho"][-1])
        self.assertFalse(ROWS["gergelim"][-1])
        self.assertTrue(ROWS["cebola roxa"][-1])
        self.assertTrue(ROWS["batata palha"][-1])

    def test_queridinha_technical_sheet_totals_600g(self):
        self.assertEqual(sum(quantity for _, quantity in QUERIDINHA_600G), 600)
