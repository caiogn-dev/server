from decimal import Decimal
from django.test import SimpleTestCase
from apps.nutrition.services.description_parser import parse_weighted_ingredients


class DescriptionParserTests(SimpleTestCase):
    def test_parses_agriao_both_weight_orders_and_ignores_total(self):
        parsed = parse_weighted_ingredients("Porção total: 330 g 120 g de frango desfiado 130g arroz branco 80 g de feijão preto")
        self.assertEqual([(i["ingredient_name"], i["quantity_g"]) for i in parsed["items"]], [
            ("Frango cozido", Decimal("120")), ("Arroz branco cozido", Decimal("130")), ("Feijão preto cozido", Decimal("80")),
        ])
        self.assertEqual(parsed["unmatched_weights"], [])

    def test_parses_salad_and_keeps_unknown_weight_ambiguous(self):
        parsed = parse_weighted_ingredients("Alface 90 g, frango grelhado 120 g, milho 45 g, cenoura 45 g")
        self.assertEqual([i["ingredient_name"] for i in parsed["items"]], ["Alface", "Frango grelhado", "Cenoura"])
        self.assertEqual(parsed["unmatched_weights"], ["45 g"])

    def test_range_is_never_silently_averaged(self):
        parsed = parse_weighted_ingredients("30~50g de legumes")
        self.assertEqual(parsed["items"], [])
        self.assertEqual(parsed["unmatched_weights"], ["50g"])

    def test_does_not_assign_unknown_component_to_previous_ingredient(self):
        parsed = parse_weighted_ingredients("120g frango desfiado. 20g de mussarela")
        self.assertEqual([(i["ingredient_name"], i["quantity_g"]) for i in parsed["items"]], [("Frango cozido", Decimal("120"))])
        self.assertEqual(parsed["unmatched_weights"], ["20g"])
