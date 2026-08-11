from decimal import Decimal
from django.test import SimpleTestCase
from apps.nutrition.services.description_parser import parse_raw_components, format_recipe_description


class RawDescriptionParserTests(SimpleTestCase):
    def test_salad_list_and_comma_format(self):
        rows = parse_raw_components("Alface 90 g, filé de frango 120 g, milho 45 g. Acompanha molho especial.")
        self.assertEqual([(r["raw_name"], r["quantity_g"]) for r in rows], [
            ("alface", Decimal("90")), ("file de frango", Decimal("120")), ("milho", Decimal("45")),
        ])

    def test_weight_first_agriao_format_ignores_total(self):
        rows = parse_raw_components("Porção total: 330 g 120 g de frango desfiado 130 g de arroz branco 80 g de feijão preto")
        self.assertEqual([r["quantity_g"] for r in rows], [Decimal("120"), Decimal("130"), Decimal("80")])

    def test_formats_like_queridinha(self):
        rows = [{"raw_name":"alface","quantity_g":Decimal("90")},{"raw_name":"frango","quantity_g":Decimal("120")}]
        text = format_recipe_description("Salada", rows, "Acompanha molho especial.")
        self.assertIn("- Alface 90 g", text)
        self.assertIn("- Frango 120 g", text)
        self.assertIn("*Acompanha molho especial.*", text)

    def test_component_joined_by_e(self):
        rows = parse_raw_components("gergelim 1 g e cebola roxa 15 g")
        self.assertEqual([(row["raw_name"], row["quantity_g"]) for row in rows], [
            ("gergelim", Decimal("1")), ("cebola roxa", Decimal("15")),
        ])
