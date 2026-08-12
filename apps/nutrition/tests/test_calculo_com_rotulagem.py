"""
O cálculo da receita depois de ganhar alergênico, lupa frontal e a regra de
"qual ingrediente está faltando".

O caso que motivou o último: a tabela vinha vazia e o lojista não tinha como
saber que o problema era um único ingrediente sem sódio cadastrado.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.nutrition.models import (
    NutritionIngredient, ProductNutritionProfile, ProductRecipe, RecipeItem,
)
from apps.nutrition.services.calculator import calculate_recipe
from apps.stores.models import Store, StoreProduct


def ingrediente(nome, **valores):
    padrao = dict(energy_kcal=0, carbohydrates_g=0, total_sugars_g=0, added_sugars_g=0,
                  protein_g=0, total_fat_g=0, saturated_fat_g=0, trans_fat_g=0,
                  fiber_g=0, sodium_mg=0)
    padrao.update(valores)
    return NutritionIngredient.objects.create(
        canonical_name=nome, display_name=nome, allergens_reviewed=True, **padrao,
    )


class CalculoComRotulagemTest(TestCase):
    def setUp(self):
        dono = get_user_model().objects.create_user(
            username="dono-nutricao", email="dono-nutricao@teste.local", password="x",
        )
        self.store = Store.objects.create(name="Loja Teste", slug="loja-teste", owner=dono)
        self.produto = StoreProduct.objects.create(store=self.store, name="Prato", slug="prato", price=10)
        self.recipe = ProductRecipe.objects.create(product=self.produto, serving_size_g=Decimal("100"))

    def test_diz_qual_ingrediente_esta_sem_dado(self):
        RecipeItem.objects.create(recipe=self.recipe, ingredient=ingrediente("Arroz"), quantity_g=100)
        RecipeItem.objects.create(recipe=self.recipe,
                                  ingredient=ingrediente("Bacalhau", sodium_mg=None),
                                  quantity_g=100)

        r = calculate_recipe(self.recipe)

        self.assertIn("sodium_mg", r["missing_nutrients"])
        self.assertEqual(r["missing_by_nutrient"]["sodium_mg"], ["Bacalhau"])
        self.assertEqual(r["incomplete_ingredients"], ["Bacalhau"])

    def test_receita_completa_nao_acusa_ingrediente(self):
        RecipeItem.objects.create(recipe=self.recipe, ingredient=ingrediente("Arroz"), quantity_g=100)
        r = calculate_recipe(self.recipe)
        self.assertEqual(r["incomplete_ingredients"], [])
        self.assertTrue(r["front_of_pack"]["conclusivo"])

    def test_lupa_frontal_sai_do_valor_por_100g(self):
        # 100 g de banha pura: 40 g de saturada por 100 g, muito acima de 6.
        RecipeItem.objects.create(recipe=self.recipe,
                                  ingredient=ingrediente("Banha", saturated_fat_g=40),
                                  quantity_g=100)
        r = calculate_recipe(self.recipe)
        self.assertEqual(r["front_of_pack"]["texto"], ["ALTO EM GORDURA SATURADA"])

    def test_liquido_usa_o_limite_de_liquido(self):
        ProductNutritionProfile.objects.create(
            product=self.produto, recipe=self.recipe,
            physical_form=ProductNutritionProfile.PhysicalForm.LIQUIDO,
        )
        self.recipe.refresh_from_db()
        RecipeItem.objects.create(recipe=self.recipe,
                                  ingredient=ingrediente("Xarope", added_sugars_g=10),
                                  quantity_g=100)

        r = calculate_recipe(self.recipe)

        self.assertEqual(r["front_of_pack"]["forma"], "liquido")
        self.assertEqual(r["front_of_pack"]["texto"], ["ALTO EM AÇÚCAR ADICIONADO"])

    def test_valores_de_etiqueta_vem_arredondados_e_os_crus_continuam(self):
        RecipeItem.objects.create(recipe=self.recipe,
                                  ingredient=ingrediente("Óleo", trans_fat_g=Decimal("0.04"),
                                                         energy_kcal=Decimal("123.4")),
                                  quantity_g=100)
        r = calculate_recipe(self.recipe)

        self.assertEqual(r["label_per_100g"]["trans_fat_g"], Decimal("0"))
        self.assertEqual(r["label_per_100g"]["energy_kcal"], Decimal("123"))
        self.assertEqual(r["per_100g"]["trans_fat_g"], Decimal("0.04"))

    def test_alergenico_cai_dos_ingredientes_sem_ninguem_digitar(self):
        leite = ingrediente("Muçarela")
        leite.allergens = ["leite"]
        leite.save()
        farinha = ingrediente("Farinha de trigo")
        farinha.allergens = ["trigo"]
        farinha.save()
        RecipeItem.objects.create(recipe=self.recipe, ingredient=leite, quantity_g=50)
        RecipeItem.objects.create(recipe=self.recipe, ingredient=farinha, quantity_g=50)

        r = calculate_recipe(self.recipe)

        self.assertIn("CONTÉM LEITE E TRIGO.", r["allergens"]["texto"])
        self.assertIn("CONTÉM GLÚTEN.", r["allergens"]["texto"])

    def test_receita_sem_alergenico_declara_que_nao_tem_gluten(self):
        RecipeItem.objects.create(recipe=self.recipe, ingredient=ingrediente("Arroz"), quantity_g=100)
        r = calculate_recipe(self.recipe)
        self.assertEqual(r["allergens"]["texto"], "NÃO CONTÉM GLÚTEN.")
        self.assertTrue(r["allergens"]["revisado"])

    def test_ingrediente_sem_revisao_nao_gera_declaracao(self):
        # O caso perigoso: importar 600 alimentos da TACO sem alergênico e a
        # etiqueta sair afirmando "NÃO CONTÉM GLÚTEN" para todos eles.
        cru = ingrediente("Farinha importada")
        cru.allergens_reviewed = False
        cru.save()
        RecipeItem.objects.create(recipe=self.recipe, ingredient=cru, quantity_g=100)

        r = calculate_recipe(self.recipe)

        self.assertFalse(r["allergens"]["revisado"])
        self.assertEqual(r["allergens"]["texto"], "")
        self.assertEqual(r["allergens"]["ingredientes_sem_revisao"], ["Farinha importada"])
