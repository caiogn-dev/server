from decimal import Decimal
from unittest.mock import Mock
from django.test import SimpleTestCase
from apps.nutrition.services.calculator import calculate_recipe


class RecipeCalculatorTests(SimpleTestCase):
    def item(self, grams, **values):
        ingredient = Mock(**{field: values.get(field, Decimal("0")) for field in (
            "energy_kcal", "carbohydrates_g", "total_sugars_g", "added_sugars_g", "protein_g",
            "total_fat_g", "saturated_fat_g", "trans_fat_g", "fiber_g", "sodium_mg")})
        # O cálculo passou a ler alergênicos junto (RDC 26/2015). Sem estes
        # campos o Mock devolve outro Mock, que não é iterável.
        ingredient.display_name = values.get("display_name", "Ingrediente")
        ingredient.allergens = values.get("allergens", [])
        ingredient.may_contain = values.get("may_contain", [])
        ingredient.allergens_reviewed = values.get("allergens_reviewed", True)
        return Mock(ingredient=ingredient, quantity_g=Decimal(str(grams)), prepared_quantity_g=None)

    def recipe(self, items, serving=100):
        manager = Mock(); manager.select_related.return_value.all.return_value = items
        return Mock(items=manager, prepared_weight_g=None, serving_size_g=Decimal(str(serving)))

    def test_calculates_total_per_100g_serving_and_daily_value(self):
        result = calculate_recipe(self.recipe([self.item(100, energy_kcal=Decimal("100"), protein_g=Decimal("10")), self.item(100, energy_kcal=Decimal("200"), protein_g=Decimal("20"))], serving=50))
        self.assertEqual(result["per_100g"]["energy_kcal"], Decimal("150.00"))
        self.assertEqual(result["per_serving"]["protein_g"], Decimal("7.50"))

    def test_missing_value_is_not_silently_treated_as_zero(self):
        item = self.item(100); item.ingredient.total_sugars_g = None
        result = calculate_recipe(self.recipe([item]))
        self.assertIsNone(result["per_100g"]["total_sugars_g"])
        self.assertIn("total_sugars_g", result["missing_nutrients"])
