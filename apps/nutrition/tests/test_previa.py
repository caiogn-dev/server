"""
A prévia calcula sem gravar.

A tela precisa responder enquanto a pessoa mexe nas gramas. Salvar a cada
tecla mudaria a etiqueta de um produto que está no ar enquanto alguém ainda
está experimentando proporção.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.nutrition.models import NutritionIngredient, ProductRecipe
from apps.nutrition.services.calculator import calculate_recipe
from apps.nutrition.services.previa import montar


def ingrediente(nome, **valores):
    padrao = dict(energy_kcal=100, carbohydrates_g=10, total_sugars_g=0, added_sugars_g=0,
                  protein_g=5, total_fat_g=2, saturated_fat_g=1, trans_fat_g=0,
                  fiber_g=1, sodium_mg=50)
    padrao.update(valores)
    return NutritionIngredient.objects.create(
        canonical_name=nome, display_name=nome, source="manual",
        allergens_reviewed=True, **padrao)


class MontarPreviaTest(TestCase):
    def test_calcula_igual_ao_salvo(self):
        # O ponto do desenho: mesmo código. Duas implementações divergiriam
        # justamente onde dói — número visto ≠ número impresso.
        a, b = ingrediente("A"), ingrediente("B", energy_kcal=200)
        previa = montar([{"ingredient": str(a.id), "quantity_g": 100},
                         {"ingredient": str(b.id), "quantity_g": 100}], serving_size_g=100)
        r = calculate_recipe(previa)
        self.assertEqual(r["per_100g"]["energy_kcal"], Decimal("150.00"))

    def test_nao_grava_receita(self):
        a = ingrediente("A")
        montar([{"ingredient": str(a.id), "quantity_g": 100}])
        self.assertEqual(ProductRecipe.objects.count(), 0)

    def test_linha_pela_metade_e_ignorada(self):
        # A prévia roda enquanto a pessoa digita: linha sem ingrediente ainda
        # não é erro, é trabalho em andamento.
        a = ingrediente("A")
        previa = montar([{"ingredient": str(a.id), "quantity_g": 100},
                         {"ingredient": "", "quantity_g": 50},
                         {"ingredient": str(a.id), "quantity_g": 0}])
        self.assertEqual(len(previa.items.all()), 1)

    def test_ingrediente_inexistente_nao_quebra(self):
        previa = montar([{"ingredient": "00000000-0000-0000-0000-000000000000", "quantity_g": 10}])
        self.assertEqual(len(previa.items.all()), 0)

    def test_quantidade_invalida_nao_quebra(self):
        a = ingrediente("A")
        previa = montar([{"ingredient": str(a.id), "quantity_g": "abc"}])
        self.assertEqual(len(previa.items.all()), 0)

    def test_forma_liquida_chega_no_calculo(self):
        a = ingrediente("Xarope", added_sugars_g=10)
        r = calculate_recipe(montar([{"ingredient": str(a.id), "quantity_g": 100}],
                                    physical_form="liquido"))
        self.assertEqual(r["front_of_pack"]["forma"], "liquido")
        self.assertEqual(r["front_of_pack"]["texto"], ["ALTO EM AÇÚCAR ADICIONADO"])


class PreviaEndpointTest(TestCase):
    def setUp(self):
        u = get_user_model().objects.create_user(username="chef", email="chef@t.local", password="x")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=u).key}")

    def test_devolve_calculo_sem_criar_receita(self):
        a = ingrediente("Arroz")
        r = self.client.post("/api/v1/nutrition/recipes/previa/", {
            "items": [{"ingredient": str(a.id), "quantity_g": 200}],
            "serving_size_g": 100,
        }, format="json")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(float(r.json()["total_weight_g"]), 200.0)
        self.assertEqual(ProductRecipe.objects.count(), 0)

    def test_receita_vazia_nao_estoura(self):
        r = self.client.post("/api/v1/nutrition/recipes/previa/", {"items": []}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_exige_autenticacao(self):
        self.assertEqual(APIClient().post("/api/v1/nutrition/recipes/previa/", {}, format="json").status_code,
                         401)
