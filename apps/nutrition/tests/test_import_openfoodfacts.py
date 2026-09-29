"""Open Food Facts → ingredientes globais com marca. O que interessa: unidades
convertidas certo (sódio g→mg, sal→sódio), incompleto fora, alergênicos das tags."""
from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.nutrition.management.commands.import_openfoodfacts import alergenicos_do_off, mapear_produto_off
from apps.nutrition.models import NutritionIngredient

QUEIJO = {
    "code": "7891234500011", "product_name": "queijo minas padrão", "brands": "Tirolez, Grupo X", "quantity": "500 g",
    "categories_tags": ["en:dairies", "en:cheeses", "pt:queijo-minas"],
    "allergens_tags": ["en:milk"], "traces_tags": ["en:soybeans"],
    "nutriments": {"energy-kcal_100g": 320, "carbohydrates_100g": 3.2, "sugars_100g": 1.1, "proteins_100g": 23,
                   "fat_100g": 25, "saturated-fat_100g": 16, "sodium_100g": 0.62, "fiber_100g": 0},
}
MOLHO_SO_SAL = {**QUEIJO, "code": "789000", "product_name": "Molho de tomate", "brands": "Pomarola",
                "nutriments": {"energy-kcal_100g": 30, "carbohydrates_100g": 6, "sugars_100g": 4, "proteins_100g": 1,
                               "fat_100g": 0.2, "saturated-fat_100g": 0, "salt_100g": 1.0}}
INCOMPLETO = {**QUEIJO, "code": "1", "nutriments": {"energy-kcal_100g": 100}}
SEM_MARCA = {**QUEIJO, "code": "2", "brands": ""}


class MapeamentoTests(TestCase):
    def test_queijo_com_marca_e_sodio_em_mg(self):
        r = mapear_produto_off(QUEIJO)
        self.assertEqual(r["display_name"], "Queijo minas padrão — Tirolez")
        self.assertEqual(r["canonical_name"], "queijo minas padrão — tirolez")
        self.assertEqual(r["sodium_mg"], Decimal("620.0000"))
        self.assertEqual(r["energy_kcal"], Decimal("320"))
        self.assertEqual(r["allergens"], ["leite"]); self.assertEqual(r["may_contain"], ["soja"])
        self.assertTrue(r["allergens_reviewed"])
        self.assertEqual(r["category"], "queijo minas")
        self.assertEqual(r["source"], NutritionIngredient.Source.OFF)
        self.assertIn("openfoodfacts.org/produto/7891234500011", r["source_reference"])

    def test_sal_vira_sodio_e_incompleto_ou_sem_marca_fica_fora(self):
        self.assertEqual(mapear_produto_off(MOLHO_SO_SAL)["sodium_mg"], Decimal("400.0000"))
        self.assertIsNone(mapear_produto_off(INCOMPLETO))
        self.assertIsNone(mapear_produto_off(SEM_MARCA))
        self.assertEqual(alergenicos_do_off(["en:milk", "en:gluten", "en:weird"]), ["leite", "trigo"])

    def test_comando_grava_e_nao_duplica_a_mesma_embalagem(self):
        pagina = {"count": 3, "products": [QUEIJO, {**QUEIJO, "code": "7891234500028", "quantity": "1 kg"}, INCOMPLETO]}
        with patch("apps.nutrition.management.commands.import_openfoodfacts.buscar_pagina", return_value=pagina):
            call_command("import_openfoodfacts", "--max", "50", "--pausa", "0")
        q = NutritionIngredient.objects.filter(source=NutritionIngredient.Source.OFF)
        self.assertEqual(q.count(), 1)
        i = q.get()
        self.assertIsNone(i.store); self.assertEqual(i.source_code, "7891234500011"); self.assertEqual(i.allergens, ["leite"])
